import io
import os
from types import SimpleNamespace

import pytest


@pytest.fixture
def envify(load_script):
    return load_script("envify.py")


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
