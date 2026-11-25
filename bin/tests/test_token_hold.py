import os
import shutil
import socket
import stat
import tempfile
from pathlib import Path

import pytest

VALUE = "a-fake-bearer-of-more-than-thirty-two-characters"


@pytest.fixture
def hold(load_module):
    return load_module("token_hold")


@pytest.fixture
def folder():
    # Unix socket paths stop at about 104 bytes, which pytest's tmp_path can pass.
    base = "/dev/shm" if Path("/dev/shm").is_dir() else None
    directory = Path(tempfile.mkdtemp(prefix="th-", dir=base))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture
def held(hold, folder):
    path = folder / "fleet-1" / "token.sock"
    hold.start(path, VALUE)
    yield path
    hold.stop(path)


@pytest.fixture
def left_behind(hold, folder):
    path = folder / "fleet-1" / "token.sock"
    path.parent.mkdir(mode=0o700)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as killed:
        killed.bind(str(path))
    yield path
    hold.stop(path)


class TestPrivateBase:
    @pytest.mark.parametrize("platform,environ,shm_exists,expected", [
        ("darwin", {"TMPDIR": "/var/folders/ab/T/"}, True, Path("/var/folders/ab/T/")),
        ("darwin", {}, True, None),
        ("linux", {"TMPDIR": "/tmp"}, True, "shm"),
        ("linux", {}, False, None),
    ])
    def should_pick_the_users_tmpdir_on_macos_and_the_containers_shm_on_linux(
            self, hold, tmp_path, platform, environ, shm_exists, expected):
        shm = tmp_path if shm_exists else tmp_path / "missing"

        base = hold.private_base(platform, environ, shm)

        assert base == (shm if expected == "shm" else expected)

    def should_name_one_socket_per_user_and_token_in_the_base(self, hold):
        assert (hold.socket_in(Path("/dev/shm"), 1001, "A_TOKEN"), hold.socket_in(None, 1001, "A_TOKEN")) == (
            Path("/dev/shm/fleet-1001/A_TOKEN.sock"), None)

    def should_never_answer_with_a_token_held_under_another_name(self, hold, folder):
        hold.start(hold.socket_in(folder, 1, "OLD_TOKEN"), VALUE)
        try:
            assert hold.fetch(hold.socket_in(folder, 1, "NEW_TOKEN")) is None
        finally:
            hold.stop(hold.socket_in(folder, 1, "OLD_TOKEN"))


class TestHolder:
    def should_answer_the_value_it_was_started_with(self, hold, held):
        assert hold.fetch(held) == VALUE

    def should_open_its_folder_and_socket_to_its_user_only(self, held):
        modes = (stat.S_IMODE(held.parent.stat().st_mode), stat.S_IMODE(held.stat().st_mode))

        assert modes == (0o700, 0o600)

    def should_remove_its_socket_before_it_confirms_a_stop(self, hold, held):
        stopped = hold.stop(held)

        assert (stopped, held.exists(), hold.fetch(held)) == (True, False, None)

    def should_answer_nothing_where_no_holder_listens(self, hold, folder):
        stale = folder / "stale.sock"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as unbound:
            unbound.bind(str(stale))

        assert (hold.fetch(folder / "none.sock"), hold.fetch(stale), hold.stop(folder / "none.sock")) == (None, None, False)

    def should_refuse_a_folder_that_other_users_can_open(self, hold, folder):
        shared = folder / "shared"
        shared.mkdir()
        os.chmod(shared, 0o755)

        with pytest.raises(hold.HoldError, match="only this user"):
            hold.start(shared / "token.sock", VALUE)

    def should_refuse_to_start_a_second_holder(self, hold, held):
        with pytest.raises(hold.HoldError, match="already answers"):
            hold.start(held, "another")

    def should_replace_the_socket_a_killed_holder_left_behind(self, hold, left_behind):
        hold.start(left_behind, VALUE)

        assert hold.fetch(left_behind) == VALUE


class TestLaunch:
    @pytest.fixture
    def spawned(self, hold, monkeypatch):
        runs = []

        class FakePopen:
            def __init__(self, argv, **kwargs):
                self.stdin = self
                self.written = b""
                self.closed = False
                self.returncode = 1
                runs.append((argv, kwargs, self))

            def write(self, data):
                self.written += data

            def close(self):
                self.closed = True

            def poll(self):
                return self.returncode

        monkeypatch.setattr(hold.subprocess, "Popen", FakePopen)
        return runs

    def should_hand_the_value_over_on_stdin_only(self, hold, folder, spawned, monkeypatch):
        monkeypatch.setenv("EXPORTED_BEARER", VALUE)

        hold.launch(folder / "token.sock", VALUE)

        argv, kwargs, holder = spawned[0]
        assert (VALUE in " ".join(argv), VALUE in "".join(kwargs["env"].values()), holder.written, holder.closed,
                kwargs["start_new_session"]) == (False, False, VALUE.encode(), True, True)

    def should_fail_when_the_holder_exits_before_it_answers(self, hold, folder, spawned):
        with pytest.raises(hold.HoldError, match="exited with 1"):
            hold.start(folder / "fleet-1" / "token.sock", VALUE)
