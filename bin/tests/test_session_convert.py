import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

SCHEMA = """
CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT, time_updated INTEGER);
CREATE TABLE message (id TEXT, session_id TEXT, time_created INTEGER, data TEXT);
CREATE TABLE part (id TEXT, message_id TEXT, time_created INTEGER, data TEXT);
"""
DEFAULT_DATABASE = Path(".local") / "share" / "opencode" / "opencode.db"


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "opencode.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO session VALUES ('older', 'Older work', 1000000)")
        conn.execute("INSERT INTO session VALUES ('newer', NULL, 2000000)")
        conn.execute("INSERT INTO message VALUES ('m1', 'older', 1, ?)", (json.dumps({"role": "user"}),))
        conn.execute("INSERT INTO part VALUES ('p1', 'm1', 1, ?)", (json.dumps({"type": "text", "text": "hello"}),))
        conn.commit()
    return path


@pytest.fixture
def convert(load_script, monkeypatch, database):
    monkeypatch.setenv("OPENCODE_DB", str(database))
    return load_script("session-convert")


class TestOpencodeDatabasePath:
    def test_should_read_the_path_from_the_environment(self, convert, database):
        assert convert.OPENCODE_DB_PATH == database

    def test_should_default_to_the_user_data_directory(self, load_script, monkeypatch, tmp_path):
        monkeypatch.delenv("OPENCODE_DB", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))

        module = load_script("session-convert")

        assert module.OPENCODE_DB_PATH == tmp_path / DEFAULT_DATABASE


class TestOpencodeSessions:
    def test_should_list_the_sessions_of_that_database_newest_first(self, convert):
        sessions = convert.list_opencode_sessions()

        assert [(s.id, s.title) for s in sessions] == [("newer", "Untitled"), ("older", "Older work")]

    def test_should_list_nothing_when_the_database_is_missing(self, convert, monkeypatch, tmp_path):
        monkeypatch.setattr(convert, "OPENCODE_DB_PATH", tmp_path / "gone.db")

        assert convert.list_opencode_sessions() == []

    def test_should_read_the_messages_of_a_session_from_that_database(self, convert):
        session = convert.parse_opencode_session("older")

        assert [(m.role, m.text) for m in session.messages] == [("user", "hello")]


class TestRunAsScript:
    def test_should_export_an_opencode_session_to_markdown_in_the_current_directory(
            self, run_cli, database, tmp_path):
        workdir = tmp_path / "work"
        workdir.mkdir()

        result = run_cli("session-convert", env_extra={"OPENCODE_DB": str(database), "HOME": str(tmp_path)},
                         mock_bins={"gum": "exit 1"}, stdin="4\n2\n", cwd=workdir)

        assert result.returncode == 0, result.stderr
        exported = (workdir / "session-older.md").read_text().splitlines()
        assert [exported[0], exported[1], *exported[4:7]] == ["# Session: Older work", "Source ID: older",
                                                               "## User", "", "hello"]
