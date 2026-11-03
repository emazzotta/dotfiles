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
def notify(load_script, tmp_path, monkeypatch):
    module = load_script("claude-notify")
    monkeypatch.setattr(module, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(module, "DEVBOX_TOKEN_FILE", tmp_path / "no-token")
    monkeypatch.setattr(module, "IS_MAC", False)
    monkeypatch.setattr(module.socket, "gethostname", lambda: "f635a28c3a2e")
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
    return module


@pytest.fixture
def spawned(notify, monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "spawn", lambda arguments, payload=None: calls.append((list(arguments), payload)))
    return calls


@pytest.fixture
def delivered(notify, monkeypatch):
    bodies = []
    monkeypatch.setattr(notify, "deliver", lambda body: bodies.append(json.loads(body)) or 0)
    return bodies


def _hook(notify, event_name, **fields):
    notify.handle_hook(json.dumps({"session_id": str(SESSION), "hook_event_name": event_name, **fields}))


def _armed_token(spawned):
    (arguments, _), = spawned
    assert arguments[:2] == ["fire", str(SESSION)]
    return arguments[2]


class TestFirstSentence:
    @pytest.mark.parametrize("message, expected", [
        ("Emanuele, done: pushed 2 commits. The pipeline is green.", "Done: pushed 2 commits."),
        ("Emanuele, 2026-11-03 02:10 CET (session 4a01, container f635): ready to push?", "Ready to push?"),
        ("**Waiting** for your `OK` on [MR !42](https://example.com/42).", "Waiting for your OK on MR !42."),
        ("\n\n## Summary\n- first point\n- second point", "Summary"),
        ("1. Ship it", "Ship it"),
    ])
    def should_take_the_first_sentence_without_canary_or_markdown(self, notify, message, expected):
        assert notify.first_sentence(message) == expected

    @pytest.mark.parametrize("message", ["", "Emanuele, ", "  \n  "])
    def should_fall_back_when_the_reply_has_no_text(self, notify, message):
        assert notify.first_sentence(message) == notify.FINISHED_FALLBACK

    def should_cap_a_long_sentence_with_an_ellipsis(self, notify):
        sentence = notify.first_sentence("word " * 100)

        assert len(sentence) == notify.SENTENCE_LIMIT
        assert sentence.endswith("\u2026")


class TestPromptSentence:
    @pytest.mark.parametrize("tool_name, tool_input, expected", [
        ("AskUserQuestion", {"questions": [{"question": "Tea or coffee?"}]}, "Asks: Tea or coffee?"),
        ("ExitPlanMode", {"plan": "..."}, "Has a plan ready for your approval."),
        ("Bash", {"command": "git push", "description": "Push the branch"}, "Needs your OK to run: Push the branch"),
        ("Bash", {"command": "git push"}, "Needs your OK to run: git push"),
        ("mcp__playwright__browser_click", {}, "Needs your OK for mcp__playwright__browser_click."),
    ])
    def should_say_what_the_prompt_is_about(self, notify, tool_name, tool_input, expected):
        assert notify.prompt_sentence(tool_name, tool_input) == expected


class TestFinishedPing:
    def should_arm_a_ping_with_the_first_sentence_when_claude_stops(self, notify, spawned, delivered):
        _hook(notify, "Stop", last_assistant_message="Emanuele, done. Details follow.", background_tasks=[])

        assert notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: None) == 0
        assert delivered == [{"session": str(SESSION), "container": "f635a28c3a2e", "text": "Done."}]

    def should_wait_the_finished_delay_before_sending(self, notify, spawned, delivered):
        _hook(notify, "Stop", last_assistant_message="Done.")
        waited = []

        notify.fire(SESSION, _armed_token(spawned), sleep=waited.append)

        assert waited == [10.0]

    def should_not_ping_when_a_prompt_was_submitted_in_time(self, notify, spawned, delivered):
        _hook(notify, "Stop", last_assistant_message="Done.")
        _hook(notify, "UserPromptSubmit", prompt="next")

        notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: None)

        assert delivered == []

    def should_let_only_the_latest_stop_ping(self, notify, spawned, delivered):
        _hook(notify, "Stop", last_assistant_message="First.")
        _hook(notify, "Stop", last_assistant_message="Second.")
        (first, _), (second, _) = spawned

        notify.fire(SESSION, first[2], sleep=lambda seconds: None)
        assert delivered == []

        notify.fire(SESSION, second[2], sleep=lambda seconds: None)
        assert [body["text"] for body in delivered] == ["Second."]

    @pytest.mark.parametrize("task_type", ["subagent", "workflow", "monitor"])
    def should_stay_quiet_while_background_work_will_wake_claude(self, notify, spawned, delivered, task_type):
        _hook(notify, "Stop", last_assistant_message="First.")
        token = _armed_token(spawned)

        _hook(notify, "Stop", last_assistant_message="Waiting on agents.", background_tasks=[{"type": task_type}])
        notify.fire(SESSION, token, sleep=lambda seconds: None)

        assert len(spawned) == 1
        assert delivered == []

    def should_still_ping_when_only_a_background_shell_runs(self, notify, spawned):
        _hook(notify, "Stop", last_assistant_message="Done.", background_tasks=[{"type": "shell"}])

        assert _armed_token(spawned)

    def should_never_ping_for_an_unattended_run(self, notify, spawned, monkeypatch):
        monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "sdk-cli")

        _hook(notify, "Stop", last_assistant_message="Done.")

        assert spawned == []


class TestPromptPing:
    def should_send_the_noted_prompt_when_claude_code_reports_it_unanswered(self, notify, spawned):
        _hook(notify, "PermissionRequest", tool_name="ExitPlanMode", tool_input={})
        _hook(notify, "Notification", notification_type="permission_prompt",
              message="Claude Code needs your approval for the plan")

        (arguments, payload), = spawned
        assert arguments == ["send"]
        assert json.loads(payload)["text"] == "Has a plan ready for your approval."

    def should_fall_back_to_the_notification_message(self, notify, spawned):
        _hook(notify, "Notification", notification_type="permission_prompt", message="Claude needs your permission")

        (_, payload), = spawned
        assert json.loads(payload)["text"] == "Claude needs your permission"

    def should_not_reuse_a_prompt_note_after_a_new_prompt_was_submitted(self, notify, spawned):
        _hook(notify, "PermissionRequest", tool_name="Bash", tool_input={"command": "git push"})
        _hook(notify, "UserPromptSubmit", prompt="no, wait")
        _hook(notify, "Notification", notification_type="permission_prompt", message="Claude needs your permission")

        (_, payload), = spawned
        assert json.loads(payload)["text"] == "Claude needs your permission"

    @pytest.mark.parametrize("notification_type", ["idle_prompt", "auth_success"])
    def should_ignore_other_notifications(self, notify, spawned, notification_type):
        _hook(notify, "Notification", notification_type=notification_type, message="x")

        assert spawned == []


class TestDelivery:
    def should_use_the_bridge_from_a_container(self, notify, monkeypatch):
        runs = []
        monkeypatch.setattr(notify.subprocess, "run",
                            lambda command, **kwargs: runs.append((command, kwargs["input"])) or
                            type("Done", (), {"returncode": 0})())

        assert notify.deliver('{"text": "x"}') == 0
        assert runs == [(["envify", "--bridge", "claude-notify", "--stdin"], '{"text": "x"}')]

    def should_use_the_box_token_on_the_dev_box(self, notify, monkeypatch, tmp_path):
        token_file = tmp_path / "request-token"
        token_file.write_text("box-token\n")
        monkeypatch.setattr(notify, "DEVBOX_TOKEN_FILE", token_file)
        posts = []
        monkeypatch.setattr(notify, "post_to_store", lambda body, bearer: posts.append(bearer) or 0)

        notify.deliver("{}")

        assert posts == ["box-token"]

    def should_rely_on_the_tailnet_identity_on_the_mac(self, notify, monkeypatch):
        monkeypatch.setattr(notify, "IS_MAC", True)
        posts = []
        monkeypatch.setattr(notify, "post_to_store", lambda body, bearer: posts.append(bearer) or 0)

        notify.deliver("{}")

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
    def should_post_the_notice_as_json_with_the_bearer(self, notify, store):
        assert notify.post_to_store('{"text": "x"}', "box-token") == 0

        (path, headers, body), = store.received
        assert path == "/notify"
        assert headers["Content-Type"] == "application/json"
        assert headers["Authorization"] == "Bearer box-token"
        assert body == b'{"text": "x"}'

    def should_report_a_refusal_without_the_token(self, notify, store, monkeypatch):
        monkeypatch.setattr(store, "status", 403)
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            result = notify.post_to_store("{}", "box-token")

        assert result == 1
        assert "HTTP 403" in stderr.getvalue()
        assert "box-token" not in stderr.getvalue()


class TestMain:
    def should_never_fail_the_hook_on_bad_input(self, notify, monkeypatch):
        monkeypatch.setattr(notify.sys, "stdin", io.StringIO("{not json"))

        with redirect_stderr(io.StringIO()):
            assert notify.main([]) == 0

    def should_reject_unknown_arguments(self, notify):
        with redirect_stderr(io.StringIO()):
            assert notify.main(["bogus"]) == 2
