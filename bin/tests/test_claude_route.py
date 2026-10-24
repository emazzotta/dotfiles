import json
import subprocess
import sys

import pytest


@pytest.fixture
def route(load_script):
    return load_script("claude-route")


def classifier_output(reply: str) -> str:
    return json.dumps({"result": reply})


class TestParseRoute:
    def should_read_the_suggested_model_and_effort(self, route):
        parsed = route.parse_route(classifier_output('{"model": "sonnet", "effort": "low"}'))
        assert parsed == route.Route("sonnet", "low")

    def should_read_a_reply_wrapped_in_a_code_fence(self, route):
        parsed = route.parse_route(classifier_output('```json\n{"model": "opus", "effort": "high"}\n```'))
        assert parsed == route.Route("opus", "high")

    @pytest.mark.parametrize("output", [
        classifier_output('{"model": "gpt", "effort": "low"}'),
        classifier_output('{"model": "opus", "effort": "extreme"}'),
        classifier_output("no idea"),
        "not json",
        json.dumps({"error": "rate limited"}),
    ])
    def should_give_no_suggestion_for_an_unusable_reply(self, route, output):
        assert route.parse_route(output) is None


class TestRouteArgs:
    @pytest.fixture
    def on_a_terminal(self, route, monkeypatch):
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.setattr(route.shutil, "which", lambda _name: "/usr/bin/gum")
        monkeypatch.setattr(route, "classify", lambda _prompt: route.Route("sonnet", "low"))

    def answer(self, route, monkeypatch, returncode):
        monkeypatch.setattr(route, "run", lambda *_a, **_k: subprocess.CompletedProcess([], returncode))

    def should_apply_the_suggestion_when_confirmed(self, route, monkeypatch, on_a_terminal):
        self.answer(route, monkeypatch, 0)
        assert route.route_args("fix it") == ["--model", "sonnet", "--effort", "low"]

    def should_keep_the_defaults_when_declined(self, route, monkeypatch, on_a_terminal):
        self.answer(route, monkeypatch, 1)
        assert route.route_args("fix it") == []

    def should_exit_when_the_question_is_cancelled(self, route, monkeypatch, on_a_terminal):
        self.answer(route, monkeypatch, 130)
        with pytest.raises(SystemExit, match="130"):
            route.route_args("fix it")

    def should_keep_the_defaults_without_asking_when_classification_fails(self, route, monkeypatch, on_a_terminal):
        monkeypatch.setattr(route, "classify", lambda _prompt: None)
        monkeypatch.setattr(route, "run", lambda *_a, **_k: pytest.fail("asked without a suggestion"))
        assert route.route_args("fix it") == []

    def should_keep_the_defaults_without_classifying_when_not_on_a_terminal(self, route, monkeypatch):
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(route, "classify", lambda _prompt: pytest.fail("classified without a terminal"))
        assert route.route_args("fix it") == []


class TestMain:
    def should_start_claude_with_the_route_ahead_of_the_forwarded_args(self, route, monkeypatch):
        monkeypatch.setattr(route, "route_args", lambda _prompt: ["--model", "opus", "--effort", "high"])
        execs = []
        monkeypatch.setattr(route.os, "execvp", lambda file, argv: execs.append((file, argv)))
        monkeypatch.setattr(sys, "argv", ["claude-route", "--session-id", "abc", "fix it"])
        route.main()
        assert execs == [("claude", ["claude", "--model", "opus", "--effort", "high", "--session-id", "abc", "fix it"])]

    def should_refuse_to_start_without_a_prompt(self, route, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["claude-route"])
        with pytest.raises(SystemExit, match="2"):
            route.main()
