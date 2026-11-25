import io
import json
import threading
from contextlib import redirect_stderr
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar
from uuid import UUID

import pytest

SESSION = UUID("4a015f0f-199b-4270-9c06-fecc5d85b976")


@pytest.fixture
def delivery(load_module, tmp_path, monkeypatch):
    notify_delivery = load_module("notify_delivery")
    monkeypatch.setattr(notify_delivery, "DEVBOX_TOKEN_FILE", tmp_path / "no-token")
    monkeypatch.setattr(notify_delivery, "IS_MAC", False)
    monkeypatch.setattr(notify_delivery.socket, "gethostname", lambda: "f635a28c3a2e")
    monkeypatch.setenv("CLAUDE_PROJECTS", str(tmp_path / "projects"))
    return notify_delivery


class TestSend:
    def should_send_the_notice_of_the_session_with_its_kind(self, delivery, monkeypatch):
        bodies = []
        monkeypatch.setattr(delivery, "deliver", lambda body: bodies.append(body) or 0)

        delivery.send(SESSION, "Master: Tests fail", delivery.PingKind.PROMPT)

        assert [json.loads(body) for body in bodies] == [{"session": str(SESSION), "container": "f635a28c3a2e", "title": None,
                                                          "text": "Master: Tests fail", "kind": "prompt"}]


class TestDelivery:
    def should_use_the_bridge_from_a_container(self, delivery, monkeypatch):
        runs = []
        monkeypatch.setattr(delivery.subprocess, "run",
                            lambda command, **kwargs: runs.append((command, kwargs["input"])) or
                            type("Done", (), {"returncode": 0})())

        assert delivery.deliver('{"text": "x"}') == 0
        assert runs == [(["envify", "--bridge", "claude-notify", "--stdin"], '{"text": "x"}')]

    def should_use_the_box_token_on_the_dev_box(self, delivery, monkeypatch, tmp_path):
        token_file = tmp_path / "request-token"
        token_file.write_text("box-token\n")
        monkeypatch.setattr(delivery, "DEVBOX_TOKEN_FILE", token_file)
        posts = []
        monkeypatch.setattr(delivery, "post_to_store", lambda body, bearer: posts.append(bearer) or 0)

        delivery.deliver("{}")

        assert posts == ["box-token"]

    def should_rely_on_the_tailnet_identity_on_the_mac(self, delivery, monkeypatch):
        monkeypatch.setattr(delivery, "IS_MAC", True)
        posts = []
        monkeypatch.setattr(delivery, "post_to_store", lambda body, bearer: posts.append(bearer) or 0)

        delivery.deliver("{}")

        assert posts == [None]


class _Recorder(BaseHTTPRequestHandler):
    status = 202
    received: ClassVar[list] = []

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        self.received.append((self.path, dict(self.headers), self.rfile.read(length)))
        self.send_response(self.status)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def store(monkeypatch):
    _Recorder.received = []
    server = HTTPServer(("127.0.0.1", 0), _Recorder)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("KEYGUARD_STORE_URL", f"http://127.0.0.1:{server.server_address[1]}")
    yield _Recorder
    server.shutdown()


class TestPostToStore:
    def should_post_the_notice_as_json_with_the_bearer(self, delivery, store):
        assert delivery.post_to_store('{"text": "x"}', "box-token") == 0

        (path, headers, body), = store.received
        assert path == "/notify"
        assert headers["Content-Type"] == "application/json"
        assert headers["Authorization"] == "Bearer box-token"
        assert body == b'{"text": "x"}'

    def should_report_a_refusal_without_the_token(self, delivery, store, monkeypatch):
        monkeypatch.setattr(store, "status", 403)
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            result = delivery.post_to_store("{}", "box-token")

        assert result == 1
        assert "HTTP 403" in stderr.getvalue()
        assert "box-token" not in stderr.getvalue()
