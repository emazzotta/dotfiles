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
            self.timeouts = []

        def call(self, method, path, body=None, timeout=fleet.REQUEST_TIMEOUT_S):
            self.calls.append((method, path, body))
            self.timeouts.append(timeout)
            answer = self.answers[(method, path.split("?")[0])]
            status, body = answer.pop(0) if isinstance(answer, list) else answer
            return fleet.Answer(status, body)

    return StubApi


class TestTerminalUrl:
    @pytest.mark.parametrize("environ,markers,expected", [
        ({}, set(), "http://localhost:8122"),
        ({}, {"/.dockerenv"}, "http://host.docker.internal:8122"),
        ({}, {"/opt/unlock", "/.dockerenv"}, "https://terminal.mazzotta.me"),
        ({"WEB_TERMINAL_URL": "https://terminal.test/"}, {"/opt/unlock"}, "https://terminal.test"),
    ])
    def should_take_the_configured_url_else_the_terminal_of_this_runtime(self, fleet, environ, markers, expected):
        assert fleet.terminal_url(environ, lambda path: str(path) in markers) == expected


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


class TestDescribe:
    def should_show_the_master_mark_the_cue_and_the_flag_when_the_terminal_lists_them(self, fleet):
        line = fleet.describe(session(master=True, cue="master", flag="Tests fail"))

        assert line == "aaaaaaaa  claude@mac  idle  Fix the login form  [/workspace/code/app]  master  cue:master  flag: Tests fail"


OTHER = "bbbbbbbb-0000-4000-8000-000000000002"
MASTER = "cccccccc-0000-4000-8000-000000000003"


@pytest.fixture
def watching(fleet, stub):
    class Clock:
        now = 0.0

        def __call__(self):
            return self.now

    def _watch(*looks, replies=None):
        listed = iter([*looks[:-1], *[looks[-1]] * 10])
        alerts = []
        api = stub({("GET", f"/sessions/{key}/last-reply"): (200, {"text": text}) for key, text in (replies or {}).items()})
        api.call = _listing(api, listed)
        clock = Clock()
        watcher = fleet.Watcher(api, MASTER, fleet.Limits(20 * 60, 10 * 60), lambda title, flag: alerts.append((title, flag)) or True, clock)
        return watcher, clock, alerts

    def _listing(api, listed):
        answer = api.call

        def call(method, path, body=None, timeout=fleet.REQUEST_TIMEOUT_S):
            if path == "/sessions":
                return fleet.Answer(200, {"sessions": next(listed), "offline": []})
            return answer(method, path, body, timeout)
        return call

    return _watch


class TestWatcher:
    def should_leave_the_master_session_out(self, watching):
        watcher, _, _ = watching([session(), session(conversation=MASTER, short="cccccccc")])

        assert watcher.start() == 1

    def should_report_a_session_busy_past_the_limit_once_with_its_last_reply(self, watching):
        busy = session(status="busy")
        watcher, clock, _ = watching([busy], [busy], [busy], replies={CLAUDE: "Running the\nmigration."})
        watcher.start()

        clock.now = 19 * 60
        early = watcher.look()
        clock.now = 21 * 60
        late = watcher.look()
        clock.now = 30 * 60

        assert (early, late, watcher.look()) == ([], [
            "stuck aaaaaaaa  claude@mac  busy  Fix the login form  [/workspace/code/app]  busy 21 min",
            "  last reply: Running the migration.",
        ], [])

    def should_say_so_when_a_stuck_session_has_no_reply_to_judge_from(self, watching):
        busy = session(status="busy")
        watcher, clock, _ = watching([busy], [busy], replies={CLAUDE: None})
        watcher.start()
        clock.now = 20 * 60

        assert watcher.look()[-1] == "  last reply: (none to judge from)"

    def should_count_busy_time_anew_after_a_session_rests(self, watching):
        busy, idle = session(status="busy"), session(status="idle")
        watcher, clock, _ = watching([busy], [idle], [busy], [busy], replies={CLAUDE: "Done."})
        watcher.start()
        clock.now = 15 * 60
        watcher.look()
        clock.now = 16 * 60
        watcher.look()
        clock.now = 30 * 60

        assert watcher.look() == []

    def should_print_the_reply_of_a_session_that_turns_idle(self, watching):
        watcher, _, _ = watching([session(status="busy")], [session(status="idle")], replies={CLAUDE: "Tests pass."})
        watcher.start()

        assert watcher.look() == [
            "busy -> aaaaaaaa  claude@mac  idle  Fix the login form  [/workspace/code/app]",
            "  reply: Tests pass.",
        ]

    def should_send_a_flag_the_owner_left_unseen_to_telegram_once(self, watching):
        flagged = session(flag="Tests fail", cue="master")
        watcher, clock, alerts = watching([flagged], [flagged], [flagged])
        watcher.start()
        clock.now = 9 * 60
        early = watcher.look()
        clock.now = 10 * 60

        assert (early, watcher.look(), watcher.look(), alerts) == (
            [], ["telegram aaaaaaaa: Tests fail"], [], [("Fix the login form", "Tests fail")])

    def should_not_send_a_flag_the_owner_saw(self, watching):
        flagged = session(flag="Tests fail", cue="master")
        watcher, clock, alerts = watching([flagged], [session()], [flagged])
        watcher.start()
        clock.now = 5 * 60
        watcher.look()
        clock.now = 12 * 60

        assert (watcher.look(), alerts) == ([], [])

    def should_not_send_a_flag_whose_window_waits_for_an_answer(self, watching):
        waiting = session(status="waiting", flag="Tests fail", cue="waiting")
        watcher, clock, alerts = watching([waiting], [waiting])
        watcher.start()
        clock.now = 60 * 60

        assert (watcher.look(), alerts) == ([], [])


class TestTelegramAlert:
    def should_send_the_flag_as_a_prompt_of_the_master_so_a_reply_reaches_it(self, fleet, monkeypatch):
        sent = []
        monkeypatch.setattr(fleet.notify_delivery, "send", lambda session, text, kind: sent.append((str(session), text, kind.value)) or 0)

        assert fleet.telegram_alert(MASTER)("Fix the login form", "Tests fail") is True
        assert sent == [(MASTER, "Master: Fix the login form: Tests fail", "prompt")]

    def should_send_nothing_for_a_master_that_is_no_claude_conversation(self, fleet, monkeypatch):
        sent = []
        monkeypatch.setattr(fleet.notify_delivery, "send", lambda *args: sent.append(args) or 0)

        assert (fleet.telegram_alert("ses_opencode")("x", "y"), fleet.telegram_alert(None)("x", "y"), sent) == (False, False, [])


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

    def should_flag_a_session_with_the_words_given(self, fleet, stub, capsys):
        api = stub({("POST", "/sessions/aaaaaaaa/flag"): (200, {"ok": True, **session(flag="Tests fail", cue="master")})})

        code = fleet.main(["flag", "aaaaaaaa", "Tests fail"], lambda: api)

        assert (code, api.calls[0][2], capsys.readouterr().out) == (
            0, {"text": "Tests fail"}, "flagged aaaaaaaa  claude@mac  idle  Fix the login form  [/workspace/code/app]  cue:master  flag: Tests fail\n")

    def should_mark_its_own_session_as_the_master_for_the_terminal_and_claude_notify(self, fleet, stub, monkeypatch, tmp_path):
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", MASTER)
        monkeypatch.setattr(fleet.master_session, "MARK_DIR", tmp_path / "master")
        api = stub({("POST", f"/sessions/{MASTER}/master"): (200, {"ok": True, **session(conversation=MASTER, short="cccccccc", master=True)})})

        code = fleet.main(["master", "on"], lambda: api)

        assert (code, api.calls[0][2], fleet.master_session.is_master(fleet.uuid.UUID(MASTER))) == (0, {"on": True}, True)

    def should_ask_for_the_session_when_it_cannot_tell_its_own(self, fleet, stub, monkeypatch, capsys):
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)

        code = fleet.main(["master", "on"], lambda: stub({}))

        assert (code, capsys.readouterr().err) == (1, "fleet: name the session with --session: CLAUDE_CODE_SESSION_ID is not set\n")

    def should_close_a_session_by_its_conversation_and_say_how_its_agent_ended(self, fleet, stub, monkeypatch, capsys):
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", MASTER)
        api = stub({
            ("GET", "/sessions"): (200, {"sessions": [session()], "offline": []}),
            ("DELETE", f"/sessions/{CLAUDE}"): (200, {"ok": True, "ended": "exit", **session()}),
        })

        code = fleet.main(["close", "aaaaaaaa"], lambda: api)

        assert (code, api.calls[-1], capsys.readouterr().out) == (
            0, ("DELETE", f"/sessions/{CLAUDE}", None), "closed aaaaaaaa  claude@mac  idle  Fix the login form  [/workspace/code/app]  (exit)\n")

    def should_wait_for_the_close_longer_than_the_terminal_waits_for_the_agent(self, fleet, stub):
        api = stub({
            ("GET", "/sessions"): (200, {"sessions": [session()], "offline": []}),
            ("DELETE", f"/sessions/{CLAUDE}"): (200, {"ok": True, "ended": "exit", **session()}),
        })

        fleet.main(["close", "aaaaaaaa"], lambda: api)

        assert api.timeouts[-1] > fleet.CLOSE_WAIT_S

    def should_ask_the_terminal_to_force_the_close_only_when_told_to(self, fleet, stub):
        api = stub({
            ("GET", "/sessions"): (200, {"sessions": [session(status="busy")], "offline": []}),
            ("DELETE", f"/sessions/{CLAUDE}"): (200, {"ok": True, "ended": "hangup", **session(status="busy")}),
        })

        fleet.main(["close", "aaaaaaaa", "--force"], lambda: api)

        assert api.calls[-1][1] == f"/sessions/{CLAUDE}?force=true"

    def should_exit_3_when_the_terminal_refuses_to_close_a_busy_session(self, fleet, stub, capsys):
        api = stub({
            ("GET", "/sessions"): (200, {"sessions": [session(status="busy")], "offline": []}),
            ("DELETE", f"/sessions/{CLAUDE}"): (409, {"error": "The agent is busy.", **session(status="busy")}),
        })

        code = fleet.main(["close", "aaaaaaaa"], lambda: api)

        assert (code, capsys.readouterr().err) == (3, "refused: The agent is busy.\n")

    def should_refuse_to_close_its_own_session_even_with_force(self, fleet, stub, monkeypatch, capsys):
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", CLAUDE)
        api = stub({("GET", "/sessions"): (200, {"sessions": [session()], "offline": []})})

        code = fleet.main(["close", "aaaaaaaa", "--force"], lambda: api)

        assert (code, len(api.calls), capsys.readouterr().err) == (3, 1, "refused: aaaaaaaa is this session\n")

    def should_fail_with_the_reason_the_terminal_gives(self, fleet, stub, capsys):
        api = stub({("GET", "/boxes"): (401, {"error": "Send the automation token as a bearer."})})

        code = fleet.main(["boxes"], lambda: api)

        assert (code, capsys.readouterr().err) == (1, "fleet: 401: Send the automation token as a bearer.\n")


OWNER_INPUT = f"/sessions/{CLAUDE}/owner-input"


@pytest.fixture
def signer(fleet, monkeypatch):
    asked = []

    def owner_token(text, listed, exists):
        asked.append((text, listed["conversation"], listed["box"], listed["title"]))
        return "eyJ2IjoxfQ.c2ln"

    monkeypatch.setattr(fleet, "owner_token", owner_token)
    return asked


class TestSendAsOwner:
    def should_ask_the_owner_to_sign_for_the_full_conversation_and_its_box_then_send_the_token(self, fleet, stub, signer, capsys):
        api = stub({
            ("GET", "/sessions"): (200, {"sessions": [session()], "offline": []}),
            ("POST", OWNER_INPUT): [(400, {"error": "Send the token of a message the owner signed."}), (200, {"ok": True, **session()})],
        })

        code = fleet.main(["send", "--as-owner", "aaaaaaaa", "yes, push"], lambda: api)

        assert (code, signer, api.calls[1:], capsys.readouterr().out) == (
            0, [("yes, push", CLAUDE, "mac", "Fix the login form")],
            [("POST", OWNER_INPUT, {}), ("POST", OWNER_INPUT, {"token": "eyJ2IjoxfQ.c2ln"})],
            "sent as the owner to aaaaaaaa  claude@mac  idle  Fix the login form  [/workspace/code/app]\n")

    @pytest.mark.parametrize("listed,said", [
        (session(status="busy"), "refused: aaaaaaaa is busy: the owner signs for an idle session only\n"),
        (session(status="waiting"), "refused: aaaaaaaa is waits-for-owner: the owner signs for an idle session only\n"),
        (session(agent="opencode"), "refused: aaaaaaaa runs opencode: only Claude Code checks a message the owner signed\n"),
    ], ids=["busy", "waiting", "opencode"])
    def should_not_ask_the_owner_for_a_message_the_session_could_not_take(self, fleet, stub, signer, capsys, listed, said):
        api = stub({("GET", "/sessions"): (200, {"sessions": [listed], "offline": []})})

        code = fleet.main(["send", "--as-owner", "aaaaaaaa", "yes, push"], lambda: api)

        assert (code, signer, len(api.calls), capsys.readouterr().err) == (3, [], 1, said)

    def should_not_ask_the_owner_when_the_terminal_takes_no_owner_messages(self, fleet, stub, signer, capsys):
        api = stub({
            ("GET", "/sessions"): (200, {"sessions": [session()], "offline": []}),
            ("POST", OWNER_INPUT): (404, {"error": "Not found."}),
        })

        code = fleet.main(["send", "--as-owner", "aaaaaaaa", "yes, push"], lambda: api)

        assert (code, signer, capsys.readouterr().err) == (
            1, [], "fleet: the terminal takes no owner messages: it needs web-terminal fd5e2fd or later with KEYGUARD_OWNER_PUBLIC_KEY\n")

    def should_exit_3_when_the_terminal_refuses_the_signed_message(self, fleet, stub, signer, capsys):
        api = stub({
            ("GET", "/sessions"): (200, {"sessions": [session()], "offline": []}),
            ("POST", OWNER_INPUT): [(400, {}), (409, {"error": "The owner's signature has expired.", **session()})],
        })

        code = fleet.main(["send", "--as-owner", "aaaaaaaa", "yes, push"], lambda: api)

        assert (code, capsys.readouterr().err) == (3, "refused: The owner's signature has expired.\n")


class TestOwnerToken:
    def should_ask_keyguard_on_the_mac(self, fleet, monkeypatch):
        asked = []
        monkeypatch.setattr(fleet.envify, "owner_signature", lambda *args: asked.append(args) or "eyJ2IjoxfQ.c2ln")

        token = fleet.owner_token("yes", session(title=None), lambda path: False)

        assert (token, asked) == ("eyJ2IjoxfQ.c2ln", [("yes", CLAUDE, "mac", "")])

    def should_fail_with_the_reason_keyguard_gives(self, fleet, monkeypatch):
        def refused(*_):
            raise fleet.envify.EnvifyError("keyguard answered 403: you refused")
        monkeypatch.setattr(fleet.envify, "owner_signature", refused)

        with pytest.raises(fleet.FleetError, match="keyguard gave no owner signature: keyguard answered 403: you refused"):
            fleet.owner_token("yes", session(), lambda path: False)

    def should_ask_the_unlock_client_on_the_dev_box_with_the_text_on_stdin(self, fleet, monkeypatch):
        ran = []

        def fake_run(argv, **kwargs):
            ran.append((argv, kwargs["input"]))
            return fleet.subprocess.CompletedProcess(argv, 0, stdout="eyJ2IjoxfQ.c2ln\n")
        monkeypatch.setattr(fleet.subprocess, "run", fake_run)

        token = fleet.owner_token("yes,\npush", session(box="devbox"), lambda path: str(path) == "/opt/unlock")

        assert (token, ran) == ("eyJ2IjoxfQ.c2ln", [(
            ["/opt/unlock/keyguard-passkey", "sign", "--target", CLAUDE, "--box", "devbox", "--title", "Fix the login form"], "yes,\npush")])

    def should_fail_with_the_exit_code_of_the_unlock_client(self, fleet, monkeypatch):
        monkeypatch.setattr(fleet.subprocess, "run", lambda argv, **_: fleet.subprocess.CompletedProcess(argv, 2, stdout=""))

        with pytest.raises(fleet.FleetError, match="keyguard-passkey sign exited 2"):
            fleet.owner_token("yes", session(box="devbox"), lambda path: str(path) == "/opt/unlock")


class TestCli:
    def should_print_its_usage_without_loading_the_token(self, run_cli):
        result = run_cli("fleet", ["--help"], env_extra={"TELEGRAM_BOT_WEB_TERMINAL_AUTOMATION_TOKEN": ""})

        assert (result.returncode, "watch" in result.stdout, "envify" in result.stderr) == (0, True, False)
