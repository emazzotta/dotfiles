import json
from uuid import UUID

import pytest

from bin.tests.conftest import BIN_DIR

SESSION = UUID("48f92bcb-f080-4149-8046-a7e1df07fef5")


def title_record(title):
    return json.dumps({"type": "ai-title", "aiTitle": title, "sessionId": str(SESSION)})


def message_record(text):
    return json.dumps({"type": "user", "message": {"content": text}})


@pytest.fixture
def titles(load_module, monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PROJECTS", str(tmp_path / "projects"))
    return load_module("session_title")


@pytest.fixture
def transcript(tmp_path):
    def _write(*records):
        path = tmp_path / "projects" / "-workspace" / f"{SESSION}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"{record}\n" for record in records))
        return path
    return _write


class TestFind:
    def should_give_the_latest_title_in_the_transcript(self, titles, transcript):
        transcript(title_record("First title"), message_record("hello"), title_record("Latest title"))

        assert titles.find(SESSION) == "Latest title"

    def should_give_an_empty_title_when_no_transcript_exists(self, titles):
        assert titles.find(SESSION) == ""

    def should_give_an_empty_title_when_the_transcript_cannot_be_read(self, titles, tmp_path):
        (tmp_path / "projects" / "-workspace" / f"{SESSION}.jsonl").mkdir(parents=True)

        assert titles.find(SESSION) == ""

    def should_skip_a_line_that_mentions_the_title_type_but_is_no_title_record(self, titles, transcript):
        transcript(title_record("Real title"), message_record('"ai-title" in prose'), "{broken ai-title")

        assert titles.find(SESSION) == "Real title"


class TestTranscriptScan:
    def should_find_a_title_that_lies_several_chunks_before_the_end(self, titles, transcript, monkeypatch):
        monkeypatch.setattr(titles, "CHUNK_BYTES", 16)
        transcript(title_record("Early title"), *(message_record(f"filler {n}") for n in range(50)))

        assert titles.find(SESSION) == "Early title"

    def should_stop_scanning_at_the_limit_from_the_end(self, titles, transcript, monkeypatch):
        monkeypatch.setattr(titles, "SCAN_LIMIT_BYTES", 200)
        transcript(title_record("Too far back"), *(message_record(f"filler {n}") for n in range(50)))

        assert titles.find(SESSION) == ""

    def should_read_the_first_line_when_the_scan_reaches_the_start(self, titles, transcript, monkeypatch):
        monkeypatch.setattr(titles, "CHUNK_BYTES", 7)
        path = transcript(title_record("Only line"))

        assert list(titles.lines_from_end(path))[-1] == title_record("Only line").encode()


class TestClean:
    @pytest.mark.parametrize("raw,expected", [
        ("Rechnungstag f\u00fcr Saskia", "Rechnungstag f\u00fcr Saskia"),
        ("two\nlines\tand  gaps", "two lines and gaps"),
        ("bidi \u202eevil\u202c and zero\u200bwidth", "bidi evil and zerowidth"),
        ("bell\x07 and escape\x1b[31m", "bell and escape[31m"),
        ("  padded  ", "padded"),
    ])
    def should_keep_only_visible_text_on_one_line(self, titles, raw, expected):
        assert titles.clean(raw) == expected

    def should_clip_a_long_title_with_an_ellipsis(self, titles):
        cleaned = titles.clean("word " * 30)

        assert len(cleaned) == titles.TITLE_LIMIT
        assert cleaned.endswith("\u2026")

    def should_keep_a_title_at_the_limit_whole(self, titles):
        title = "x" * titles.TITLE_LIMIT

        assert titles.clean(title) == title


def should_keep_the_ellipsis_an_escape_in_source():
    source = (BIN_DIR / "session_title.py").read_text()

    assert "\u2026" not in source
