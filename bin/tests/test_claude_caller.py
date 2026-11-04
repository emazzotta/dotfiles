import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

SESSION = UUID("48f92bcb-f080-4149-8046-a7e1df07fef5")


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
    return module


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
