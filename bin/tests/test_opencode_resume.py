import json
import sqlite3

import pytest

SCHEMA = """
CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT, time_created INTEGER, time_updated INTEGER);
CREATE TABLE message (id TEXT, session_id TEXT, time_created INTEGER, data TEXT);
CREATE TABLE part (id TEXT, message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT);
"""


def compact(payload):
    """opencode stores compact JSON - the content query filters on `"type":"text"`."""
    return json.dumps(payload, separators=(",", ":"))


def seed(db_path, sessions):
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    for sid, title, updated_ms, turns in sessions:
        conn.execute("INSERT INTO session VALUES (?, ?, ?, ?)", (sid, title, updated_ms, updated_ms))
        for order, (role, text) in enumerate(turns):
            conn.execute("INSERT INTO message VALUES (?, ?, ?, ?)",
                         (f"m{sid}{order}", sid, order, compact({"role": role})))
            conn.execute("INSERT INTO part VALUES (?, ?, ?, ?, ?)",
                         (f"p{sid}{order}", f"m{sid}{order}", sid, order,
                          compact({"type": "text", "text": text})))
    conn.commit()
    conn.close()


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "opencode.db"
    seed(path, [
        ("adjacent", "fix the DOCKER compose stack", 1_000_000, [("user", "fix the DOCKER compose stack")]),
        ("scattered", "docker is fine", 2_000_000, [("user", "docker is fine"), ("assistant", "we compose later")]),
        ("unrelated", "something else", 3_000_000, [("user", "something else entirely")]),
    ])
    return path


@pytest.fixture
def resume(load_script, monkeypatch, db, tmp_path):
    monkeypatch.setenv("OPENCODE_DB", str(db))
    module = load_script("opencode-resume")
    monkeypatch.setattr(module, "CACHE_PATH", tmp_path / "cache.tsv")
    return module


def ids_of(output):
    return [line.split("\t")[1] for line in output.splitlines()]


class TestIndexing:
    def test_should_index_every_session_from_the_database(self, resume):
        assert {s.sid for s in resume.build_sessions()} == {"adjacent", "scattered", "unrelated"}

    def test_should_lowercase_indexed_content_for_searching(self, resume):
        content = {s.sid: s.content_lower for s in resume.build_sessions()}

        assert "docker compose" in content["adjacent"]

    def test_should_convert_millisecond_timestamps_to_seconds(self, resume):
        updated = {s.sid: s.updated_at for s in resume.build_sessions()}

        assert updated["unrelated"] == 3000

    def test_should_reuse_the_cache_when_time_updated_is_unchanged(self, resume):
        resume.build_sessions()

        assert {s.sid for s in resume.load_sessions()} == {"adjacent", "scattered", "unrelated"}


class TestSearchCommand:
    def test_should_rank_adjacent_words_above_scattered_words(self, resume, capsys):
        resume.build_sessions()

        resume.cmd_search("docker compose", count=10)

        assert ids_of(capsys.readouterr().out) == ["adjacent", "scattered"]

    def test_should_print_nothing_when_nothing_matches(self, resume, capsys):
        resume.build_sessions()

        resume.cmd_search("nonexistent-token", count=10)

        assert capsys.readouterr().out == ""


class TestPreview:
    def test_should_render_turns_with_role_labels(self, resume):
        rendered = resume.render_preview("scattered")

        assert "user" in rendered and "assistant" in rendered

    def test_should_highlight_query_tokens(self, resume, load_script):
        picker = load_script("session_picker.py")

        assert picker.HIGHLIGHT_ON in resume.render_preview("adjacent", "compose")

    def test_should_report_a_missing_session_without_raising(self, resume):
        assert "not found" in resume.render_preview("nope")

    def test_should_report_a_missing_database_without_raising(self, resume, monkeypatch, tmp_path):
        monkeypatch.setattr(resume, "DB_PATH", tmp_path / "gone.db")

        assert "not found" in resume.render_preview("adjacent")
