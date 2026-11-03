import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

BIN_DIR = Path(__file__).resolve().parent.parent

STARTED = datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc)
FIRST_ID = UUID("1ebc7b46-f767-43d8-8507-f16442fb591f")
CLEARED_ID = UUID("12628732-a407-4733-9384-f014ec3a4d00")
POD_DOMAIN = "linux:f229:pid:[4026533355]"
OTHER_CONTAINER = "linux:f229:pid:[4026531111]"


@pytest.fixture
def registry_module(load_module):
    return load_module("session_registry")


@pytest.fixture
def make_record(registry_module, tmp_path):
    def _make(**overrides):
        defaults = {
            "session_id": FIRST_ID,
            "cwd": tmp_path,
            "cl_args": ("-s", "--model", "opus"),
            "tmux_session": "work",
            "started_at": STARTED,
        }
        return registry_module.SessionRecord(**(defaults | overrides))
    return _make


@pytest.fixture
def registry(registry_module, tmp_path):
    return registry_module.Registry(tmp_path / "registry", tmp_path / "processes", tmp_path / "transcripts")


@pytest.fixture
def tmux_calls(registry_module, monkeypatch):
    calls = []

    def fake_tmux(*args):
        calls.append(args)
        return "%7" if "-P" in args else ""

    monkeypatch.setattr(registry_module, "_tmux", fake_tmux)
    monkeypatch.setattr(registry_module, "_has_tmux_session", lambda name: name == "work")
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("TMUX_PANE", raising=False)
    return calls


@pytest.fixture
def tmux_server(registry_module, monkeypatch):
    """Answers each poll for the tmux server in turn, repeating the last answer."""
    def _answer(*running: bool):
        answers = list(running)
        monkeypatch.setattr(registry_module, "_tmux_server_running", lambda: answers.pop(0) if len(answers) > 1 else answers[0])
    monkeypatch.setattr(registry_module, "TMUX_EXIT_GRACE", timedelta(milliseconds=50))
    monkeypatch.setattr(registry_module, "TMUX_POLL_INTERVAL", timedelta(0))
    return _answer


@pytest.fixture
def private_tmux(tmp_path, monkeypatch):
    """A server of its own whose windows run cat, so a typed command is echoed, never run.

    tmux picks the socket in $TMUX over TMUX_TMPDIR: drop it, or the tests drive the caller's server.
    """
    socket_dir = tmp_path / "tmux"
    socket_dir.mkdir()
    monkeypatch.setenv("TMUX_TMPDIR", str(socket_dir))
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("TMUX_PANE", raising=False)
    subprocess.run(["tmux", "-f", os.devnull, "new-session", "-d", "-s", "work", "cat"], check=True)
    subprocess.run(["tmux", "set", "-g", "default-command", "cat"], check=True)
    yield
    subprocess.run(["tmux", "kill-server"], capture_output=True, check=False)


def write_process_file(directory: Path, pid: int, session_id: UUID, started: datetime, domain: str = POD_DOMAIN):
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"pid": pid, "sessionId": str(session_id), "startedAt": int(started.timestamp() * 1000), "pidDomain": domain}
    (directory / f"{pid}.json").write_text(json.dumps(payload))


def write_transcript(registry, session_id: UUID) -> None:
    registry.transcripts.mkdir(parents=True, exist_ok=True)
    (registry.transcripts / f"{session_id}.jsonl").write_text("{}\n")


def records_in(registry) -> list[dict]:
    return [json.loads(path.read_text()) for path in sorted(registry.directory.glob("*.json"))]


class TestSessionRecord:
    def test_should_survive_a_round_trip_through_json(self, registry_module, make_record):
        record = make_record()

        assert registry_module.SessionRecord.from_json(record.to_json()) == record

    def test_should_keep_a_session_not_yet_picked_as_none(self, registry_module, make_record):
        record = make_record(session_id=None, tmux_session=None)

        assert registry_module.SessionRecord.from_json(record.to_json()) == record

    def test_should_keep_the_pane_pid_mounts_and_run_folder_through_json(self, registry_module, make_record, tmp_path):
        mount = registry_module.Mount(tmp_path / "web-terminal", "/workspace/code/web-terminal")
        record = make_record(tmux_pane="%12", pid=4242, mounts=(mount,), claude_sessions=tmp_path / "run")

        assert registry_module.SessionRecord.from_json(record.to_json()) == record

    def test_should_read_a_record_written_before_the_pane_was_kept(self, registry_module, make_record):
        old = json.loads(make_record().to_json())
        for key in ("tmuxPane", "pid", "mounts", "claudeSessions"):
            del old[key]

        record = registry_module.SessionRecord.from_json(json.dumps(old))

        assert (record.tmux_pane, record.pid, record.mounts, record.claude_sessions) == (None, None, (), None)

    def test_should_quote_the_resume_command_for_the_shell(self, make_record):
        record = make_record(cl_args=("-p", "/tmp/my project", "--model", "opus"))

        assert record.resume_command() == f"cl -r {FIRST_ID} -p '/tmp/my project' --model opus"


class TestSignalOf:
    @pytest.mark.parametrize(("returncode", "expected"), [
        (0, None),
        (1, None),
        (-signal.SIGKILL, signal.SIGKILL),
        (128 + signal.SIGKILL, signal.SIGKILL),
        (128 + signal.SIGINT, signal.SIGINT),
        (255, None),
    ])
    def test_should_name_the_signal_behind_an_exit_status(self, registry_module, returncode, expected):
        assert registry_module.signal_of(returncode) == expected


class TestEndedByUser:
    @pytest.mark.parametrize(("signum", "in_tmux", "expected"), [
        (None, False, True),
        (signal.SIGINT, False, True),
        (signal.SIGHUP, True, True),
        (signal.SIGHUP, False, False),
        (signal.SIGTERM, True, False),
        (signal.SIGKILL, True, False),
    ], ids=["exited", "interrupted-key", "tmux-window-closed", "connection-dropped", "terminated", "killed"])
    def test_should_tell_a_deliberate_end_from_an_interruption(self, registry_module, tmux_server, signum, in_tmux, expected):
        tmux_server(True)

        assert registry_module.ended_by_user(signum, in_tmux) is expected

    @pytest.mark.parametrize("running", [(False,), (True, True, False)], ids=["already-gone", "gone-a-moment-later"])
    def test_should_count_a_hangup_from_a_dying_tmux_server_as_an_interruption(self, registry_module, tmux_server, running):
        tmux_server(*running)

        assert registry_module.ended_by_user(signal.SIGHUP, in_tmux=True) is False


class TestTrackedSession:
    def test_should_hold_the_record_so_restore_cannot_claim_it_while_cl_runs(self, registry, registry_module, make_record):
        with registry.track(make_record()):
            path = next(registry.directory.glob("*.json"))

            assert registry_module._Claim.take(path) is None

    def test_should_remove_the_record_when_the_session_exits_on_its_own(self, registry, make_record):
        with registry.track(make_record()) as session:
            session.finish(None)

        assert not list(registry.directory.iterdir())

    @pytest.mark.parametrize(("signum", "tmux_session", "tmux_running", "kept"), [
        (signal.SIGHUP, "work", True, False),
        (signal.SIGHUP, "work", False, True),
        (signal.SIGHUP, None, False, True),
        (signal.SIGTERM, "work", True, True),
    ], ids=["ctrl-q-in-tmux", "tmux-server-died", "ssh-dropped", "terminated"])
    def test_should_keep_only_records_of_interrupted_sessions(
        self, registry, make_record, tmux_server, signum, tmux_session, tmux_running, kept
    ):
        tmux_server(tmux_running)
        with registry.track(make_record(tmux_session=tmux_session)) as session:
            session.finish(signum)

        assert bool(records_in(registry)) is kept

    def test_should_remove_the_run_folder_with_the_record_of_a_session_that_ended(self, registry, make_record, tmp_path):
        run = tmp_path / "run"
        run.mkdir()
        (run / "1.json").write_text("{}")

        with registry.track(make_record(claude_sessions=run)) as session:
            session.finish(None)

        assert not run.exists()

    def test_should_keep_the_run_folder_of_an_interrupted_session_for_restore(self, registry, make_record, tmp_path):
        run = tmp_path / "run"
        run.mkdir()

        with registry.track(make_record(claude_sessions=run)) as session:
            session.finish(signal.SIGTERM)

        assert run.is_dir()

    def test_should_log_the_folder_of_each_conversation_the_session_shows(self, registry_module, make_record, tmp_path):
        log = tmp_path / "conversations.tsv"
        registry = registry_module.Registry(tmp_path / "registry", tmp_path / "processes", tmp_path / "transcripts", log)

        with registry.track(make_record()) as session:
            session._update(CLEARED_ID)
            session.finish(None)

        assert log.read_text() == f"{FIRST_ID}\t{tmp_path}\n{CLEARED_ID}\t{tmp_path}\n"

    def test_should_settle_a_session_only_once(self, registry, make_record):
        with registry.track(make_record()) as session:
            session.finish(signal.SIGTERM)
            session.finish(None)

        assert records_in(registry)

    def test_should_record_the_session_claude_switched_to(self, registry, make_record):
        with registry.track(make_record()) as session:
            session._update(CLEARED_ID)

            assert records_in(registry)[0]["sessionId"] == str(CLEARED_ID)

    def test_should_not_track_a_launch_without_a_record(self, registry, registry_module):
        assert registry.track(None) is registry_module.UNTRACKED

    def test_should_still_launch_when_the_record_cannot_be_written(self, registry, registry_module, make_record, tmp_path):
        blocked = tmp_path / "blocked"
        blocked.write_text("")
        unwritable = registry_module.Registry(blocked / "registry", registry.claude_processes, registry.transcripts)

        assert unwritable.track(make_record()) is registry_module.UNTRACKED


class TestRecordSurvivesAKill:
    HOLD_RECORD = (
        "import sys, time\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import session_registry as r\n"
        "from datetime import datetime, timezone\n"
        "from pathlib import Path\n"
        "record = r.SessionRecord(None, Path('.'), (), 'work', datetime.now(timezone.utc))\n"
        "session = r.Registry(Path(sys.argv[2]), Path(sys.argv[2]), Path(sys.argv[2])).track(record)\n"
        "print('ready', flush=True)\n"
        "time.sleep(30)\n"
    )

    @pytest.mark.slow
    def test_should_leave_a_claimable_record_when_cl_is_killed(self, registry_module, tmp_path):
        holder = subprocess.Popen(
            [sys.executable, "-c", self.HOLD_RECORD, str(BIN_DIR), str(tmp_path)],
            stdout=subprocess.PIPE, text=True,
        )
        assert holder.stdout.readline().strip() == "ready"
        path = next(tmp_path.glob("*.json"))
        assert registry_module._Claim.take(path) is None

        holder.kill()
        holder.wait()

        claim = registry_module._Claim.take(path)
        assert claim is not None
        assert claim.record().tmux_session == "work"
        claim.release(discard=True)


class TestClaudeProcess:
    def test_should_read_the_session_from_the_file_of_a_known_pid(self, registry_module, tmp_path):
        write_process_file(tmp_path, 4242, CLEARED_ID, STARTED + timedelta(seconds=1))
        process = registry_module.ClaudeProcess(tmp_path, STARTED, 4242, FIRST_ID)

        assert process.session_id() == CLEARED_ID

    def test_should_ignore_a_file_left_by_an_earlier_process_with_that_pid(self, registry_module, tmp_path):
        write_process_file(tmp_path, 4242, CLEARED_ID, STARTED - timedelta(days=3))
        process = registry_module.ClaudeProcess(tmp_path, STARTED, 4242, FIRST_ID)

        assert process.session_id() is None

    def test_should_find_the_file_by_session_and_keep_following_it_after_clear(self, registry_module, tmp_path):
        write_process_file(tmp_path, 7, FIRST_ID, STARTED + timedelta(seconds=1))
        process = registry_module.ClaudeProcess(tmp_path, STARTED, None, FIRST_ID)
        assert process.session_id() == FIRST_ID

        write_process_file(tmp_path, 7, CLEARED_ID, STARTED + timedelta(seconds=1))

        assert process.session_id() == CLEARED_ID

    def test_should_stop_trusting_a_file_another_container_took_over(self, registry_module, tmp_path):
        write_process_file(tmp_path, 7, FIRST_ID, STARTED + timedelta(seconds=1))
        process = registry_module.ClaudeProcess(tmp_path, STARTED, None, FIRST_ID)
        process.session_id()

        write_process_file(tmp_path, 7, CLEARED_ID, STARTED + timedelta(seconds=5), domain=OTHER_CONTAINER)

        assert process.session_id() is None

    def test_should_follow_the_only_file_in_a_folder_of_its_own_without_pid_or_session(self, registry_module, tmp_path):
        write_process_file(tmp_path, 1, CLEARED_ID, STARTED + timedelta(seconds=1))
        process = registry_module.ClaudeProcess(tmp_path, STARTED, None, None, alone=True)

        assert process.session_id() == CLEARED_ID

    def test_should_know_nothing_without_a_pid_or_a_session(self, registry_module, tmp_path):
        write_process_file(tmp_path, 7, FIRST_ID, STARTED + timedelta(seconds=1))

        assert registry_module.ClaudeProcess(tmp_path, STARTED, None, None).session_id() is None


class TestRestore:
    @staticmethod
    def interrupt(registry, record):
        with registry.track(record) as session:
            session.finish(signal.SIGKILL)

    def test_should_say_so_when_nothing_was_interrupted(self, registry, tmux_calls, capsys):
        assert registry.restore() == 0
        assert "No interrupted sessions" in capsys.readouterr().out
        assert not tmux_calls

    def test_should_type_the_resume_command_into_a_new_window_of_the_original_session(
        self, registry, make_record, tmux_calls, tmp_path
    ):
        record = make_record()
        write_transcript(registry, FIRST_ID)
        self.interrupt(registry, record)

        assert registry.restore() == 0

        assert tmux_calls == [
            ("new-window", "-d", "-t", "=work:", "-c", str(tmp_path), "-P", "-F", "#{pane_id}"),
            ("send-keys", "-t", "%7", "-l", record.resume_command()),
            ("send-keys", "-t", "%7", "Enter"),
        ]
        assert not records_in(registry)

    def test_should_create_the_tmux_session_when_it_no_longer_exists(self, registry, make_record, tmux_calls):
        write_transcript(registry, FIRST_ID)
        self.interrupt(registry, make_record(tmux_session="gone"))

        registry.restore()

        assert tmux_calls[0][:4] == ("new-session", "-d", "-s", "gone")

    def test_should_remove_the_run_folder_of_a_session_it_reopened(self, registry, make_record, tmux_calls, tmp_path):
        run = tmp_path / "run"
        run.mkdir()
        write_transcript(registry, FIRST_ID)
        self.interrupt(registry, make_record(claude_sessions=run))

        registry.restore()

        assert not run.exists()

    def test_should_drop_a_session_killed_before_its_first_prompt(self, registry, make_record, tmux_calls):
        self.interrupt(registry, make_record())

        assert registry.restore() == 0

        assert not tmux_calls
        assert not records_in(registry)

    def test_should_leave_running_sessions_alone(self, registry, make_record, tmux_calls):
        write_transcript(registry, FIRST_ID)
        with registry.track(make_record()):
            registry.restore()

            assert not tmux_calls
            assert records_in(registry)

    def test_should_count_what_restore_would_reopen_without_touching_it(self, registry, make_record, tmux_calls):
        second_id = UUID("32455626-ba1a-47a3-8064-01be22525795")
        write_transcript(registry, FIRST_ID)
        self.interrupt(registry, make_record())
        self.interrupt(registry, make_record(session_id=second_id))
        write_transcript(registry, CLEARED_ID)

        with registry.track(make_record(session_id=CLEARED_ID)):
            assert registry.count_interrupted() == 1

        assert len(records_in(registry)) == 2
        assert registry.restore() == 0
        assert len(tmux_calls) == 3

    def test_should_keep_the_record_when_tmux_fails(self, registry, registry_module, make_record, monkeypatch):
        def broken_tmux(*_args):
            raise subprocess.CalledProcessError(1, "tmux")

        monkeypatch.setattr(registry_module, "_tmux", broken_tmux)
        monkeypatch.setattr(registry_module, "_has_tmux_session", lambda _name: True)
        write_transcript(registry, FIRST_ID)
        self.interrupt(registry, make_record())

        assert registry.restore() == 1
        assert records_in(registry)


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("tmux") is None, reason="needs tmux")
class TestRestoreWithRealTmux:
    def test_should_open_one_window_per_interrupted_session(self, registry, make_record, private_tmux):
        second_id = UUID("32455626-ba1a-47a3-8064-01be22525795")
        for session_id in (FIRST_ID, second_id):
            write_transcript(registry, session_id)
            TestRestore.interrupt(registry, make_record(session_id=session_id))

        assert registry.restore() == 0

        windows = subprocess.run(
            ["tmux", "list-windows", "-t", "=work", "-F", "#{pane_id}"], capture_output=True, text=True, check=True,
        ).stdout.split()
        expected = [f"cl -r {session_id} -s --model opus" for session_id in (FIRST_ID, second_id)]
        assert len(windows) == 3
        assert self.screens(windows[1:], until=expected) == expected

    @staticmethod
    def screens(panes, until, attempts=40):
        """The echo reaches the screen asynchronously, so poll for it rather than sleep."""
        found = []
        for _ in range(attempts):
            text = "".join(
                subprocess.run(["tmux", "capture-pane", "-p", "-t", pane], capture_output=True, text=True, check=True).stdout
                for pane in panes
            )
            found = [line for line in until if line in text]
            if found == until:
                break
            time.sleep(0.05)
        return found


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("tmux") is None, reason="needs tmux")
class TestHangupFromRealTmux:
    """A tracked process in a tmux window, settling its record on SIGHUP as cl's exit guard does."""

    HOLD_RECORD = (
        "import signal, sys, time\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import session_registry as r\n"
        "from datetime import datetime, timezone\n"
        "from pathlib import Path\n"
        "record = r.SessionRecord(None, Path('.'), (), 'work', datetime.now(timezone.utc))\n"
        "session = r.Registry(Path(sys.argv[2]), Path(sys.argv[2]), Path(sys.argv[2])).track(record)\n"
        "signal.signal(signal.SIGHUP, lambda signum, _frame: (session.finish(signum), sys.exit(129)))\n"
        "Path(sys.argv[3]).touch()\n"
        "time.sleep(30)\n"
    )

    @pytest.fixture
    def record_in_window(self, tmp_path, private_tmux):
        registry_dir, ready = tmp_path / "registry", tmp_path / "ready"
        holder = shlex.join([sys.executable, "-c", self.HOLD_RECORD, str(BIN_DIR), str(registry_dir), str(ready)])
        subprocess.run(["tmux", "new-window", "-d", "-t", "=work:", "-n", "held", holder], check=True)
        self.wait_until(ready.exists)
        return next(registry_dir.glob("*.json"))

    def test_should_drop_the_record_when_its_window_is_closed(self, registry_module, record_in_window):
        subprocess.run(["tmux", "kill-window", "-t", "=work:held"], check=True)

        assert self.settle(registry_module, record_in_window) is False

    def test_should_keep_the_record_when_the_tmux_server_is_killed(self, registry_module, record_in_window):
        subprocess.run(["tmux", "kill-server"], check=True)

        assert self.settle(registry_module, record_in_window) is True

    @staticmethod
    def settle(registry_module, path: Path, attempts=100) -> bool:
        """Wait for the holder to let go of the record, and tell whether it kept it."""
        for _ in range(attempts):
            claim = registry_module._Claim.take(path)
            if claim is not None:
                claim.release(discard=False)
                return path.exists()
            if not path.exists():
                return False
            time.sleep(0.05)
        raise AssertionError("the holder never let go of its record")

    @staticmethod
    def wait_until(condition, attempts=100):
        for _ in range(attempts):
            if condition():
                return
            time.sleep(0.05)
        raise AssertionError("gave up waiting")
