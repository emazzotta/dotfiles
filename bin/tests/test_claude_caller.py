import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from bin.tests.conftest import BIN_DIR, requires_tool, skip_on_darwin

SESSION = UUID("48f92bcb-f080-4149-8046-a7e1df07fef5")
ROOT = "ses_e55094ca5ffeOv2MVKG3yIYwxa"
SUBAGENT = "ses_e55094ca6001AbCdEfGhIjKlMn"
OTHER = "ses_e55094cb7002ZyXwVuTsRqPoNm"
SESSIONS = {
    ROOT: {"id": ROOT, "title": "Fix the share page"},
    SUBAGENT: {"id": SUBAGENT, "parentID": ROOT, "title": "Find the renderer (@explore subagent)"},
    OTHER: {"id": OTHER, "title": "Another chat"},
}
BUSY = {"type": "busy"}
OPENCODE_PID = 4242
PORT = 4096


def title_record(title):
    return json.dumps({"type": "ai-title", "aiTitle": title, "sessionId": str(SESSION)})


def message_record(text):
    return json.dumps({"type": "user", "message": {"content": text}})


@pytest.fixture
def caller(load_script, monkeypatch, tmp_path):
    module = load_script("claude-caller")
    monkeypatch.setattr(module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", str(SESSION))
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.setattr(module, "parent_and_name", lambda pid: None)
    return module


@pytest.fixture
def opencode(caller, monkeypatch):
    """opencode two processes up, as when its bash tool runs envify, and the sessions its server answers with."""
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")
    monkeypatch.setattr(caller.os, "getppid", lambda: 4244)
    tree = {4244: (4243, "bash"), 4243: (OPENCODE_PID, "opencode"), OPENCODE_PID: (1, "zsh")}
    monkeypatch.setattr(caller, "parent_and_name", tree.get)
    monkeypatch.setattr(caller, "listening_ports", lambda pid: [PORT] if pid == 4243 else [])
    server = SimpleNamespace(statuses={}, sessions=json.loads(json.dumps(SESSIONS)), paths=[])

    def asked(port, path):
        server.paths.append(path)
        if port != PORT:
            return None
        if path == "/session/status":
            return server.statuses
        return server.sessions.get(path[len("/session/"):])
    monkeypatch.setattr(caller, "asked", asked)
    return server


@pytest.fixture
def transcript(caller):
    def _write(*records):
        path = caller.PROJECTS_DIR / "-workspace" / f"{SESSION}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"{record}\n" for record in records))
        return path
    return _write


class TestDescribe:
    def should_give_the_first_block_of_the_session_id_and_its_latest_title(self, caller, transcript):
        transcript(title_record("First guess"), message_record("hi"), title_record("Keyguard approval names"),
                   message_record("go"))

        assert caller.describe() == {"session": "48f92bcb", "title": "Keyguard approval names"}

    def should_leave_the_title_empty_when_the_transcript_has_none_yet(self, caller, transcript):
        transcript(message_record("hi"))

        assert caller.describe() == {"session": "48f92bcb", "title": ""}

    def should_leave_the_title_empty_when_no_transcript_exists(self, caller):
        assert caller.describe() == {"session": "48f92bcb", "title": ""}

    def should_name_the_shell_when_no_session_is_set(self, caller, monkeypatch):
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")

        assert caller.describe() == {"session": "", "title": "shell"}

    def should_treat_a_session_id_that_is_no_uuid_as_none(self, caller, monkeypatch):
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "not-a-session")

        assert caller.describe() == {"session": "", "title": "shell"}

    def should_skip_a_line_that_mentions_the_title_type_but_is_no_title_record(self, caller, transcript):
        transcript(title_record("Real title"), message_record('"ai-title" in prose'), "{broken ai-title")

        assert caller.describe()["title"] == "Real title"


class TestOpencode:
    def should_name_the_working_session_by_the_end_of_its_id(self, caller, opencode):
        opencode.statuses = {ROOT: BUSY}

        assert caller.describe() == {"session": "G3yIYwxa", "title": "Fix the share page"}

    @pytest.mark.parametrize("statuses", [{SUBAGENT: BUSY}, {ROOT: BUSY, SUBAGENT: BUSY}])
    def should_name_the_session_a_working_subagent_works_for(self, caller, opencode, statuses):
        opencode.statuses = statuses

        assert caller.describe() == {"session": "G3yIYwxa", "title": "Fix the share page"}

    def should_count_a_session_that_retries_as_working(self, caller, opencode):
        opencode.statuses = {ROOT: {"type": "retry", "attempt": 2, "message": "rate limited", "next": 0}}

        assert caller.describe()["session"] == "G3yIYwxa"

    def should_pass_over_idle_sessions(self, caller, opencode):
        opencode.statuses = {OTHER: {"type": "idle"}, ROOT: BUSY}

        assert caller.describe()["session"] == "G3yIYwxa"

    def should_clean_the_title(self, caller, opencode):
        opencode.statuses = {ROOT: BUSY}
        opencode.sessions[ROOT]["title"] = "two\nlines \u202eflipped"

        assert caller.describe()["title"] == "two lines flipped"

    def should_prefer_the_claude_session(self, caller, opencode, monkeypatch):
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", str(SESSION))
        opencode.statuses = {ROOT: BUSY}

        assert caller.describe() == {"session": "48f92bcb", "title": ""}
        assert opencode.paths == []

    def should_name_none_when_two_sessions_work_at_once(self, caller, opencode):
        opencode.statuses = {ROOT: BUSY, OTHER: BUSY}

        assert caller.describe() == {"session": "", "title": "shell"}

    def should_name_none_when_a_working_session_is_unknown(self, caller, opencode):
        opencode.statuses = {ROOT: BUSY, "ses_e55094cc0000UnknownSession": BUSY}

        assert caller.describe() == {"session": "", "title": "shell"}

    def should_name_none_when_a_session_answers_with_another_id(self, caller, opencode):
        opencode.statuses = {ROOT: BUSY}
        opencode.sessions[ROOT]["id"] = OTHER

        assert caller.describe() == {"session": "", "title": "shell"}

    def should_give_up_on_sessions_that_name_each_other_as_parent(self, caller, opencode):
        opencode.statuses = {SUBAGENT: BUSY}
        opencode.sessions[ROOT]["parentID"] = SUBAGENT

        assert caller.describe() == {"session": "", "title": "shell"}

    def should_not_ask_for_a_session_id_that_is_no_opencode_id(self, caller, opencode):
        opencode.statuses = {"../config": BUSY}

        assert caller.describe() == {"session": "", "title": "shell"}
        assert opencode.paths == ["/session/status"]

    def should_name_none_when_the_server_does_not_answer(self, caller, opencode):
        opencode.statuses = None

        assert caller.describe() == {"session": "", "title": "shell"}

    def should_name_none_outside_opencode(self, caller, opencode, monkeypatch):
        monkeypatch.setattr(caller, "parent_and_name", {4244: (4243, "bash"), 4243: (1, "zsh")}.get)
        opencode.statuses = {ROOT: BUSY}

        assert caller.describe() == {"session": "", "title": "shell"}
        assert opencode.paths == []

    def should_read_the_port_from_lsof(self, caller, monkeypatch):
        listing = "p4243\nf23\nn127.0.0.1:41337\nf24\nn[::1]:4097\n"
        monkeypatch.setattr(caller.subprocess, "run", lambda command, **_: SimpleNamespace(returncode=0, stdout=listing))

        assert caller.listening_ports(4243) == [41337, 4097]

    @pytest.mark.parametrize("listing,expected", [
        (" 4243 /home/opencode/.opencode/bin/opencode\n", (4243, "opencode")),
        ("    1 zsh\n", (1, "zsh")),
        ("", None),
    ])
    def should_read_the_parent_and_name_from_ps(self, load_script, monkeypatch, listing, expected):
        module = load_script("claude-caller")
        monkeypatch.setattr(module.subprocess, "run", lambda command, **_: SimpleNamespace(returncode=0, stdout=listing))

        assert module.parent_and_name(4244) == expected


FAKE_OPENCODE = """
import json, os, subprocess, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SESSIONS = json.loads(os.environ["FAKE_SESSIONS"])
STATUSES = json.loads(os.environ["FAKE_STATUSES"])


class Answer(BaseHTTPRequestHandler):
    def do_GET(self):
        body = STATUSES if self.path == "/session/status" else SESSIONS.get(self.path[len("/session/"):])
        self.send_response(404 if body is None else 200)
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Answer)
threading.Thread(target=server.serve_forever, daemon=True).start()
sys.stdout.write(subprocess.run(["bash", "-c", '"$0"; true', sys.argv[1]], capture_output=True, text=True).stdout)
"""


@skip_on_darwin
@requires_tool("lsof")
def should_name_the_session_of_the_opencode_it_runs_under(tmp_path):
    fake = tmp_path / "opencode"
    fake.write_text(f"#!{sys.executable}{FAKE_OPENCODE}")
    fake.chmod(0o755)
    env = {key: value for key, value in os.environ.items() if key not in {"CLAUDE_CODE_SESSION_ID", "TMUX"}}
    env.update(FAKE_SESSIONS=json.dumps(SESSIONS), FAKE_STATUSES=json.dumps({SUBAGENT: BUSY}))

    result = subprocess.run([str(fake), str(BIN_DIR / "claude-caller")], capture_output=True, text=True, env=env,
                            timeout=30, check=False)

    assert json.loads(result.stdout) == {"session": "G3yIYwxa", "title": "Fix the share page"}


class TestTranscriptScan:
    def should_find_a_title_that_lies_several_chunks_before_the_end(self, caller, transcript, monkeypatch):
        monkeypatch.setattr(caller, "CHUNK_BYTES", 16)
        transcript(title_record("Early title"), *(message_record(f"filler {n}") for n in range(50)))

        assert caller.describe()["title"] == "Early title"

    def should_stop_scanning_at_the_limit_from_the_end(self, caller, transcript, monkeypatch):
        monkeypatch.setattr(caller, "SCAN_LIMIT_BYTES", 200)
        transcript(title_record("Too far back"), *(message_record(f"filler {n}") for n in range(50)))

        assert caller.describe()["title"] == ""

    def should_read_the_first_line_when_the_scan_reaches_the_start(self, caller, transcript, monkeypatch):
        monkeypatch.setattr(caller, "CHUNK_BYTES", 7)
        path = transcript(title_record("Only line"))

        assert list(caller.lines_from_end(path))[-1] == title_record("Only line").encode()


class TestClean:
    @pytest.mark.parametrize("raw,expected", [
        ("Rechnungstag f\u00fcr Saskia", "Rechnungstag f\u00fcr Saskia"),
        ("two\nlines\tand  gaps", "two lines and gaps"),
        ("bidi \u202eevil\u202c and zero\u200bwidth", "bidi evil and zerowidth"),
        ("bell\x07 and escape\x1b[31m", "bell and escape[31m"),
        ("  padded  ", "padded"),
    ])
    def should_keep_only_visible_text_on_one_line(self, caller, raw, expected):
        assert caller.clean(raw) == expected

    def should_clip_a_long_title_with_an_ellipsis(self, caller):
        cleaned = caller.clean("word " * 30)

        assert len(cleaned) == caller.TITLE_LIMIT
        assert cleaned.endswith("\u2026")

    def should_keep_a_title_at_the_limit_whole(self, caller):
        title = "x" * caller.TITLE_LIMIT

        assert caller.clean(title) == title


class TestShellTitle:
    def should_name_the_tmux_window_of_a_shell(self, caller, monkeypatch):
        monkeypatch.setenv("TMUX", "/tmp/tmux-1001/default,123,0")
        monkeypatch.setenv("TMUX_PANE", "%19")
        calls = []

        def fake_run(command, **_):
            calls.append(command)
            return SimpleNamespace(returncode=0, stdout="main:8\n")
        monkeypatch.setattr(caller.subprocess, "run", fake_run)

        assert caller.shell_title() == "shell in tmux main:8"
        assert calls == [["tmux", "-S", "/tmp/tmux-1001/default", "display-message", "-p", "-t", "%19", "#S:#I"]]

    def should_fall_back_to_shell_when_tmux_fails(self, caller, monkeypatch):
        monkeypatch.setenv("TMUX", "/tmp/tmux-1001/default,123,0")
        monkeypatch.setenv("TMUX_PANE", "%19")

        def timed_out(command, **_):
            raise subprocess.TimeoutExpired(command, 1)
        monkeypatch.setattr(caller.subprocess, "run", timed_out)

        assert caller.shell_title() == "shell"


class TestCli:
    def should_print_one_json_line_and_exit_zero(self, run_cli, tmp_path):
        projects = tmp_path / "projects" / "-workspace"
        projects.mkdir(parents=True)
        (projects / f"{SESSION}.jsonl").write_text(title_record("Caf\u00e9 \u2013 notes") + "\n")

        result = run_cli("claude-caller", env_extra={
            "CLAUDE_PROJECTS": str(tmp_path / "projects"), "CLAUDE_CODE_SESSION_ID": str(SESSION),
            "TMUX": "", "TMUX_PANE": ""})

        assert result.returncode == 0
        assert json.loads(result.stdout) == {"session": "48f92bcb", "title": "Caf\u00e9 \u2013 notes"}
        assert result.stdout.isascii()

    def should_exit_zero_when_the_transcript_cannot_be_read(self, run_cli, tmp_path):
        unreadable = tmp_path / "projects" / "-workspace" / f"{SESSION}.jsonl"
        unreadable.mkdir(parents=True)

        result = run_cli("claude-caller", env_extra={
            "CLAUDE_PROJECTS": str(tmp_path / "projects"), "CLAUDE_CODE_SESSION_ID": str(SESSION)})

        assert result.returncode == 0
        assert json.loads(result.stdout) == {"session": "48f92bcb", "title": ""}


def should_keep_the_ellipsis_an_escape_in_source():
    source = (Path(__file__).parent.parent / "claude-caller").read_text()

    assert "\u2026" not in source
