from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

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
        def __init__(self, answers, tokens=None):
            super().__init__("http://terminal.test", tokens or fleet.Tokens({fleet.TOKEN_NAME: "token"}, None))
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


OPENCODE = "ses_1111111111aaaaaaaaOpEnCoDe"


def resumed(**over):
    return {"window": "@5", "pane": "%12", "box": "devbox", "session": "main", "conversation": CLAUDE,
            "model": "claude-sonnet-5-5", "effort": "high", **over}


def listing(**over):
    return 200, {"sessions": [session(pane="%12", **over)] if over else [], "offline": []}


@pytest.fixture
def clock(fleet, monkeypatch):
    now = SimpleNamespace(now=0.0)

    def sleep(seconds):
        now.now += seconds

    monkeypatch.setattr(fleet, "time", SimpleNamespace(monotonic=lambda: now.now, sleep=sleep))
    return now


class TestTerminalUrl:
    @pytest.mark.parametrize("environ,markers,expected", [
        ({}, set(), "http://localhost:8122"),
        ({}, {"/.dockerenv"}, "http://host.docker.internal:8122"),
        ({}, {"/opt/unlock", "/.dockerenv"}, "http://web-terminal.web-terminal.svc.cluster.local"),
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

    @pytest.mark.parametrize("outcome,expected", [
        ("decision", "decision"),
        ("blocked", "blocked"),
        ("running", "running"),
        ("done", "done"),
        (None, "idle"),
    ])
    def should_tell_an_idle_session_by_what_its_last_reply_leaves_for_the_owner(self, fleet, outcome, expected):
        assert fleet.state_of(session(outcome=outcome)) == expected

    def should_read_a_terminal_that_lists_no_outcome_as_idle(self, fleet):
        assert fleet.state_of(session()) == "idle"


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

    @pytest.mark.parametrize("outcome,state", [("done", "done"), (None, "idle"), ("running", "running")])
    def should_show_the_background_tasks_beside_the_state_the_reply_gives(self, fleet, outcome, state):
        line = fleet.describe(session(outcome=outcome, tasks=2))

        assert line == f"aaaaaaaa  claude@mac  {state}  Fix the login form  [/workspace/code/app]  tasks:2"


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

    @pytest.mark.parametrize("outcome", ["decision", "blocked", "running", "done", None])
    def should_print_the_reply_of_a_session_that_turns_idle_whatever_its_reply_leaves(self, watching, outcome):
        watcher, _, _ = watching([session(status="busy")], [session(status="idle", outcome=outcome)], replies={CLAUDE: "Tests pass."})
        watcher.start()

        assert watcher.look()[-1] == "  reply: Tests pass."

    def should_print_no_reply_when_an_idle_session_only_changes_its_outcome(self, watching):
        watcher, _, _ = watching([session(outcome="running", tasks=1)], [session(outcome="done")], replies={CLAUDE: "Tests pass."})
        watcher.start()

        assert watcher.look() == ["running -> aaaaaaaa  claude@mac  done  Fix the login form  [/workspace/code/app]"]

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

    def should_resume_a_conversation_by_its_short_id_and_print_the_model_and_effort_it_runs_on(self, fleet, stub, capsys):
        api = stub({("POST", "/sessions"): (201, resumed())})

        code = fleet.main(["resume", "devbox", "aaaaaaaa", "Carry on"], lambda: api)

        assert (code, api.calls[0][2], capsys.readouterr().out) == (
            0, {"box": "devbox", "resume": "aaaaaaaa", "prompt": "Carry on"},
            f"started %12 (@5) on devbox  {CLAUDE}  model claude-sonnet-5-5  effort high\n")

    def should_send_the_agent_model_and_effort_given_and_read_the_prompt_from_stdin(self, fleet, stub, monkeypatch):
        monkeypatch.setattr(fleet.sys, "stdin", SimpleNamespace(read=lambda: "Carry on"))
        api = stub({("POST", "/sessions"): (201, resumed(model="opus", effort="max"))})

        fleet.main(["resume", "devbox", CLAUDE, "-", "--agent", "claude", "--model", "opus", "--effort", "max"], lambda: api)

        assert api.calls[0][2] == {"box": "devbox", "resume": CLAUDE, "prompt": "Carry on", "agent": "claude", "model": "opus", "effort": "max"}

    def should_print_a_dash_for_a_setting_the_agent_picks_itself(self, fleet, stub, capsys):
        api = stub({("POST", "/sessions"): (201, resumed(conversation=OPENCODE, model=None, effort=None))})

        fleet.main(["resume", "devbox", "OpEnCoDe", "Carry on"], lambda: api)

        assert capsys.readouterr().out.endswith(f"{OPENCODE}  model -  effort -\n")

    def should_exit_3_when_the_conversation_to_resume_is_live(self, fleet, stub, capsys):
        api = stub({("POST", "/sessions"): (409, {"error": "aaaaaaaa is live in %3: send it the text instead."})})

        code = fleet.main(["resume", "devbox", "aaaaaaaa", "Carry on"], lambda: api)

        assert (code, capsys.readouterr().err) == (3, "refused: aaaaaaaa is live in %3: send it the text instead.\n")

    def should_wait_for_the_resumed_session_to_work_and_stop_before_it_prints_the_reply_to_the_prompt(self, fleet, stub, clock, capsys):
        api = stub({
            ("POST", "/sessions"): (201, resumed()),
            ("GET", "/sessions"): [listing(), listing(status="idle"), listing(status="busy"), listing(status="busy"), listing(status="idle")],
            ("GET", f"/sessions/{CLAUDE}/last-reply"): (200, {"text": "Done, tests pass.", **session(pane="%12")}),
        })

        code = fleet.main(["resume", "devbox", "aaaaaaaa", "Carry on", "--wait"], lambda: api)

        assert (code, capsys.readouterr().out.splitlines()[-1], [call[:2] for call in api.calls].count(("GET", "/sessions"))) == (0, "Done, tests pass.", 5)
        assert not any(path.endswith("/first-reply") for _, path, _ in api.calls)

    def should_print_no_reply_yet_when_the_resumed_session_shows_no_work_in_time(self, fleet, stub, clock, capsys):
        api = stub({("POST", "/sessions"): (201, resumed()), ("GET", "/sessions"): (200, {"sessions": [session(status="idle")], "offline": []})})

        code = fleet.main(["resume", "devbox", "aaaaaaaa", "Carry on", "--wait"], lambda: api)

        assert (code, capsys.readouterr().out.splitlines()[-1], clock.now) == (0, "no reply yet", fleet.FIRST_REPLY_WAIT_S)

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


HOLD = Path("/dev/shm/fleet-1001/FLEET_WEB_TERMINAL_AUTOMATION_TOKEN.sock")


@pytest.fixture
def holder(fleet, monkeypatch):
    state = SimpleNamespace(value=None, started=[], stopped=[])

    def start(path, value):
        state.started.append((path, value))
        state.value = value

    def stop(path):
        state.stopped.append(path)
        was_held, state.value = state.value is not None, None
        return was_held

    monkeypatch.setattr(fleet.token_hold, "fetch", lambda path: state.value)
    monkeypatch.setattr(fleet.token_hold, "start", start)
    monkeypatch.setattr(fleet.token_hold, "stop", stop)
    return state


@pytest.fixture
def loads(fleet, monkeypatch):
    caches = []

    def values_via_shell(keys, environ):
        caches.append(environ.get("ENVIFY_CACHE_TIMEOUT", "inherited"))
        return {keys[0]: f"loaded-{len(caches)}"}

    monkeypatch.setattr(fleet.envify, "values_via_shell", values_via_shell)
    return caches


@pytest.fixture
def replying(fleet):
    class ReplyingApi(fleet.Api):
        def __init__(self, tokens, statuses):
            super().__init__("http://terminal.test", tokens)
            self.statuses = list(statuses)
            self.sent_with = []

        def send(self, method, path, body, timeout, token):
            self.sent_with.append(token)
            return fleet.Answer(self.statuses.pop(0), None)

    return ReplyingApi


class TestTokens:
    def should_take_the_bearer_from_the_environment_first(self, fleet, holder, loads):
        holder.value = "held"

        assert (fleet.Tokens({fleet.TOKEN_NAME: "exported"}, HOLD).current(), loads) == ("exported", [])

    def should_take_the_held_bearer_before_loading_one(self, fleet, holder, loads):
        holder.value = "held"

        assert (fleet.Tokens({}, HOLD).current(), loads) == ("held", [])

    @pytest.mark.parametrize("hold_at", [HOLD, None])
    def should_load_through_envify_with_the_callers_cache_when_nothing_holds_one(self, fleet, holder, loads, hold_at):
        assert (fleet.Tokens({}, hold_at).current(), loads) == ("loaded-1", ["inherited"])

    def should_renew_a_held_bearer_once_when_the_terminal_refuses_it(self, fleet, holder, loads, replying):
        holder.value = "old"
        api = replying(fleet.Tokens({}, HOLD), [401, 200])

        answer = api.call("GET", "/sessions")

        assert (answer.status, api.sent_with, holder.stopped, holder.started, loads) == (
            200, ["old", "loaded-1"], [HOLD], [(HOLD, "loaded-1")], ["0"])

    def should_renew_at_most_once_in_one_run(self, fleet, holder, loads, replying):
        holder.value = "old"
        api = replying(fleet.Tokens({}, HOLD), [401, 401, 401])

        statuses = [api.call("GET", "/sessions").status for _ in range(2)]

        assert (statuses, api.sent_with, loads) == ([401, 401], ["old", "loaded-1", "loaded-1"], ["0"])

    def should_pass_a_refusal_on_when_the_bearer_is_not_held(self, fleet, holder, loads, replying):
        api = replying(fleet.Tokens({fleet.TOKEN_NAME: "exported"}, HOLD), [401])

        assert (api.call("GET", "/sessions").status, holder.stopped, loads) == (401, [], [])

    def should_ask_for_no_second_approval_after_a_renewal_that_failed(self, fleet, holder, replying, monkeypatch):
        holder.value = "old"
        asked = []

        def refused(keys, environ):
            asked.append(keys)
            raise fleet.envify.EnvifyError("Touch ID cancelled or failed")

        monkeypatch.setattr(fleet.envify, "values_via_shell", refused)
        api = replying(fleet.Tokens({}, HOLD), [401, 401])

        with pytest.raises(fleet.FleetError, match="Touch ID cancelled"):
            api.call("GET", "/sessions")

        assert (api.call("GET", "/sessions").status, len(asked), api.sent_with) == (401, 1, ["old", "old"])


class TestHoldSocket:
    def should_hold_no_bearer_on_the_devbox_where_every_session_shares_the_container(self, fleet):
        assert fleet.hold_socket({}, lambda path: path == fleet.DEVBOX_MARKER) is None

    def should_hold_it_in_the_private_folder_of_this_user_under_the_tokens_name_elsewhere(self, fleet, monkeypatch):
        monkeypatch.setattr(fleet.token_hold, "private_base", lambda platform, environ, shm: Path("/dev/shm"))

        assert fleet.hold_socket({}, lambda path: False) == Path(
            f"/dev/shm/fleet-{fleet.os.getuid()}/FLEET_WEB_TERMINAL_AUTOMATION_TOKEN.sock")

    def should_use_the_bearer_of_its_own_that_the_terminal_marks_as_fleets(self, fleet):
        assert fleet.TOKEN_NAME == "FLEET_WEB_TERMINAL_AUTOMATION_TOKEN"


class TestHoldingMaster:
    @pytest.fixture
    def marking(self, fleet, stub, monkeypatch, tmp_path):
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", MASTER)
        monkeypatch.setattr(fleet.master_session, "MARK_DIR", tmp_path / "master")

        def run(state, tokens, *flags):
            marked = flags[-1] if flags else MASTER
            answer = (200, {"ok": True, **session(conversation=marked, short=marked[:8], master=state == "on")})
            api = stub({("POST", f"/sessions/{marked}/master"): answer}, tokens)
            return fleet.main(["master", state, *flags], lambda: api), api
        return run

    def should_hold_a_bearer_loaded_past_keyguards_cache_when_it_turns_master(self, fleet, holder, loads, marking):
        code, api = marking("on", fleet.Tokens({}, HOLD))

        assert (code, holder.started, loads, api.calls[0][2]) == (0, [(HOLD, "loaded-1")], ["0"], {"on": True})

    def should_hold_the_exported_bearer_without_loading_one(self, fleet, holder, loads, marking):
        marking("on", fleet.Tokens({fleet.TOKEN_NAME: "exported"}, HOLD))

        assert (holder.started, loads) == ([(HOLD, "exported")], [])

    def should_keep_a_holder_that_already_answers(self, fleet, holder, loads, marking):
        holder.value = "held"

        marking("on", fleet.Tokens({}, HOLD))

        assert (holder.started, loads) == ([], [])

    def should_say_it_holds_nothing_where_no_private_folder_exists(self, fleet, holder, loads, marking, capsys):
        code, _ = marking("on", fleet.Tokens({}, None))

        assert (code, holder.started, "holds no token" in capsys.readouterr().err) == (0, [], True)

    def should_stop_the_holder_when_it_stops_being_master(self, fleet, holder, loads, marking):
        holder.value = "held"

        code, _ = marking("off", fleet.Tokens({}, HOLD))

        assert (code, holder.stopped) == (0, [HOLD])

    def should_hold_nothing_when_it_marks_another_session(self, fleet, holder, loads, marking):
        marking("on", fleet.Tokens({fleet.TOKEN_NAME: "exported"}, HOLD), "--session", CLAUDE)

        assert holder.started == []

    def should_hold_the_bearer_when_it_names_its_own_session(self, fleet, holder, loads, marking):
        marking("on", fleet.Tokens({fleet.TOKEN_NAME: "exported"}, HOLD), "--session", MASTER)

        assert holder.started == [(HOLD, "exported")]


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
        result = run_cli("fleet", ["--help"], env_extra={"FLEET_WEB_TERMINAL_AUTOMATION_TOKEN": ""})

        assert (result.returncode, "watch" in result.stdout, "envify" in result.stderr) == (0, True, False)
