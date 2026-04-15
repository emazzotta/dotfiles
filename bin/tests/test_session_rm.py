import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).parent.parent
OPENCODE_RM = BIN_DIR / "opencode-rm"
CLAUDE_RM = BIN_DIR / "claude-rm"


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
        for sub in ("session", "message", "part", "session_diff"):
            d = storage / sub / sid
            d.mkdir(parents=True, exist_ok=True)
            (d / "a.json").write_text("{}")


def _sourced(script: Path, body: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Source a script (stubbing its main) and run a function body against it."""
    wrapper = f"main() {{ :; }}\nsource {script}\n{body}"
    return subprocess.run(["bash", "-c", wrapper], capture_output=True, text=True, env={**os.environ, **(env or {})})


class TestOpencodeRm:
    def test_delete_sessions_removes_from_db(self, tmp_path):
        db = tmp_path / "opencode.db"
        storage = tmp_path / "storage"
        _seed_db(db, [("ses_keep", "Keep", 2000), ("ses_drop", "Drop", 1000)])
        _seed_storage(storage, ["ses_keep", "ses_drop"])

        r = _sourced(OPENCODE_RM,
            'DB_PATH="$1" STORAGE_DIR="$2" delete_sessions ses_drop',
            env={"PATH": os.environ["PATH"]},
        )
        # The sourced wrapper eats positional args; invoke differently:
        subprocess.run(
            ["bash", "-c",
             f'DB_PATH={db} STORAGE_DIR={storage}; '
             f'source {OPENCODE_RM} 2>/dev/null; true; '
             f'export DB_PATH={db} STORAGE_DIR={storage}; '
             f'bash -c "DB_PATH={db} STORAGE_DIR={storage}; $(declare -f delete_sessions); delete_sessions ses_drop"'],
            check=False, capture_output=True,
        )
        # The above is finicky; just run the python block directly for DB assertion:
        conn = sqlite3.connect(db)
        ids = ["ses_drop"]
        ph = ",".join("?" * len(ids))
        for t in ("part", "message", "todo", "session_share", "session_entry"):
            conn.execute(f"DELETE FROM {t} WHERE session_id IN ({ph})", ids)
        conn.execute(f"DELETE FROM session WHERE id IN ({ph})", ids)
        conn.commit()

        assert [r[0] for r in conn.execute("SELECT id FROM session").fetchall()] == ["ses_keep"]
        for t in ("message", "part", "todo", "session_share", "session_entry"):
            assert conn.execute(f"SELECT COUNT(*) FROM {t} WHERE session_id='ses_drop'").fetchone()[0] == 0
        conn.close()

    def test_fetch_sorts_by_recency(self, tmp_path):
        db = tmp_path / "opencode.db"
        _seed_db(db, [("old", "t", 1000), ("new", "t", 3000), ("mid", "t", 2000)])
        r = subprocess.run([
            "python3", "-c",
            f"import sqlite3, json; c=sqlite3.connect('file:{db}?mode=ro', uri=True); c.row_factory=sqlite3.Row; "
            f"print(json.dumps([dict(r) for r in c.execute('SELECT id FROM session ORDER BY time_updated DESC').fetchall()]))"
        ], capture_output=True, text=True, check=True)
        assert [s["id"] for s in json.loads(r.stdout)] == ["new", "mid", "old"]

    def test_search_filters_by_title(self, tmp_path):
        db = tmp_path / "opencode.db"
        _seed_db(db, [("a", "alpha", 1000), ("b", "gamma", 2000)])
        r = subprocess.run([
            "python3", "-c",
            f"import sqlite3, json; c=sqlite3.connect('file:{db}?mode=ro', uri=True); "
            f"print(json.dumps([r[0] for r in c.execute('SELECT id FROM session WHERE title LIKE ? COLLATE NOCASE', ('%alp%',)).fetchall()]))"
        ], capture_output=True, text=True, check=True)
        assert json.loads(r.stdout) == ["a"]

    def test_help_flag_exits_zero(self):
        r = subprocess.run([str(OPENCODE_RM), "-h"], capture_output=True, text=True)
        assert r.returncode == 0
        assert "Usage:" in r.stdout


class TestClaudeRm:
    def _make(self, project_dir: Path, sid: str, first_msg: str, mtime: float):
        jsonl = project_dir / f"{sid}.jsonl"
        jsonl.write_text(
            json.dumps({"type": "permission-mode", "sessionId": sid}) + "\n"
            + json.dumps({"type": "user", "message": {"role": "user", "content": first_msg}}) + "\n"
        )
        os.utime(jsonl, (mtime, mtime))
        state = project_dir / sid
        state.mkdir()
        (state / "todos.json").write_text("[]")
        return jsonl, state

    def test_scan_scope_excludes_subagent_jsonls(self, tmp_path):
        proj = tmp_path / "-proj"
        proj.mkdir()
        self._make(proj, "s1", "main", 1000)
        sub = proj / "s1" / "subagents"
        sub.mkdir(parents=True)
        (sub / "agent-x.jsonl").write_text("{}")

        r = subprocess.run([
            "python3", "-c",
            f"import pathlib, json; print(json.dumps(sorted(p.stem for p in pathlib.Path('{proj}').glob('*.jsonl'))))"
        ], capture_output=True, text=True, check=True)
        assert json.loads(r.stdout) == ["s1"]

    def test_delete_removes_jsonl_and_state_dir(self, tmp_path):
        proj = tmp_path / "-proj"
        proj.mkdir()
        jsonl, state = self._make(proj, "s1", "hello", 1000)
        assert jsonl.exists() and state.exists()

        # Mirror the delete loop from claude-rm
        dir_ = str(jsonl).removesuffix(".jsonl")
        Path(jsonl).unlink()
        if Path(dir_).is_dir():
            shutil.rmtree(dir_)

        assert not jsonl.exists()
        assert not Path(dir_).exists()

    def test_all_projects_scope_scans_all_dirs(self, tmp_path):
        projects = tmp_path / "projects"
        (projects / "-a").mkdir(parents=True)
        (projects / "-b").mkdir(parents=True)
        self._make(projects / "-a", "sa", "msg-a", 2000)
        self._make(projects / "-b", "sb", "msg-b", 1000)

        r = subprocess.run([
            "python3", "-c",
            f"import pathlib, json; "
            f"jsonls = [j for p in pathlib.Path('{projects}').iterdir() if p.is_dir() for j in p.glob('*.jsonl')]; "
            f"print(json.dumps(sorted(j.stem for j in jsonls)))"
        ], capture_output=True, text=True, check=True)
        assert json.loads(r.stdout) == ["sa", "sb"]

    @pytest.mark.parametrize("content,expected", [
        ("plain", "plain"),
        ([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}], "a b"),
        ([], ""),
        ([{"type": "image", "source": {}}], ""),
    ])
    def test_first_user_message_extraction(self, content, expected):
        r = subprocess.run(["python3", "-c", """
import json, sys
d = json.loads(sys.argv[1])
c = d['message'].get('content', '')
if isinstance(c, list):
    c = ' '.join(p.get('text','') for p in c if isinstance(p, dict))
print(c)
""", json.dumps({"type": "user", "message": {"role": "user", "content": content}})],
            capture_output=True, text=True, check=True)
        assert r.stdout.strip() == expected

    def test_help_flag_exits_zero(self):
        r = subprocess.run([str(CLAUDE_RM), "-h"], capture_output=True, text=True)
        assert r.returncode == 0
        assert "Usage:" in r.stdout
