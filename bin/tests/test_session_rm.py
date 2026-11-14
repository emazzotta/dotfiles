import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest

OPENCODE_STORAGE_KINDS = ("session", "message", "part", "session_diff")
OPENCODE_CHILD_TABLES = ("message", "part", "todo", "session_share", "session_entry")
DECLINE_CONFIRMATION = {"gum": "exit 1"}


def _picker(offered: Path, *needles: str) -> dict[str, str]:
    """A picker that records what it was offered and picks the lines naming a needle."""
    pick = f"grep -E -- '{'|'.join(needles)}' \"{offered}\"" if needles else "exit 1"
    return {"picker": f'cat > "{offered}"\n{pick}'}


def _last_columns(offered: Path) -> list[str]:
    return [line.split()[-1] for line in offered.read_text().splitlines()]


@pytest.fixture
def offered(tmp_path):
    return tmp_path / "offered"


def _seed_db(db_path: Path, sessions):
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE session (id TEXT PRIMARY KEY, project_id TEXT, slug TEXT, directory TEXT,
                              title TEXT, version TEXT, time_created INTEGER, time_updated INTEGER);
        CREATE TABLE message (id TEXT, session_id TEXT, time_created INTEGER, time_updated INTEGER, data TEXT);
        CREATE TABLE part (id TEXT, message_id TEXT, session_id TEXT, time_created INTEGER, time_updated INTEGER, data TEXT);
        CREATE TABLE todo (session_id TEXT, content TEXT, status TEXT, priority INTEGER, position INTEGER,
                           time_created INTEGER, time_updated INTEGER);
        CREATE TABLE session_share (session_id TEXT, id TEXT, secret TEXT, url TEXT, time_created INTEGER, time_updated INTEGER);
        CREATE TABLE session_entry (id TEXT, session_id TEXT, type TEXT, time_created INTEGER, time_updated INTEGER, data TEXT);
    """)
    for sid, title, tu in sessions:
        conn.execute("INSERT INTO session VALUES (?, 'p', 's', '/', ?, '1', ?, ?)", (sid, title, tu, tu))
        conn.execute("INSERT INTO message VALUES ('m_'||?, ?, ?, ?, '{}')", (sid, sid, tu, tu))
        conn.execute("INSERT INTO part VALUES ('pt_'||?, 'm_'||?, ?, ?, ?, '{}')", (sid, sid, sid, tu, tu))
        conn.execute("INSERT INTO todo VALUES (?, 'x', 'done', 1, 1, ?, ?)", (sid, tu, tu))
        conn.execute("INSERT INTO session_share VALUES (?, 'ss_'||?, 'sec', 'u', ?, ?)", (sid, sid, tu, tu))
        conn.execute("INSERT INTO session_entry VALUES ('e_'||?, ?, 't', ?, ?, '{}')", (sid, sid, tu, tu))
    conn.commit()
    conn.close()


def _seed_storage(storage: Path, session_ids):
    for sid in session_ids:
        for kind in OPENCODE_STORAGE_KINDS:
            directory = storage / kind / sid
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "a.json").write_text("{}")


def _session_ids(db: Path) -> list[str]:
    with closing(sqlite3.connect(db)) as conn:
        return [row[0] for row in conn.execute("SELECT id FROM session ORDER BY id")]


def _child_rows(db: Path, session_id: str) -> list[int]:
    with closing(sqlite3.connect(db)) as conn:
        return [
            conn.execute(f"SELECT COUNT(*) FROM {table} WHERE session_id = ?", (session_id,)).fetchone()[0]
            for table in OPENCODE_CHILD_TABLES
        ]


class TestOpencodeRm:
    @pytest.fixture
    def opencode(self, tmp_path, run_cli, offered):
        db, storage = tmp_path / "opencode.db", tmp_path / "storage"

        def _run(*args, pick=(), mocks=None):
            return run_cli(
                "opencode-rm", list(args),
                env_extra={"OPENCODE_DB": str(db), "OPENCODE_STORAGE": str(storage)},
                mock_bins={**_picker(offered, *pick), **(mocks or {})},
            )

        return SimpleNamespace(run=_run, db=db, storage=storage)

    def should_delete_the_picked_session_from_database_and_storage(self, opencode):
        _seed_db(opencode.db, [("ses_keep", "Keep", 2000), ("ses_drop", "Drop", 1000)])
        _seed_storage(opencode.storage, ["ses_keep", "ses_drop"])

        result = opencode.run("-y", pick=["ses_drop"])

        assert result.returncode == 0, result.stderr
        assert _session_ids(opencode.db) == ["ses_keep"]
        assert _child_rows(opencode.db, "ses_drop") == [0] * len(OPENCODE_CHILD_TABLES)
        assert _child_rows(opencode.db, "ses_keep") == [1] * len(OPENCODE_CHILD_TABLES)
        for kind in OPENCODE_STORAGE_KINDS:
            assert not (opencode.storage / kind / "ses_drop").exists()
            assert (opencode.storage / kind / "ses_keep").is_dir()

    def should_keep_every_session_when_the_confirmation_is_declined(self, opencode):
        _seed_db(opencode.db, [("ses_keep", "Keep", 2000), ("ses_drop", "Drop", 1000)])
        _seed_storage(opencode.storage, ["ses_drop"])

        result = opencode.run(pick=["ses_drop"], mocks=DECLINE_CONFIRMATION)

        assert result.returncode == 1
        assert _session_ids(opencode.db) == ["ses_drop", "ses_keep"]
        assert (opencode.storage / "session" / "ses_drop").is_dir()

    def should_offer_sessions_newest_first(self, opencode, offered):
        _seed_db(opencode.db, [("old", "t", 1000), ("new", "t", 3000), ("mid", "t", 2000)])

        opencode.run()

        assert _last_columns(offered) == ["new", "mid", "old"]

    def should_offer_only_sessions_whose_title_matches_the_search(self, opencode, offered):
        _seed_db(opencode.db, [("a", "alpha", 1000), ("b", "gamma", 2000)])

        opencode.run("ALP")

        assert _last_columns(offered) == ["a"]

    def should_print_usage_for_the_help_flag(self, opencode):
        result = opencode.run("-h")

        assert result.returncode == 0
        assert "Usage:" in result.stdout


def _write_session(project: Path, sid: str, content="hello", mtime: float = 1000.0) -> tuple[Path, Path]:
    project.mkdir(parents=True, exist_ok=True)
    transcript = project / f"{sid}.jsonl"
    transcript.write_text(
        json.dumps({"type": "permission-mode", "sessionId": sid}) + "\n"
        + json.dumps({"type": "user", "message": {"role": "user", "content": content}}) + "\n"
    )
    os.utime(transcript, (mtime, mtime))
    state = project / sid
    state.mkdir()
    (state / "todos.json").write_text("[]")
    return transcript, state


class TestClaudeRm:
    @pytest.fixture
    def claude(self, tmp_path, run_cli, offered):
        projects = tmp_path / "projects"
        workdir = (tmp_path / "work").resolve()
        workdir.mkdir()

        def _run(*args, pick=(), mocks=None):
            return run_cli(
                "claude-rm", list(args),
                env_extra={"CLAUDE_PROJECTS": str(projects)},
                mock_bins={**_picker(offered, *pick), **(mocks or {})},
                cwd=workdir,
            )

        current = projects / str(workdir).replace("/", "-")
        return SimpleNamespace(run=_run, projects=projects, current=current)

    def should_delete_the_transcript_and_state_directory_of_the_picked_session(self, claude):
        kept_transcript, kept_state = _write_session(claude.current, "keep")
        transcript, state = _write_session(claude.current, "drop")

        result = claude.run("-y", pick=["drop.jsonl"])

        assert result.returncode == 0, result.stderr
        assert not transcript.exists()
        assert not state.exists()
        assert kept_transcript.is_file()
        assert kept_state.is_dir()

    def should_keep_every_session_when_the_confirmation_is_declined(self, claude):
        transcript, state = _write_session(claude.current, "drop")

        result = claude.run(pick=["drop.jsonl"], mocks=DECLINE_CONFIRMATION)

        assert result.returncode == 1
        assert transcript.is_file()
        assert state.is_dir()

    def should_not_offer_subagent_transcripts(self, claude, offered):
        _, state = _write_session(claude.current, "s1")
        (state / "subagents").mkdir()
        (state / "subagents" / "agent-x.jsonl").write_text("{}")

        claude.run()

        assert _last_columns(offered) == [str(claude.current / "s1.jsonl")]

    def should_offer_only_the_current_project_by_default(self, claude, offered):
        _write_session(claude.current, "here")
        _write_session(claude.projects / "-elsewhere", "there")

        claude.run()

        assert _last_columns(offered) == [str(claude.current / "here.jsonl")]

    def should_offer_every_project_newest_first_with_the_all_flag(self, claude, offered):
        _write_session(claude.projects / "-a", "older", mtime=1000)
        _write_session(claude.projects / "-b", "newer", mtime=2000)

        claude.run("-a")

        assert [Path(path).stem for path in _last_columns(offered)] == ["newer", "older"]

    def should_offer_only_sessions_whose_first_message_matches_the_search(self, claude, offered):
        _write_session(claude.current, "login", content="Fix the Login bug")
        _write_session(claude.current, "docs", content="write docs")

        claude.run("login bug")

        assert _last_columns(offered) == [str(claude.current / "login.jsonl")]

    @pytest.mark.parametrize("content,title", [
        ("plain", "plain"),
        ([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}], "a b"),
        ([], "(no prompt)"),
        ([{"type": "image", "source": {}}], "(no prompt)"),
    ])
    def should_title_a_session_with_its_first_user_message(self, claude, offered, content, title):
        _write_session(claude.current, "s1", content=content)

        claude.run()

        assert offered.read_text().startswith(f"{title} ")

    def should_print_usage_for_the_help_flag(self, claude):
        result = claude.run("-h")

        assert result.returncode == 0
        assert "Usage:" in result.stdout
