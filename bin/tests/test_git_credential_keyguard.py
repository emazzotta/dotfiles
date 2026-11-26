import io
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).parent.parent
NAME = "READ_TOKEN"
VALUE = "a-fake-read-token-of-more-than-thirty-two-characters"
SLOW_LOAD_S = 0.3
REQUEST = "protocol=https\nhost=example.com\n\n"


@pytest.fixture
def helper(load_script):
    return load_script("git-credential-keyguard")


@pytest.fixture
def folder():
    # Unix socket paths stop at about 104 bytes, which pytest's tmp_path can pass.
    base = "/dev/shm" if Path("/dev/shm").is_dir() else None
    directory = Path(tempfile.mkdtemp(prefix="gck-", dir=base))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture
def at(helper, folder, monkeypatch):
    path = folder / "fleet-1" / f"{NAME}.sock"
    monkeypatch.setattr(helper, "hold_socket", lambda name: path)
    yield path
    helper.token_hold.stop(path)


@pytest.fixture
def loads(helper, monkeypatch):
    calls = []

    def fake_load(name):
        calls.append(name)
        time.sleep(SLOW_LOAD_S)
        return VALUE

    monkeypatch.setattr(helper, "load", fake_load)
    return calls


@pytest.fixture
def request_on_stdin(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(REQUEST))


class TestAnswer:
    def should_answer_with_the_held_value_without_loading(self, helper, at, loads):
        helper.token_hold.start(at, VALUE)

        assert (helper.answer(NAME), loads) == (f"password={VALUE}\n", [])

    def should_load_once_and_hold_the_value_for_the_next_request(self, helper, at, loads):
        answers = [helper.answer(NAME), helper.answer(NAME)]

        assert (answers, loads, helper.token_hold.fetch(at)) == ([f"password={VALUE}\n"] * 2, [NAME], VALUE)

    def should_load_once_when_two_requests_arrive_together(self, helper, at, loads):
        answers = []
        requests = [threading.Thread(target=lambda: answers.append(helper.answer(NAME))) for _ in range(2)]

        for each in requests:
            each.start()
        for each in requests:
            each.join()

        assert (answers, loads) == ([f"password={VALUE}\n"] * 2, [NAME])

    def should_tell_git_to_stop_asking_when_the_load_fails(self, helper, at, monkeypatch, capsys):
        def refused(name):
            raise helper.LoadError("Touch ID cancelled")

        monkeypatch.setattr(helper, "load", refused)

        answer = helper.answer(NAME)

        assert (answer, helper.token_hold.fetch(at)) == ("quit=1\n", None)
        assert "no value for READ_TOKEN: Touch ID cancelled" in capsys.readouterr().err

    def should_still_answer_when_the_value_cannot_be_held(self, helper, at, loads, monkeypatch):
        def broken(path, value):
            raise helper.token_hold.HoldError("the holder exited with 1")

        monkeypatch.setattr(helper.token_hold, "start", broken)

        assert helper.answer(NAME) == f"password={VALUE}\n"

    def should_load_every_time_where_the_box_has_no_private_folder(self, helper, loads, monkeypatch):
        monkeypatch.setattr(helper, "hold_socket", lambda name: None)

        answers = [helper.answer(NAME), helper.answer(NAME)]

        assert (answers, loads) == ([f"password={VALUE}\n"] * 2, [NAME, NAME])


class TestLoad:
    def should_report_only_the_first_line_of_a_failed_load(self, helper, monkeypatch):
        def failed(keys, environ):
            raise helper.envify.EnvifyError("\nTouch ID cancelled\nserver returned 403\n")

        monkeypatch.setattr(helper.envify, "values_via_shell", failed)

        with pytest.raises(helper.LoadError, match="^Touch ID cancelled$"):
            helper.load(NAME)

    def should_refuse_an_empty_value(self, helper, monkeypatch):
        monkeypatch.setattr(helper.envify, "values_via_shell", lambda keys, environ: {NAME: ""})

        with pytest.raises(helper.LoadError, match="READ_TOKEN is empty"):
            helper.load(NAME)

    @pytest.mark.parametrize("path,expected", [
        ("/usr/bin", f"/usr/bin{os.pathsep}{BIN_DIR.resolve()}"),
        (None, str(BIN_DIR.resolve())),
    ])
    def should_find_envify_in_its_own_folder_after_the_callers_path(self, helper, path, expected):
        environ = {} if path is None else {"PATH": path}

        assert helper.with_own_folder_on_path(environ)["PATH"] == expected


class TestMain:
    def should_stop_the_holder_when_git_erases_the_value(self, helper, at, request_on_stdin):
        helper.token_hold.start(at, VALUE)

        code = helper.main([NAME, "erase"])

        assert (code, helper.token_hold.fetch(at)) == (0, None)

    @pytest.mark.parametrize("operation", ["store", "capability"])
    def should_ignore_every_other_operation(self, helper, at, loads, request_on_stdin, capsys, operation):
        code = helper.main([NAME, operation])

        assert (code, capsys.readouterr().out, loads) == (0, "", [])

    @pytest.mark.parametrize("arguments", [["read_token", "get"], ["A;B", "get"], [NAME], []])
    def should_refuse_anything_but_a_keyguard_name_and_an_operation(self, helper, loads, arguments, capsys):
        code = helper.main(arguments)

        assert (code, loads) == (2, [])
        assert "usage:" in capsys.readouterr().err

    def should_print_its_usage_on_help(self, helper, capsys):
        assert (helper.main(["--help"]), capsys.readouterr().out.startswith("usage:")) == (0, True)


@pytest.mark.slow
class TestThroughGit:
    @pytest.fixture
    def name(self, load_module):
        token = f"GCK_TEST_{os.getpid()}"
        yield token
        hold = load_module("token_hold")
        at = hold.socket_in(hold.private_base(sys.platform, os.environ, hold.SHM), os.getuid(), token)
        if at is not None:
            hold.stop(at)

    @pytest.fixture
    def git(self, tmp_path, name):
        mock_dir = tmp_path / "mock_bin"
        mock_dir.mkdir()
        (mock_dir / "envify").write_text(f'echo load >> "{tmp_path / "loads"}"\nexport {name}={VALUE}\n')
        config = tmp_path / "gitconfig"
        config.write_text(
            '[credential "https://example.com/owner/"]\n'
            "\thelper =\n"
            f"\thelper = {BIN_DIR.resolve() / 'git-credential-keyguard'} {name}\n"
            "\tusername = owner\n")
        env = {**os.environ, "PATH": f"{mock_dir}{os.pathsep}{os.environ['PATH']}", "GIT_CONFIG_GLOBAL": str(config),
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "SSH_ASKPASS": ""}

        def run(action, url):
            return subprocess.run(["git", "credential", action], input=f"url={url}\n\n", capture_output=True,
                                  text=True, env=env)

        run.loads = lambda: len((tmp_path / "loads").read_text().splitlines()) if (tmp_path / "loads").exists() else 0
        return run

    def should_answer_git_from_one_load_until_git_rejects_the_value(self, git):
        url = "https://example.com/owner/repo.git"

        first, second = git("fill", url), git("fill", url)
        loads_before_reject = git.loads()
        git("reject", url)
        git("fill", url)

        assert (first.stdout, second.stdout) == (
            f"protocol=https\nhost=example.com\nusername=owner\npassword={VALUE}\n",) * 2
        assert (loads_before_reject, git.loads()) == (1, 2)

    def should_stay_silent_for_a_url_outside_its_scope(self, git):
        result = git("fill", "https://example.com/other/repo.git")

        assert (result.returncode != 0, VALUE in result.stdout, git.loads()) == (True, False, 0)
