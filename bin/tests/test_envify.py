import io
import os

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

