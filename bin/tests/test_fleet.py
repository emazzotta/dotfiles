from __future__ import annotations

import json

import pytest

CLAUDE = "aaaaaaaa-0000-4000-8000-000000000001"
QUESTION = {"id": "toolu_01", "questions": [{"question": "Which database?", "header": "DB", "multiSelect": False,
                                             "options": [{"label": "Postgres", "description": ""}, {"label": "SQLite", "description": ""}]}]}


def session(**over):
    return {"conversation": CLAUDE, "short": "aaaaaaaa", "title": "Fix the login form", "cwd": "/workspace/code/app",
            "box": "mac", "pane": "%3", "agent": "claude", "status": "idle", "question": None, **over}


@pytest.fixture
def fleet(load_script):
    return load_script("fleet")


@pytest.fixture
def stub(fleet):
    class StubApi(fleet.Api):
        def __init__(self, answers):
            super().__init__("http://terminal.test", "token")
            self.answers = answers
            self.calls = []

        def call(self, method, path, body=None, timeout=fleet.REQUEST_TIMEOUT_S):
            self.calls.append((method, path, body))
            status, answer = self.answers[(method, path.split("?")[0])]
            return fleet.Answer(status, answer)

    return StubApi


class TestTerminalUrl:
    @pytest.mark.parametrize("environ,in_container,expected", [
        ({}, False, "http://localhost:8122"),
        ({}, True, "http://host.docker.internal:8122"),
        ({"WEB_TERMINAL_URL": "https://terminal.test/"}, True, "https://terminal.test"),
    ])
    def should_take_the_configured_url_else_the_local_terminal(self, fleet, environ, in_container, expected):
        assert fleet.terminal_url(environ, in_container) == expected


class TestState:
    @pytest.mark.parametrize("over,expected", [
        ({"status": "busy"}, "busy"),
        ({"status": "idle"}, "idle"),
        ({"status": "waiting", "question": QUESTION}, "asks"),
        ({"status": "waiting"}, "waits-for-owner"),
    ])
    def should_tell_a_question_apart_from_a_prompt_only_the_owner_answers(self, fleet, over, expected):
        assert fleet.state_of(session(**over)) == expected


class TestChanges:
    def should_report_started_ended_and_changed_sessions_only(self, fleet):
        other = session(conversation="b", short="bbbbbbbb", title="Other")
        gone = session(conversation="c", short="cccccccc", title="Gone")
        before = fleet.snapshot([session(status="busy"), other, gone])
        new = session(conversation="d", short="dddddddd", title="New")

        lines = fleet.changes(before, fleet.snapshot([session(status="idle"), other, new]))

        assert lines == [
            "+ dddddddd  claude@mac  idle  New  [/workspace/code/app]",
            "- cccccccc  claude@mac  idle  Gone  [/workspace/code/app]",
            "busy -> aaaaaaaa  claude@mac  idle  Fix the login form  [/workspace/code/app]",
        ]


class TestMain:
    def should_list_each_session_with_the_questions_it_asks(self, fleet, stub, capsys):
        api = stub({("GET", "/sessions"): (200, {"sessions": [session(status="waiting", question=QUESTION)], "offline": ["devbox"]})})

        code = fleet.main(["ls"], lambda: api)

        assert (code, capsys.readouterr().out.splitlines()) == (0, [
            "aaaaaaaa  claude@mac  asks  Fix the login form  [/workspace/code/app]",
            "  Q1 (one): Which database?  options: Postgres, SQLite",
            "could not read: devbox",
        ])

    def should_answer_with_the_question_id_the_session_lists(self, fleet, stub):
        api = stub({
            ("GET", "/sessions"): (200, {"sessions": [session(status="waiting", question=QUESTION)], "offline": []}),
            ("POST", f"/sessions/{CLAUDE}/answer"): (200, {"ok": True, **session()}),
        })

        code = fleet.main(["answer", "aaaaaaaa", "SQLite"], lambda: api)

        assert (code, api.calls[-1]) == (0, ("POST", f"/sessions/{CLAUDE}/answer", {"question": "toolu_01", "answers": [["SQLite"]]}))

    def should_take_the_answers_to_several_questions_as_json(self, fleet, stub):
        api = stub({
            ("GET", "/sessions"): (200, {"sessions": [session(status="waiting", question=QUESTION)], "offline": []}),
            ("POST", f"/sessions/{CLAUDE}/answer"): (200, {"ok": True, **session()}),
        })

        fleet.main(["answer", CLAUDE, "--answers-json", json.dumps([["Postgres"], ["Small", "Large"]])], lambda: api)

        assert api.calls[-1][2]["answers"] == [["Postgres"], ["Small", "Large"]]

    def should_refuse_to_answer_a_session_that_waits_at_a_prompt(self, fleet, stub, capsys):
        api = stub({("GET", "/sessions"): (200, {"sessions": [session(status="waiting")], "offline": []})})

        code = fleet.main(["answer", "aaaaaaaa", "Yes"], lambda: api)

        assert (code, len(api.calls), capsys.readouterr().err) == (3, 1, "refused: aaaaaaaa asks no question (waits-for-owner)\n")

    def should_exit_3_when_the_terminal_refuses_a_message_to_a_waiting_agent(self, fleet, stub, capsys):
        api = stub({("POST", "/sessions/aaaaaaaa/input"): (409, {"error": "The agent waits for an answer, which a message would give."})})

        code = fleet.main(["send", "aaaaaaaa", "go on"], lambda: api)

        assert (code, capsys.readouterr().err) == (3, "refused: The agent waits for an answer, which a message would give.\n")

    def should_escape_a_pane_in_the_path(self, fleet, stub, capsys):
        api = stub({("GET", "/sessions/devbox%3A%254/last-reply"): (200, {"text": "Tests pass.", **session(status="idle")})})

        code = fleet.main(["reply", "devbox:%4"], lambda: api)

        assert (code, capsys.readouterr().out.splitlines()[-1]) == (0, "Tests pass.")

    def should_start_an_agent_and_print_its_first_reply_when_asked_to_wait(self, fleet, stub, capsys):
        api = stub({
            ("POST", "/sessions"): (201, {"window": "@5", "pane": "%12", "box": "mac", "session": "main"}),
            ("GET", "/sessions/%2512/first-reply"): (200, {"text": "On it.", **session(pane="%12", status="busy")}),
        })

        code = fleet.main(["start", "mac", "claude", "Fix the form", "--effort", "high", "--wait"], lambda: api)

        assert (code, api.calls[0][2], capsys.readouterr().out.splitlines()[-1]) == (
            0, {"box": "mac", "agent": "claude", "prompt": "Fix the form", "effort": "high"}, "On it.")

    def should_fail_with_the_reason_the_terminal_gives(self, fleet, stub, capsys):
        api = stub({("GET", "/boxes"): (401, {"error": "Send the automation token as a bearer."})})

        code = fleet.main(["boxes"], lambda: api)

        assert (code, capsys.readouterr().err) == (1, "fleet: 401: Send the automation token as a bearer.\n")


class TestCli:
    def should_print_its_usage_without_loading_the_token(self, run_cli):
        result = run_cli("fleet", ["--help"], env_extra={"TELEGRAM_BOT_WEB_TERMINAL_AUTOMATION_TOKEN": ""})

        assert (result.returncode, "watch" in result.stdout, "envify" in result.stderr) == (0, True, False)
