import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stderr
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest

SESSION = UUID("4a015f0f-199b-4270-9c06-fecc5d85b976")
PANE = "%4"
LONG_AGO = datetime(2020, 1, 1, tzinfo=UTC)
LONG_AFTER = datetime(2100, 1, 1, tzinfo=UTC)
SUBAGENT = "a3f9c2e1b7d04e55"
QUESTION = {"questions": [{"question": "Tea or coffee?"}]}


@pytest.fixture
def notify(load_script, tmp_path, monkeypatch):
    module = load_script("claude-notify")
    monkeypatch.setattr(module, "STATE_DIR", tmp_path / "state")
    delivery = sys.modules["notify_delivery"]
    monkeypatch.setattr(delivery, "DEVBOX_TOKEN_FILE", tmp_path / "no-token")
    monkeypatch.setattr(delivery, "IS_MAC", False)
    monkeypatch.setattr(delivery.socket, "gethostname", lambda: "f635a28c3a2e")
    monkeypatch.setattr(module.master_session, "MARK_DIR", tmp_path / "master")
    monkeypatch.setattr(module.presence, "PRESENCE_DIR", tmp_path / "presence")
    monkeypatch.setattr(module, "window_marks", module.WindowMarks)
    monkeypatch.setenv("CLAUDE_PROJECTS", str(tmp_path / "projects"))
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
    monkeypatch.delenv("TMUX_PANE", raising=False)
    return module


def _reader(notify, kind):
    return lambda: notify.presence.Presence(kind)


@pytest.fixture
def at_a_computer(notify):
    return _reader(notify, "computer")


@pytest.fixture
def from_telegram(notify, monkeypatch):
    monkeypatch.setattr(notify, "window_marks", lambda: notify.WindowMarks("automation"))


def _record_kill(window, arguments):
    if arguments[0] == "kill-window":
        window.events.append(arguments)
    return ""


@pytest.fixture
def one_shot(notify, monkeypatch):
    window = SimpleNamespace(marks=notify.WindowMarks("automation", "1"), events=[])
    monkeypatch.setattr(notify, "window_marks", lambda: window.marks)
    monkeypatch.setattr(notify, "tmux_output", lambda *arguments: _record_kill(window, arguments))
    monkeypatch.setenv("TMUX_PANE", PANE)
    return window


@pytest.fixture
def spawned(notify, monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "spawn", lambda arguments: calls.append(list(arguments)))
    return calls


@pytest.fixture
def delivered(notify, monkeypatch):
    bodies = []
    monkeypatch.setattr(notify, "deliver", lambda body: bodies.append(json.loads(body)) or 0)
    return bodies


def _hook(notify, event_name, **fields):
    notify.handle_hook(json.dumps({"session_id": str(SESSION), "hook_event_name": event_name, **fields}))


def _armed_token(spawned):
    arguments, = spawned
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
        assert delivered == [{"session": str(SESSION), "container": "f635a28c3a2e", "title": None, "text": "Done.",
                              "kind": "finished"}]

    def should_name_the_session_by_its_title(self, notify, spawned, delivered, tmp_path):
        transcript = tmp_path / "projects" / "-workspace" / f"{SESSION}.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text(json.dumps({"type": "ai-title", "aiTitle": "Telegram alert layout"}) + "\n")
        _hook(notify, "Stop", last_assistant_message="Done.")

        notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: None)

        assert [body["title"] for body in delivered] == ["Telegram alert layout"]

    def should_send_no_title_when_the_transcript_cannot_be_read(self, notify, spawned, delivered, tmp_path):
        (tmp_path / "projects" / "-workspace" / f"{SESSION}.jsonl").mkdir(parents=True)
        _hook(notify, "Stop", last_assistant_message="Done.")

        notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: None)

        assert [body["title"] for body in delivered] == [None]

    def should_wait_ten_minutes_in_short_polls_before_sending_while_someone_is_at_a_computer(
            self, notify, spawned, delivered, at_a_computer):
        _hook(notify, "Stop", last_assistant_message="Done.")
        waited = []

        notify.fire(SESSION, _armed_token(spawned), sleep=waited.append, presence_reader=at_a_computer)

        assert waited == [5.0] * 120
        assert [body["text"] for body in delivered] == ["Done."]

    def should_stop_waiting_as_soon_as_a_prompt_cancels_the_ping(self, notify, spawned, delivered):
        _hook(notify, "Stop", last_assistant_message="Done.")
        waited = []

        def submit_on_first_poll(seconds):
            waited.append(seconds)
            _hook(notify, "UserPromptSubmit", prompt="next")

        notify.fire(SESSION, _armed_token(spawned), sleep=submit_on_first_poll)

        assert waited == [5.0]
        assert delivered == []

    def should_not_ping_when_a_prompt_was_submitted_in_time(self, notify, spawned, delivered):
        _hook(notify, "Stop", last_assistant_message="Done.")
        _hook(notify, "UserPromptSubmit", prompt="next")

        notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: None)

        assert delivered == []

    def should_let_only_the_latest_stop_ping(self, notify, spawned, delivered):
        _hook(notify, "Stop", last_assistant_message="First.")
        _hook(notify, "Stop", last_assistant_message="Second.")
        first, second = spawned

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

    def should_not_ping_when_the_master_session_finishes(self, notify, spawned, delivered):
        notify.master_session.mark(SESSION, True)

        _hook(notify, "Stop", last_assistant_message="Watching 4 sessions.")

        assert (spawned, delivered) == ([], [])

    def should_ping_again_once_the_session_is_no_longer_the_master(self, notify, spawned, delivered):
        notify.master_session.mark(SESSION, True)
        notify.master_session.mark(SESSION, False)

        _hook(notify, "Stop", last_assistant_message="Done.")
        notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: None)

        assert [body["text"] for body in delivered] == ["Done."]

    def should_still_ping_when_only_a_background_shell_runs(self, notify, spawned):
        _hook(notify, "Stop", last_assistant_message="Done.", background_tasks=[{"type": "shell"}])

        assert _armed_token(spawned)

    def should_never_ping_for_an_unattended_run(self, notify, spawned, monkeypatch):
        monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "sdk-cli")

        _hook(notify, "Stop", last_assistant_message="Done.")

        assert spawned == []


class TestAnswerPing:
    REPLY = "Emanuele, here is the plan.\n\n**Step one** reads [the docs](https://example.com).\n\n- `a`\n- b\n"

    def should_arm_the_whole_reply_as_an_answer_for_a_session_started_from_telegram(
            self, notify, spawned, delivered, from_telegram):
        _hook(notify, "Stop", last_assistant_message=self.REPLY)

        notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: None)

        assert delivered == [{"session": str(SESSION), "container": "f635a28c3a2e", "title": None,
                              "text": self.REPLY, "kind": "answer"}]

    def should_not_cut_a_long_reply(self, notify, spawned, delivered, from_telegram):
        reply = "\n".join(f"Line {number}: " + "word " * 20 for number in range(60))
        _hook(notify, "Stop", last_assistant_message=reply)

        notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: None)

        assert [body["text"] for body in delivered] == [reply]

    @pytest.mark.parametrize("reply", ["", "  \n ", None])
    def should_fall_back_to_the_fixed_line_when_the_reply_has_no_text(
            self, notify, spawned, delivered, from_telegram, reply):
        _hook(notify, "Stop", last_assistant_message=reply)

        notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: None)

        assert [(body["text"], body["kind"]) for body in delivered] == [(notify.FINISHED_FALLBACK, "answer")]

    @pytest.mark.parametrize("origin", ["", "user", "automation-x", "Automation"])
    def should_keep_the_first_sentence_ping_for_any_other_origin(
            self, notify, spawned, delivered, monkeypatch, origin):
        monkeypatch.setattr(notify, "window_marks", lambda: notify.WindowMarks(origin))
        _hook(notify, "Stop", last_assistant_message="Done. Details follow.")

        notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: None)

        assert [(body["text"], body["kind"]) for body in delivered] == [("Done.", "finished")]

    @pytest.mark.parametrize("kind", ["computer", "phone", "away", "unknown"])
    def should_send_at_the_first_poll_whoever_is_present(self, notify, spawned, delivered, from_telegram, kind):
        _hook(notify, "Stop", last_assistant_message=self.REPLY)
        waited = []

        notify.fire(SESSION, _armed_token(spawned), sleep=waited.append, presence_reader=_reader(notify, kind))

        assert waited == [5.0]
        assert [body["kind"] for body in delivered] == ["answer"]

    def should_send_although_a_tmux_client_is_using_the_pane(
            self, notify, spawned, delivered, from_telegram, monkeypatch):
        monkeypatch.setenv("TMUX_PANE", PANE)
        _hook(notify, "Stop", last_assistant_message=self.REPLY)
        waited = []

        notify.fire(SESSION, _armed_token(spawned), sleep=waited.append, presence_reader=_reader(notify, "computer"),
                    clients=lambda: [notify.TmuxClient(PANE, LONG_AGO, LONG_AFTER)])

        assert waited == [5.0]
        assert [body["kind"] for body in delivered] == ["answer"]

    def should_send_nothing_for_a_token_that_a_newer_stop_replaced(self, notify, spawned, delivered, from_telegram):
        _hook(notify, "Stop", last_assistant_message="First answer.")
        _hook(notify, "Stop", last_assistant_message="Second answer.")
        first, second = spawned

        notify.fire(SESSION, first[2], sleep=lambda seconds: None)
        assert delivered == []

        notify.fire(SESSION, second[2], sleep=lambda seconds: None)
        assert [body["text"] for body in delivered] == ["Second answer."]

    def should_send_nothing_when_the_session_ends_before_the_poll(self, notify, spawned, delivered, from_telegram):
        _hook(notify, "Stop", last_assistant_message=self.REPLY)

        notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: _hook(notify, "SessionEnd"))

        assert delivered == []

    def should_still_cancel_the_answer_when_a_prompt_is_submitted(self, notify, spawned, delivered, from_telegram):
        _hook(notify, "Stop", last_assistant_message=self.REPLY)
        _hook(notify, "UserPromptSubmit", prompt="next")

        notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: None)

        assert delivered == []

    def should_hold_the_answer_while_background_agents_work(self, notify, spawned, from_telegram):
        _hook(notify, "Stop", last_assistant_message=self.REPLY, background_tasks=[{"type": "subagent"}])

        assert spawned == []

    def should_leave_a_prompt_ping_a_prompt_in_a_session_started_from_telegram(
            self, notify, spawned, delivered, from_telegram):
        _ask(notify)

        notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: None)

        assert [(body["text"], body["kind"]) for body in delivered] == [("Asks: Tea or coffee?", "prompt")]


NO_WORK = {"background_tasks": [], "session_crons": []}


def _stop(notify, reply, **fields):
    _hook(notify, "Stop", last_assistant_message=reply, **fields)


def _fire(notify, spawned, index=0, **kwargs):
    return notify.fire(SESSION, spawned[index][2], sleep=lambda seconds: None, **kwargs)


class TestOneShotWindow:
    REPLY = "Emanuele, the build is green.\n\nNothing else to do."
    CLOSE = ("kill-window", "-t", PANE)

    def should_close_the_window_once_the_answer_was_sent(self, notify, spawned, delivered, one_shot):
        _stop(notify, self.REPLY, **NO_WORK)

        assert _fire(notify, spawned) == 0
        assert [(body["kind"], body["text"]) for body in delivered] == [("answer", self.REPLY)]
        assert one_shot.events == [self.CLOSE]

    def should_close_only_after_the_send_returned(self, notify, spawned, one_shot, monkeypatch):
        monkeypatch.setattr(notify, "deliver", lambda body: one_shot.events.append(("send",)) or 0)
        _stop(notify, self.REPLY, **NO_WORK)

        _fire(notify, spawned)

        assert one_shot.events == [("send",), self.CLOSE]

    @pytest.mark.parametrize("fields", [
        {"background_tasks": [{"type": "shell"}], "session_crons": []},
        {"background_tasks": [], "session_crons": [{"id": "cron-1"}]},
        {"session_crons": []},
        {"background_tasks": []},
        {},
    ], ids=["shell", "cron", "no background_tasks key", "no session_crons key", "no keys"])
    def should_keep_the_window_and_say_why_when_background_work_may_remain(
            self, notify, spawned, delivered, one_shot, fields):
        _stop(notify, self.REPLY, **fields)

        _fire(notify, spawned)

        assert [(body["kind"], body["text"]) for body in delivered] == [
            ("answer", f"{notify.BACKGROUND_NOTE}\n\n{self.REPLY}")]
        assert one_shot.events == []

    @pytest.mark.parametrize("reply", [
        "Shall I push?",
        "Done.\n\nShall I push?\n\n",
        "Done.\n\nShall I push?  \n  ",
        "Done.\n\n**Shall I push?**",
        "Done.\n\n_Shall I push?_",
        "Done.\n\n- Option A?\n- Option B?",
    ])
    def should_keep_the_window_and_say_why_when_the_reply_ends_with_a_question(
            self, notify, spawned, delivered, one_shot, reply):
        _stop(notify, reply, **NO_WORK)

        _fire(notify, spawned)

        assert [body["text"] for body in delivered] == [f"{notify.QUESTION_NOTE}\n\n{reply}"]
        assert one_shot.events == []

    @pytest.mark.parametrize("reply", [
        "Is it done? Yes, it is done.",
        "Why? Because.\nIt works.",
        "Done.\n\nThe question mark ? sits mid-line.",
        "Done.",
    ])
    def should_close_the_window_when_a_question_is_not_the_last_line(
            self, notify, spawned, delivered, one_shot, reply):
        _stop(notify, reply, **NO_WORK)

        _fire(notify, spawned)

        assert [body["text"] for body in delivered] == [reply]
        assert one_shot.events == [self.CLOSE]

    def should_name_the_background_work_when_it_also_asks_a_question(self, notify, spawned, delivered, one_shot):
        _stop(notify, "Shall I wait?", background_tasks=[{"type": "shell"}], session_crons=[])

        _fire(notify, spawned)

        assert [body["text"] for body in delivered] == [f"{notify.BACKGROUND_NOTE}\n\nShall I wait?"]

    def should_keep_the_window_without_a_note_when_the_send_failed(self, notify, spawned, one_shot, monkeypatch):
        bodies = []
        monkeypatch.setattr(notify, "deliver", lambda body: bodies.append(json.loads(body)) or 1)
        _stop(notify, self.REPLY, **NO_WORK)

        assert _fire(notify, spawned) == 1
        assert [body["text"] for body in bodies] == [self.REPLY]
        assert one_shot.events == []

    def should_keep_the_window_when_a_prompt_was_submitted_while_the_answer_was_sent(
            self, notify, spawned, one_shot, monkeypatch):
        def sent_while_the_owner_types(body):
            _hook(notify, "UserPromptSubmit", prompt="one more thing")
            return 0

        monkeypatch.setattr(notify, "deliver", sent_while_the_owner_types)
        _stop(notify, self.REPLY, **NO_WORK)

        _fire(notify, spawned)

        assert one_shot.events == []

    def should_leave_the_close_to_a_newer_stop_that_came_while_the_answer_was_sent(
            self, notify, spawned, one_shot, monkeypatch):
        def sent_while_claude_stops_again(body):
            _stop(notify, "Second answer.", **NO_WORK)
            return 0

        monkeypatch.setattr(notify, "deliver", sent_while_claude_stops_again)
        _stop(notify, self.REPLY, **NO_WORK)

        _fire(notify, spawned)

        assert one_shot.events == []
        assert notify.read_pending(SESSION)["token"] == spawned[1][2]

    def should_keep_the_window_when_it_lost_a_flag_since_the_stop(self, notify, spawned, one_shot, monkeypatch):
        def sent_after_the_flag_went(body):
            one_shot.marks = notify.WindowMarks("automation", "")
            return 0

        monkeypatch.setattr(notify, "deliver", sent_after_the_flag_went)
        _stop(notify, self.REPLY, **NO_WORK)

        _fire(notify, spawned)

        assert one_shot.events == []

    def should_judge_each_stop_anew_while_the_flag_stays(self, notify, spawned, delivered, one_shot):
        _stop(notify, "Shall I go on?", **NO_WORK)
        _fire(notify, spawned)
        assert one_shot.events == []

        _stop(notify, "Yes, all done.", **NO_WORK)
        _fire(notify, spawned, index=1)

        assert [body["text"] for body in delivered] == [f"{notify.QUESTION_NOTE}\n\nShall I go on?", "Yes, all done."]
        assert one_shot.events == [self.CLOSE]

    def should_not_close_a_window_the_bot_started_without_the_ephemeral_flag(
            self, notify, spawned, delivered, one_shot):
        one_shot.marks = notify.WindowMarks("automation", "")
        _stop(notify, "Shall I push?", **NO_WORK)

        _fire(notify, spawned)

        assert [(body["kind"], body["text"]) for body in delivered] == [("answer", "Shall I push?")]
        assert one_shot.events == []

    @pytest.mark.parametrize("origin", ["", "user", "Automation"])
    def should_not_close_a_window_that_the_bot_did_not_start(self, notify, spawned, delivered, one_shot, origin):
        one_shot.marks = notify.WindowMarks(origin, "1")
        _stop(notify, self.REPLY, **NO_WORK)

        _fire(notify, spawned)

        assert [body["kind"] for body in delivered] == ["finished"]
        assert one_shot.events == []

    def should_not_close_a_window_while_background_agents_hold_the_answer(self, notify, spawned, one_shot):
        _stop(notify, self.REPLY, background_tasks=[{"type": "subagent"}], session_crons=[])

        assert spawned == []
        assert one_shot.events == []

    def should_not_close_a_window_that_waits_on_a_permission_prompt(self, notify, spawned, delivered, one_shot):
        _ask(notify)

        _fire(notify, spawned)

        assert [body["kind"] for body in delivered] == ["prompt"]
        assert one_shot.events == []

    def should_arm_no_close_for_a_reply_that_is_not_in_a_one_shot_window(self, notify, spawned, from_telegram):
        _stop(notify, self.REPLY, **NO_WORK)

        assert notify.read_pending(SESSION)["close"] is False


class TestSilentMarker:
    GREEN = "Emanuele, ops sweep 13:15: all green.\n\n[silent]"
    CLOSE = ("kill-window", "-t", PANE)

    def should_arm_no_ping_when_the_last_line_is_the_marker(self, notify, spawned):
        _stop(notify, self.GREEN, **NO_WORK)

        assert spawned == []

    def should_cancel_a_ping_still_pending_when_the_reply_is_silent(self, notify, spawned, from_telegram):
        _stop(notify, "First answer.", **NO_WORK)
        _stop(notify, self.GREEN, **NO_WORK)

        assert notify.read_pending(SESSION) is None

    def should_close_a_one_shot_window_without_sending(self, notify, spawned, delivered, one_shot):
        _stop(notify, self.GREEN, **NO_WORK)

        assert _fire(notify, spawned) == 0
        assert delivered == []
        assert one_shot.events == [self.CLOSE]

    def should_keep_a_one_shot_window_silently_when_background_work_may_remain(
            self, notify, spawned, delivered, one_shot):
        _stop(notify, self.GREEN, background_tasks=[{"type": "shell"}], session_crons=[])

        assert spawned == []
        assert one_shot.events == []

    @pytest.mark.parametrize("reply", [
        "Write [silent] as the last line to mute it.",
        "[silent]\n\nBut this line comes last.",
        "Done.\n\n[silent] after all",
    ])
    def should_send_when_the_marker_is_not_the_whole_last_line(self, notify, spawned, delivered, from_telegram, reply):
        _stop(notify, reply, **NO_WORK)

        _fire(notify, spawned)

        assert [body["text"] for body in delivered] == [reply]


class TestWindowMarks:
    def should_ask_tmux_once_for_both_options_of_the_window_holding_the_pane(self, load_script, monkeypatch):
        notify = load_script("claude-notify")
        monkeypatch.setenv("TMUX_PANE", PANE)
        runs = []
        monkeypatch.setattr(notify.subprocess, "run", lambda command, **kwargs: runs.append(command) or
                            type("Done", (), {"stdout": "automation\t1\n"})())

        assert notify.window_marks() == notify.WindowMarks("automation", "1")
        assert runs == [["tmux", "display-message", "-p", "-t", PANE, "#{@wt_origin}\t#{@wt_ephemeral}"]]

    @pytest.mark.parametrize("stdout, expected", [
        ("automation\t\n", ("automation", "")),
        ("\t1\n", ("", "1")),
        ("\t\n", ("", "")),
        ("\n", ("", "")),
        ("", ("", "")),
    ])
    def should_read_an_option_that_is_not_set_as_empty(self, load_script, monkeypatch, stdout, expected):
        notify = load_script("claude-notify")
        monkeypatch.setenv("TMUX_PANE", PANE)
        monkeypatch.setattr(notify.subprocess, "run", lambda command, **kwargs: type("Done", (), {"stdout": stdout})())

        assert notify.window_marks() == notify.WindowMarks(*expected)

    @pytest.mark.parametrize("origin, ephemeral, automation, one_shot", [
        ("automation", "1", True, True),
        ("automation", "", True, False),
        ("automation", "0", True, False),
        ("", "1", False, False),
        ("Automation", "1", False, False),
        ("user", "1", False, False),
    ])
    def should_call_a_window_one_shot_only_with_both_options(self, notify, origin, ephemeral, automation, one_shot):
        marks = notify.WindowMarks(origin, ephemeral)

        assert (marks.automation, marks.one_shot) == (automation, one_shot)

    def should_not_ask_tmux_outside_a_pane(self, load_script, monkeypatch):
        notify = load_script("claude-notify")
        monkeypatch.delenv("TMUX_PANE", raising=False)
        monkeypatch.setattr(notify.subprocess, "run", lambda *args, **kwargs: pytest.fail("tmux was asked"))

        assert notify.window_marks() == notify.WindowMarks()

    def should_give_nothing_when_tmux_cannot_run(self, load_script, monkeypatch):
        notify = load_script("claude-notify")
        monkeypatch.setenv("TMUX_PANE", PANE)

        def missing_tmux(*args, **kwargs):
            raise FileNotFoundError("tmux")

        monkeypatch.setattr(notify.subprocess, "run", missing_tmux)

        assert notify.window_marks() == notify.WindowMarks()


class TestPresenceTiming:
    @pytest.mark.parametrize("kind", ["away", "unknown"])
    def should_send_at_the_first_poll_when_nobody_is_at_a_web_terminal(self, notify, spawned, delivered, kind):
        _hook(notify, "Stop", last_assistant_message="Done.")
        waited = []

        notify.fire(SESSION, _armed_token(spawned), sleep=waited.append, presence_reader=_reader(notify, kind))

        assert waited == [5.0]
        assert [body["text"] for body in delivered] == ["Done."]

    def should_send_a_prompt_ping_at_the_first_poll_when_nobody_is_at_a_web_terminal(self, notify, spawned, delivered):
        _ask(notify)
        waited = []

        notify.fire(SESSION, _armed_token(spawned), sleep=waited.append, presence_reader=_reader(notify, "away"))

        assert waited == [5.0]
        assert [body["kind"] for body in delivered] == ["prompt"]

    @pytest.mark.parametrize("kind", ["computer", "phone"])
    def should_keep_the_ten_minute_wait_while_someone_is_present(self, notify, spawned, delivered, kind):
        _hook(notify, "Stop", last_assistant_message="Done.")
        waited = []

        notify.fire(SESSION, _armed_token(spawned), sleep=waited.append, presence_reader=_reader(notify, kind))

        assert waited == [5.0] * 120
        assert [body["text"] for body in delivered] == ["Done."]

    def should_send_at_the_next_poll_when_the_last_person_leaves_during_the_wait(self, notify, spawned, delivered):
        _hook(notify, "Stop", last_assistant_message="Done.")
        states = iter(["computer", "computer", "phone", "away", "computer"])
        waited = []

        notify.fire(SESSION, _armed_token(spawned), sleep=waited.append,
                    presence_reader=lambda: notify.presence.Presence(next(states)))

        assert waited == [5.0] * 4
        assert [body["text"] for body in delivered] == ["Done."]

    def should_let_a_prompt_submit_cancel_a_ping_that_is_due_at_the_first_poll(self, notify, spawned, delivered):
        _hook(notify, "Stop", last_assistant_message="Done.")

        def submit_before_the_poll_ends(seconds):
            _hook(notify, "UserPromptSubmit", prompt="next")

        notify.fire(SESSION, _armed_token(spawned), sleep=submit_before_the_poll_ends,
                    presence_reader=_reader(notify, "away"))

        assert delivered == []

    def should_let_a_pane_in_use_cancel_a_ping_when_no_web_terminal_is_open(
            self, notify, spawned, delivered, monkeypatch):
        monkeypatch.setenv("TMUX_PANE", PANE)
        _hook(notify, "Stop", last_assistant_message="Done.")

        notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: None, presence_reader=_reader(notify, "away"),
                    clients=lambda: [notify.TmuxClient(PANE, LONG_AGO, LONG_AFTER)])

        assert delivered == []

    def should_read_the_presence_folder_by_default(self, notify, spawned, delivered):
        _hook(notify, "Stop", last_assistant_message="Done.")
        token = _armed_token(spawned)
        folder = notify.presence.PRESENCE_DIR
        folder.mkdir(parents=True)
        (folder / "terminal").write_text(f"{int(time.time())} phone\n")
        waited = []

        notify.fire(SESSION, token, sleep=waited.append)

        assert waited == [5.0] * 120
        assert [body["text"] for body in delivered] == ["Done."]

    def should_send_at_the_first_poll_by_default_when_the_presence_folder_is_missing(
            self, notify, spawned, delivered):
        _hook(notify, "Stop", last_assistant_message="Done.")
        waited = []

        notify.fire(SESSION, _armed_token(spawned), sleep=waited.append)

        assert waited == [5.0]


class TestSeenPane:
    def should_not_ping_when_a_client_showing_the_pane_was_used_after_the_reply(
            self, notify, spawned, delivered, monkeypatch):
        monkeypatch.setenv("TMUX_PANE", PANE)
        _hook(notify, "Stop", last_assistant_message="Done.")
        waited = []

        notify.fire(SESSION, _armed_token(spawned), sleep=waited.append,
                    clients=lambda: [notify.TmuxClient(PANE, LONG_AGO, LONG_AFTER)])

        assert waited == [5.0]
        assert delivered == []
        assert not notify.state_file(SESSION, "pending").exists()

    @pytest.mark.parametrize("pane, created, activity", [
        (PANE, LONG_AGO - timedelta(days=1), LONG_AGO),
        ("%9", LONG_AGO, LONG_AFTER),
        (PANE, LONG_AFTER, LONG_AFTER),
    ], ids=["used-before-the-reply", "other-pane-used", "only-attached-after-the-reply"])
    def should_ping_when_no_client_used_the_pane_after_the_reply(
            self, notify, spawned, delivered, monkeypatch, at_a_computer, pane, created, activity):
        monkeypatch.setenv("TMUX_PANE", PANE)
        _hook(notify, "Stop", last_assistant_message="Done.")

        notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: None, presence_reader=at_a_computer,
                    clients=lambda: [notify.TmuxClient(pane, created, activity)])

        assert [body["text"] for body in delivered] == ["Done."]

    def should_not_ask_tmux_outside_a_tmux_pane(self, notify, spawned, delivered):
        _hook(notify, "Stop", last_assistant_message="Done.")
        asked = []

        notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: None,
                    clients=lambda: asked.append(True) or [])

        assert asked == []
        assert [body["text"] for body in delivered] == ["Done."]

    def should_parse_each_client_and_skip_malformed_lines(self, notify):
        listing = "%4\t1793727500\t1793727602\n%1\t1793727600\t1793727600\nno-tab-here\n%2\t\t\n%3\t1793727600\n"

        assert notify.parse_clients(listing) == [
            notify.TmuxClient("%4", datetime.fromtimestamp(1793727500, UTC), datetime.fromtimestamp(1793727602, UTC)),
            notify.TmuxClient("%1", datetime.fromtimestamp(1793727600, UTC), datetime.fromtimestamp(1793727600, UTC)),
        ]

    def should_see_no_clients_when_tmux_cannot_run(self, notify, monkeypatch):
        def missing_tmux(*args, **kwargs):
            raise FileNotFoundError("tmux")

        monkeypatch.setattr(notify.subprocess, "run", missing_tmux)

        assert notify.tmux_clients() == []


def _ask(notify, agent=None):
    _hook(notify, "PermissionRequest", tool_name="AskUserQuestion", tool_input=QUESTION, **_from(agent))
    _hook(notify, "Notification", notification_type="permission_prompt", message="Claude needs your input")


def _from(agent):
    return {"agent_id": agent} if agent else {}


def _texts_after_fire(notify, spawned, delivered):
    notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: None)
    return [body["text"] for body in delivered]


class TestPromptPing:
    def should_arm_the_noted_prompt_when_claude_code_reports_it_unanswered(self, notify, spawned, delivered):
        _hook(notify, "PermissionRequest", tool_name="ExitPlanMode", tool_input={})
        _hook(notify, "Notification", notification_type="permission_prompt",
              message="Claude Code needs your approval for the plan")

        assert _texts_after_fire(notify, spawned, delivered) == ["Has a plan ready for your approval."]

    def should_send_the_ping_as_a_prompt(self, notify, spawned, delivered):
        _ask(notify)

        notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: None)

        assert [body["kind"] for body in delivered] == ["prompt"]

    def should_wait_ten_minutes_in_short_polls_before_sending_while_someone_is_at_a_computer(
            self, notify, spawned, delivered, at_a_computer):
        _ask(notify)
        waited = []

        notify.fire(SESSION, _armed_token(spawned), sleep=waited.append, presence_reader=at_a_computer)

        assert waited == [5.0] * 120
        assert [body["text"] for body in delivered] == ["Asks: Tea or coffee?"]

    def should_not_ping_when_a_client_showing_the_pane_was_used_after_the_prompt(
            self, notify, spawned, delivered, monkeypatch):
        monkeypatch.setenv("TMUX_PANE", PANE)
        _ask(notify)

        notify.fire(SESSION, _armed_token(spawned), sleep=lambda seconds: None,
                    clients=lambda: [notify.TmuxClient(PANE, LONG_AGO, LONG_AFTER)])

        assert delivered == []

    @pytest.mark.parametrize("event_name", ["PostToolUse", "PostToolUseFailure"])
    @pytest.mark.parametrize("agent", [None, SUBAGENT], ids=["main", "subagent"])
    def should_drop_the_ping_once_the_prompted_tool_ran(self, notify, spawned, delivered, event_name, agent):
        _ask(notify, agent)

        _hook(notify, event_name, tool_name="AskUserQuestion", **_from(agent))

        assert _texts_after_fire(notify, spawned, delivered) == []

    @pytest.mark.parametrize("tool_name, agent", [("Bash", None), ("AskUserQuestion", SUBAGENT)],
                             ids=["other-tool", "same-tool-in-a-subagent"])
    def should_keep_the_ping_when_another_call_finished(self, notify, spawned, delivered, tool_name, agent):
        _ask(notify)

        _hook(notify, "PostToolUse", tool_name=tool_name, **_from(agent))

        assert _texts_after_fire(notify, spawned, delivered) == ["Asks: Tea or coffee?"]

    def should_keep_a_finished_ping_when_a_tool_ran(self, notify, spawned, delivered):
        _hook(notify, "Stop", last_assistant_message="Done.")

        _hook(notify, "PostToolUse", tool_name="Bash")

        assert _texts_after_fire(notify, spawned, delivered) == ["Done."]

    def should_fall_back_to_the_notification_message(self, notify, spawned, delivered):
        _hook(notify, "Notification", notification_type="permission_prompt", message="Claude needs your permission")

        assert _texts_after_fire(notify, spawned, delivered) == ["Claude needs your permission"]

    def should_not_reuse_a_prompt_note_after_a_new_prompt_was_submitted(self, notify, spawned, delivered):
        _hook(notify, "PermissionRequest", tool_name="Bash", tool_input={"command": "git push"})
        _hook(notify, "UserPromptSubmit", prompt="no, wait")
        _hook(notify, "Notification", notification_type="permission_prompt", message="Claude needs your permission")

        assert _texts_after_fire(notify, spawned, delivered) == ["Claude needs your permission"]

    @pytest.mark.parametrize("notification_type", ["idle_prompt", "auth_success"])
    def should_ignore_other_notifications(self, notify, spawned, notification_type):
        _hook(notify, "Notification", notification_type=notification_type, message="x")

        assert spawned == []


class TestMain:
    def should_never_fail_the_hook_on_bad_input(self, notify, monkeypatch):
        monkeypatch.setattr(notify.sys, "stdin", io.StringIO("{not json"))

        with redirect_stderr(io.StringIO()):
            assert notify.main([]) == 0

    def should_reject_unknown_arguments(self, notify):
        with redirect_stderr(io.StringIO()):
            assert notify.main(["bogus"]) == 2


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("tmux") is None, reason="needs tmux")
class TestRealTmux:
    @pytest.fixture
    def window(self, load_script, monkeypatch):
        environment = {key: value for key, value in os.environ.items() if key not in ("TMUX", "TMUX_PANE")}
        with tempfile.TemporaryDirectory(prefix="cn") as folder:
            socket_path = f"{folder}/tmux.sock"

            def tmux(*arguments):
                command = ["tmux", "-S", socket_path, "-f", "/dev/null", *arguments]
                return subprocess.run(command, capture_output=True, text=True, check=True, env=environment).stdout.strip()

            tmux("new-session", "-d", "-s", "lab", "-n", "keep", "sleep 60")
            pane = tmux("new-window", "-d", "-P", "-F", "#{pane_id}", "-n", "one-shot", "sleep 60")
            tmux("set-option", "-w", "-t", pane, "@wt_origin", "automation")
            tmux("set-option", "-w", "-t", pane, "@wt_ephemeral", "1")
            monkeypatch.setenv("TMUX", f"{socket_path},0,0")
            monkeypatch.setenv("TMUX_PANE", pane)
            try:
                yield SimpleNamespace(notify=load_script("claude-notify"), tmux=tmux, pane=pane)
            finally:
                subprocess.run(["tmux", "-S", socket_path, "kill-server"], capture_output=True, check=False, env=environment)

    def should_read_both_options_of_the_window_holding_the_pane(self, window):
        assert window.notify.window_marks() == window.notify.WindowMarks("automation", "1")

    def should_read_an_option_that_is_not_set_as_empty(self, window):
        window.tmux("set-option", "-w", "-u", "-t", window.pane, "@wt_ephemeral")

        assert window.notify.window_marks() == window.notify.WindowMarks("automation", "")

    def should_close_the_window_of_the_pane_and_no_other(self, window):
        window.notify.close_window()

        assert window.tmux("list-windows", "-F", "#{window_name}") == "keep"

    def should_leave_a_window_without_the_flag_open(self, window):
        window.tmux("set-option", "-w", "-u", "-t", window.pane, "@wt_ephemeral")

        window.notify.close_window()

        assert window.tmux("list-windows", "-F", "#{window_name}").splitlines() == ["keep", "one-shot"]
