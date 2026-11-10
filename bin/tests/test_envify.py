import io
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

WRAPPER = Path(__file__).parent.parent / "envify"


@pytest.fixture
def envify(load_script):
    return load_script("envify.py")


@pytest.fixture
def devbox_shim(tmp_path):
    return tmp_path / "devbox-envify"


@pytest.fixture
def source_envify(tmp_path, devbox_shim):
    def _source(envify_py_body):
        stub = tmp_path / "bin" / "envify.py"
        stub.parent.mkdir()
        stub.write_text(envify_py_body)
        chain = 'source "$1" ENVIFY_TEST_TOKEN && echo "loaded:$ENVIFY_TEST_TOKEN"'
        return subprocess.run(["bash", "-c", chain, "bash", str(WRAPPER)], capture_output=True, text=True,
                              env={**os.environ, "DOTFILESPATH": str(tmp_path), "ENVIFY_DEVBOX_SHIM": str(devbox_shim)})
    return _source


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b"stored"


def http_error(envify, code):
    return envify.urllib.error.HTTPError("http://localhost", code, "error", {}, io.BytesIO(b"denied"))


def raise_or_return(answer):
    if isinstance(answer, Exception):
        raise answer
    return answer


class TestLoadEnv:
    def should_export_resolved_secrets_into_the_environment(self, envify, monkeypatch):
        monkeypatch.delenv("ENVIFY_TEST_A", raising=False)
        monkeypatch.delenv("ENVIFY_TEST_B", raising=False)
        monkeypatch.setattr(envify, "_keyguard_available", lambda: False)
        monkeypatch.setattr(envify, "_resolve_via_server",
                            lambda *keys: {"ENVIFY_TEST_A": "1", "ENVIFY_TEST_B": "base64:Yg=="})

        envify.load_env(("ENVIFY_TEST_A", "ENVIFY_TEST_B"))

        assert (os.environ["ENVIFY_TEST_A"], os.environ["ENVIFY_TEST_B"]) == ("1", "b")

    def should_not_resolve_keys_already_present(self, envify, monkeypatch):
        monkeypatch.setenv("ENVIFY_TEST_A", "present")
        monkeypatch.setattr(envify, "_keyguard_available", lambda: False)
        resolved = []
        monkeypatch.setattr(envify, "_resolve_via_server",
                            lambda *keys: resolved.append(keys) or {})

        envify.load_env(("ENVIFY_TEST_A",))

        assert resolved == []


class TestGuiSession:
    @pytest.fixture
    def launchd(self, envify, monkeypatch):
        def _answer(domain, status=0):
            monkeypatch.setattr(envify.shutil, "which", lambda name: f"/bin/{name}")
            monkeypatch.setattr(envify.subprocess, "run",
                                lambda args, **kwargs: envify.subprocess.CompletedProcess(args, status, f"{domain}\n"))
        return _answer

    def should_report_a_shell_in_the_background_domain_as_outside(self, envify, launchd):
        launchd("Background")

        assert envify._outside_gui_session() is True

    def should_report_a_shell_in_the_aqua_domain_as_inside(self, envify, launchd):
        launchd("Aqua")

        assert envify._outside_gui_session() is False

    def should_report_inside_when_launchctl_cannot_name_the_domain(self, envify, launchd):
        launchd("", status=1)

        assert envify._outside_gui_session() is False

    def should_report_inside_where_there_is_no_launchctl(self, envify, monkeypatch):
        monkeypatch.setattr(envify.shutil, "which", lambda name: None)

        assert envify._outside_gui_session() is False


class TestKeychainRoute:
    @pytest.fixture
    def route(self, envify, monkeypatch):
        def _route(outside):
            monkeypatch.setattr(envify, "_keyguard_available", lambda: True)
            monkeypatch.setattr(envify, "_outside_gui_session", lambda: outside)
            monkeypatch.setattr(envify, "_resolve_via_keyguard", lambda *keys: {"ENVIFY_TEST_A": "keyguard"})
            monkeypatch.setattr(envify, "_resolve_via_server", lambda *keys: {"ENVIFY_TEST_A": "server"})
            monkeypatch.delenv("ENVIFY_TEST_A", raising=False)
        return _route

    @pytest.mark.parametrize("outside, source", [(True, "server"), (False, "keyguard")])
    def should_resolve_through_the_server_only_outside_the_gui_session(self, envify, route, outside, source):
        route(outside)

        envify.load_env(("ENVIFY_TEST_A",))

        assert os.environ["ENVIFY_TEST_A"] == source

    def should_list_through_the_server_outside_the_gui_session(self, envify, route, monkeypatch, capsys):
        route(True)
        monkeypatch.setattr(envify.subprocess, "run", lambda *args, **kwargs: pytest.fail("ran keyguard list"))
        monkeypatch.setattr(envify, "_require_host", lambda: "localhost")
        monkeypatch.setattr(envify, "_server_get", lambda host, path, timeout: "ENVIFY_TEST_A\n")

        envify.list_params()

        assert capsys.readouterr().out == "ENVIFY_TEST_A\n"


class TestSourcing:
    def should_export_the_fetched_secret_into_the_sourcing_shell(self, source_envify):
        result = source_envify('print("export ENVIFY_TEST_TOKEN=t0ken")\n')

        assert (result.returncode, result.stdout) == (0, "loaded:t0ken\n")

    def should_stop_the_chain_when_the_secret_cannot_be_fetched(self, source_envify):
        result = source_envify('import sys\nprint("Error: server returned 403", file=sys.stderr)\nsys.exit(1)\n')

        assert (result.returncode, result.stdout) == (1, "")
        assert "server returned 403" in result.stderr


class TestDevboxShim:
    BRIDGE_CLIENT = 'raise SystemExit("ran the bridge client")\n'

    def should_export_through_the_shim_instead_of_the_bridge_client(self, source_envify, devbox_shim):
        devbox_shim.write_text('export "$1=fr0m-shim"\n')

        result = source_envify(self.BRIDGE_CLIENT)

        assert (result.returncode, result.stdout) == (0, "loaded:fr0m-shim\n")

    def should_stop_the_chain_when_the_shim_fails(self, source_envify, devbox_shim):
        devbox_shim.write_text("return 1\n")

        result = source_envify(self.BRIDGE_CLIENT)

        assert (result.returncode, result.stdout, result.stderr) == (1, "", "")

    def should_exit_with_the_shims_status_when_run_as_a_command(self, devbox_shim):
        devbox_shim.write_text('echo "listed:$1"\nreturn 3\n')

        result = subprocess.run(["bash", str(WRAPPER), "--list"], capture_output=True, text=True,
                                env={**os.environ, "ENVIFY_DEVBOX_SHIM": str(devbox_shim)})

        assert (result.returncode, result.stdout, result.stderr) == (3, "listed:--list\n", "")


class TestStoreParam:
    def should_post_the_value_as_the_request_body(self, envify, monkeypatch):
        monkeypatch.setattr(envify, "_require_host", lambda: "localhost")
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            return FakeResponse()

        monkeypatch.setattr(envify.urllib.request, "urlopen", fake_urlopen)

        envify.store_param("TELEGRAM_SESSION", "s3cret")

        request = captured["request"]
        assert request.get_method() == "POST"
        expected_url = f"http://localhost:{envify._SERVER_PORT}/TELEGRAM_SESSION"
        assert request.full_url == expected_url
        assert request.data == b"s3cret"


class TestCallerHeaders:
    @pytest.fixture
    def opened(self, envify, monkeypatch):
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(request)
            return FakeResponse()

        monkeypatch.setattr(envify.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(envify, "_require_host", lambda: "localhost")
        return requests

    @pytest.fixture
    def helper_prints(self, envify, monkeypatch):
        runs = []

        def _prints(stdout):
            def fake_run(command, **_):
                runs.append(command)
                return SimpleNamespace(returncode=0, stdout=stdout)
            monkeypatch.setattr(envify.subprocess, "run", fake_run)
            return runs
        return _prints

    def should_name_the_calling_session_on_every_server_request(self, envify, opened, helper_prints):
        helper_prints('{"session": "48f92bcb", "title": "Caf\\u00e9 \\u2013 notes"}')

        envify._server_get("localhost", "GITLAB_TOKEN")
        envify.store_param("GITLAB_TOKEN", "value")
        envify._bridge_call("localhost", "mac-trash", method="POST", data=b"/a\n")

        assert [request.get_header("X-keyguard-session") for request in opened] == ["48f92bcb"] * 3
        assert {request.get_header("X-keyguard-title") for request in opened} == {"Caf%C3%A9%20%E2%80%93%20notes"}

    def should_run_the_helper_once_per_envify_run(self, envify, opened, helper_prints):
        runs = helper_prints('{"session": "48f92bcb", "title": "t"}')

        envify._server_get("localhost", "A")
        envify._server_get("localhost", "B")

        assert runs == [[str(envify._CALLER_HELPER)]]

    @pytest.mark.parametrize("stdout", ["", "not json", "[]", '{"session": "", "title": 5}'])
    def should_send_no_caller_headers_when_the_helper_says_nothing_usable(self, envify, opened, helper_prints,
                                                                         stdout):
        helper_prints(stdout)

        envify._server_get("localhost", "GITLAB_TOKEN")

        assert not opened[0].has_header("X-keyguard-session")
        assert not opened[0].has_header("X-keyguard-title")

    def should_send_no_caller_headers_when_the_helper_cannot_run(self, envify, opened, monkeypatch):
        def missing(command, **_):
            raise FileNotFoundError(command[0])
        monkeypatch.setattr(envify.subprocess, "run", missing)

        envify._server_get("localhost", "GITLAB_TOKEN")

        assert opened[0].get_header("X-keyguard-source")
        assert not opened[0].has_header("X-keyguard-session")

    def should_find_the_helper_next_to_envify(self, envify):
        assert envify._CALLER_HELPER == WRAPPER.resolve().parent / "claude-caller"


class TestTimeouts:
    def should_wait_longer_for_a_secret_than_the_server_waits_for_touch_id(self, envify, monkeypatch):
        timeouts = []

        def fake_urlopen(request, timeout):
            timeouts.append(timeout)
            return FakeResponse()

        monkeypatch.setattr(envify.urllib.request, "urlopen", fake_urlopen)

        envify._server_get("localhost", "GITLAB_TOKEN")

        assert timeouts[0] > envify._TOUCH_ID_WAIT

    @pytest.mark.parametrize(("call", "said"), [
        (lambda envify: envify._server_get("localhost", "GITLAB_TOKEN"), "Error: server did not answer within"),
        (lambda envify: envify.store_param("GITLAB_TOKEN", "value"), "Error: server did not answer within"),
        (lambda envify: envify._bridge_call("localhost", "echo", method="POST"), "Error: bridge did not answer within"),
    ])
    def should_print_an_error_line_instead_of_a_traceback_when_the_answer_times_out(self, envify, monkeypatch, capsys,
                                                                                    call, said):
        def timed_out(request, timeout):
            raise TimeoutError("timed out")

        monkeypatch.setattr(envify.urllib.request, "urlopen", timed_out)
        monkeypatch.setattr(envify, "_require_host", lambda: "localhost")

        with pytest.raises(SystemExit) as exited:
            call(envify)

        assert exited.value.code == 1
        assert said in capsys.readouterr().err


class TestSetFlag:
    @pytest.fixture
    def stored(self, envify, monkeypatch):
        calls = []
        monkeypatch.setattr(envify, "store_param", lambda key, value: calls.append((key, value)))
        return calls

    def should_store_the_value_read_from_stdin(self, envify, stored):
        envify.set_param("NEW_TOKEN", io.StringIO("s3cret\n"))

        assert stored == [("NEW_TOKEN", "s3cret")]

    def should_keep_a_multiline_value_except_its_final_newline(self, envify, stored):
        envify.set_param("SSH_KEY", io.StringIO("line1\nline2\n"))

        assert stored == [("SSH_KEY", "line1\nline2")]

    def should_refuse_an_empty_value(self, envify, stored):
        with pytest.raises(SystemExit):
            envify.set_param("NEW_TOKEN", io.StringIO("\n"))
        assert stored == []

    @pytest.mark.parametrize("name", ["A;rm -rf ~", "../_bridge/x", "1TOKEN", "WITH SPACE", ""])
    def should_refuse_a_name_that_is_not_a_variable(self, envify, stored, name):
        with pytest.raises(SystemExit):
            envify.set_param(name, io.StringIO("value"))
        assert stored == []

    def should_parse_set_as_its_own_mode(self, envify):
        args = envify._build_parser().parse_args(["--set", "NEW_TOKEN"])

        assert args.set_key == "NEW_TOKEN"

    def should_not_combine_set_with_list(self, envify):
        with pytest.raises(SystemExit):
            envify._build_parser().parse_args(["--set", "NEW_TOKEN", "--list"])


class TestRmFlag:
    @pytest.fixture
    def runs(self, envify, monkeypatch):
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            return envify.subprocess.CompletedProcess(args, getattr(self, "status", 0))

        monkeypatch.setattr(envify.subprocess, "run", fake_run)
        return calls

    def should_remove_through_keyguard_where_it_is_installed(self, envify, runs, monkeypatch):
        monkeypatch.setattr(envify, "_keyguard_available", lambda: True)

        envify.rm_param("OLD_TOKEN")

        assert runs == [["keyguard", "rm", "OLD_TOKEN"]]

    def should_refuse_without_keyguard_since_the_bridge_cannot_delete(self, envify, runs, monkeypatch):
        monkeypatch.setattr(envify, "_keyguard_available", lambda: False)
        with pytest.raises(SystemExit):
            envify.rm_param("OLD_TOKEN")
        assert runs == []

    def should_refuse_a_name_that_is_not_a_variable(self, envify, runs, monkeypatch):
        monkeypatch.setattr(envify, "_keyguard_available", lambda: True)
        with pytest.raises(SystemExit):
            envify.rm_param("../_bridge/x")
        assert runs == []

    def should_exit_with_keyguards_status_when_the_removal_fails(self, envify, runs, monkeypatch):
        monkeypatch.setattr(envify, "_keyguard_available", lambda: True)
        self.status = 1
        with pytest.raises(SystemExit) as exited:
            envify.rm_param("OLD_TOKEN")
        assert exited.value.code == 1

    def should_parse_rm_as_its_own_mode(self, envify):
        assert envify._build_parser().parse_args(["--rm", "OLD_TOKEN"]).rm_key == "OLD_TOKEN"

    def should_not_combine_rm_with_set(self, envify):
        with pytest.raises(SystemExit):
            envify._build_parser().parse_args(["--rm", "OLD_TOKEN", "--set", "NEW_TOKEN"])



class TestBridge:
    @pytest.fixture
    def opened(self, envify, monkeypatch):
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(request)
            return FakeResponse()

        monkeypatch.setattr(envify.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(envify, "_require_host", lambda: "localhost")
        return requests

    def should_send_the_body_with_the_bridge_request(self, envify, opened):
        envify._bridge_call("localhost", "mac-trash", method="POST", data=b"/a\n")

        assert (opened[0].get_method(), opened[0].data) == ("POST", b"/a\n")

    def should_call_an_endpoint_in_one_request_without_a_token(self, envify, opened):
        envify.call_bridge_endpoint("mac-trash", b"/a\n")

        assert [request.full_url for request in opened] == ["http://localhost:7777/_bridge/mac-trash"]
        assert not opened[0].has_header("Authorization")

    @pytest.mark.parametrize("include_private, path", [(False, "list"), (True, "list?all=1")])
    def should_ask_for_private_endpoints_only_with_all(self, envify, opened, include_private, path):
        envify.list_bridge_endpoints(include_private=include_private)

        assert opened[0].full_url == f"http://localhost:7777/_bridge/{path}"

    def should_wait_while_another_bridge_prompt_is_open(self, envify, monkeypatch):
        answers = [http_error(envify, 429), FakeResponse()]
        monkeypatch.setattr(envify.urllib.request, "urlopen", lambda request, timeout: raise_or_return(answers.pop(0)))
        monkeypatch.setattr(envify, "time", SimpleNamespace(monotonic=lambda: 0.0, sleep=lambda seconds: None))

        assert envify._bridge_call("localhost", "echo", method="POST") == "stored"
        assert answers == []

    def should_give_up_once_the_prompt_wait_is_over(self, envify, monkeypatch, capsys):
        clock = iter([0.0, envify._TOUCH_ID_WAIT + 1.0])
        monkeypatch.setattr(envify.urllib.request, "urlopen", lambda request, timeout: raise_or_return(http_error(envify, 429)))
        monkeypatch.setattr(envify, "time", SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda seconds: None))

        with pytest.raises(SystemExit):
            envify._bridge_call("localhost", "echo", method="POST")

        assert "bridge returned 429" in capsys.readouterr().err

    def should_not_retry_a_denied_prompt(self, envify, monkeypatch, capsys):
        calls = []
        monkeypatch.setattr(envify.urllib.request, "urlopen",
                            lambda request, timeout: calls.append(request) or raise_or_return(http_error(envify, 403)))

        with pytest.raises(SystemExit):
            envify._bridge_call("localhost", "echo", method="POST")

        assert len(calls) == 1
        assert "bridge returned 403: denied" in capsys.readouterr().err

    def should_refuse_stdin_without_a_bridge_endpoint(self, envify, monkeypatch):
        monkeypatch.setattr(envify, "_load_global_env", lambda: None)

        with pytest.raises(SystemExit) as exit_info:
            envify.main(["--stdin"])

        assert exit_info.value.code == 2
