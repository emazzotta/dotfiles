import fcntl
import json

import pytest

UUID_A = "11111111-2222-3333-4444-555555555555"
UUID_B = "66666666-7777-8888-9999-000000000000"

CAPTURE = 'printf "%s\\n" "$*" >> "$RSYNC_LOG"'


class FailedRsync:
    returncode = 255

    def __init__(self, stderr):
        self.stderr = stderr


@pytest.fixture
def claude_home(tmp_path):
    home = tmp_path / "claude"
    for name in ("projects/-workspace", "file-history", "tasks", "paste-cache", "sessions"):
        (home / name).mkdir(parents=True)
    (home / "projects/-workspace" / f"{UUID_A}.jsonl").write_text("{}\n")
    return home


@pytest.fixture
def rsync_log(tmp_path):
    return tmp_path / "rsync.log"


@pytest.fixture
def sync(run_cli, claude_home, rsync_log):
    def _run(args=None, stdin=None, live=(), rsync_exit=0):
        for pid, sid in enumerate(live, start=1):
            (claude_home / "sessions" / f"{pid}.json").write_text(
                json.dumps({"pid": pid, "sessionId": sid, "status": "running"})
            )
        return run_cli(
            "claude-sync",
            args=args or [],
            stdin=stdin,
            env_extra={
                "CLAUDE_HOME": str(claude_home),
                "CLAUDE_SYNC_REMOTE": "opencode@devbox.example.ts.net",
                "CLAUDE_SYNC_REMOTE_HOME": "/home/opencode/.claude",
                "RSYNC_LOG": str(rsync_log),
            },
            mock_bins={"rsync": f"{CAPTURE}\nexit {rsync_exit}"},
        )
    return _run


def invocations(rsync_log):
    if not rsync_log.exists():
        return []
    return [line for line in rsync_log.read_text().splitlines() if line]


class TestScope:
    def should_sync_only_the_allowlisted_paths(self, sync, rsync_log):
        sync(["--push"])

        synced = " ".join(invocations(rsync_log))
        for allowed in ("projects/", "file-history/", "tasks/", "paste-cache/"):
            assert allowed in synced
        for excluded in ("shell-snapshots", "history.jsonl", "sessions/", "credentials"):
            assert excluded not in synced

    def should_push_local_tree_to_the_remote(self, sync, claude_home, rsync_log):
        sync(["--push"])

        projects = next(i for i in invocations(rsync_log) if "projects/" in i)
        assert f"{claude_home}/projects/" in projects
        assert "opencode@devbox.example.ts.net:/home/opencode/.claude/projects/" in projects

    def should_pull_remote_tree_to_local(self, sync, claude_home, rsync_log):
        sync(["--pull"])

        projects = next(i for i in invocations(rsync_log) if "projects/" in i)
        assert "opencode@devbox.example.ts.net:/home/opencode/.claude/projects/" in projects
        assert projects.rstrip().endswith(f"{claude_home}/projects/")

    def should_run_both_directions_by_default(self, sync, rsync_log):
        sync()

        projects = [i for i in invocations(rsync_log) if "projects/" in i]
        assert len(projects) == 2


class TestSafety:
    def should_never_overwrite_a_newer_file(self, sync, rsync_log):
        sync(["--push"])

        assert all("--update" in i for i in invocations(rsync_log))

    def should_exclude_live_sessions_from_both_directions(self, sync, rsync_log):
        sync(live=[UUID_A])

        assert all(f"--exclude={UUID_A}*" in i for i in invocations(rsync_log))

    def should_exclude_every_live_session(self, sync, rsync_log):
        sync(["--push"], live=[UUID_A, UUID_B])

        first = invocations(rsync_log)[0]
        assert f"--exclude={UUID_A}*" in first
        assert f"--exclude={UUID_B}*" in first

    def should_exclude_nothing_when_no_session_is_live(self, sync, rsync_log):
        sync(["--push"])

        assert all("--exclude=" not in i for i in invocations(rsync_log))

    def should_ignore_a_session_entry_that_is_not_running(self, sync, claude_home, rsync_log):
        (claude_home / "sessions" / "9.json").write_text(
            json.dumps({"pid": 9, "sessionId": UUID_B, "status": "exited"})
        )

        sync(["--push"])

        assert all(UUID_B not in i for i in invocations(rsync_log))


class TestFailureIsNeverFatal:
    def should_exit_zero_when_the_remote_is_unreachable(self, sync, rsync_log):
        result = sync(["--push"], rsync_exit=255)

        assert result.returncode == 0

    def should_exit_zero_when_the_sessions_dir_is_missing(self, sync, claude_home):
        for entry in (claude_home / "sessions").iterdir():
            entry.unlink()
        (claude_home / "sessions").rmdir()

        assert sync(["--push"]).returncode == 0

    def should_skip_silently_when_another_run_holds_the_lock(self, sync, claude_home, rsync_log):
        lock = claude_home / "claude-sync.lock"
        lock.touch()
        with open(lock) as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)

            result = sync(["--push"])

        assert result.returncode == 0
        assert invocations(rsync_log) == []


class TestSingleSession:
    def should_push_only_the_named_session(self, sync, claude_home, rsync_log):
        (claude_home / "file-history" / UUID_A).mkdir()

        sync(["--session", UUID_A])

        synced = " ".join(invocations(rsync_log))
        assert f"{UUID_A}.jsonl" in synced
        assert f"file-history/{UUID_A}/" in synced

    def should_skip_session_dirs_that_do_not_exist(self, sync, rsync_log):
        sync(["--session", UUID_A])

        assert all(f"tasks/{UUID_A}" not in i for i in invocations(rsync_log))

    def should_push_a_named_session_even_while_it_is_live(self, sync, rsync_log):
        sync(["--session", UUID_A], live=[UUID_A])

        assert invocations(rsync_log)
        assert all("--exclude=" not in i for i in invocations(rsync_log))

    def should_read_the_session_id_from_stdin(self, sync, rsync_log):
        sync(["--push-stdin"], stdin=f"{UUID_A}\n")

        assert any(f"{UUID_A}.jsonl" in i for i in invocations(rsync_log))

    def should_reject_a_session_id_that_is_not_a_uuid(self, sync, rsync_log):
        result = sync(["--push-stdin"], stdin="../../etc/passwd\n")

        assert result.returncode != 0
        assert invocations(rsync_log) == []


class TestHelp:
    def should_print_usage_without_touching_the_network(self, sync, rsync_log):
        result = sync(["--help"])

        assert result.returncode == 0
        assert "claude-sync" in result.stdout
        assert invocations(rsync_log) == []


class TestRemoteDefaults:
    @pytest.fixture
    def script(self, load_script, monkeypatch):
        for name in ("CLAUDE_SYNC_REMOTE", "CLAUDE_SYNC_REMOTE_HOME"):
            monkeypatch.delenv(name, raising=False)
        return load_script("claude-sync")

    def should_reach_the_dev_box_through_its_ssh_alias(self, script):
        assert script.remote_base().startswith("devbox:")

    def should_not_request_a_tty_for_a_binary_transfer(self, script):
        assert "RequestTTY=no" in script.SSH_COMMAND


class TestVisibility:
    def should_stay_silent_when_not_attached_to_a_terminal(self, sync):
        result = sync(["--push"], rsync_exit=255)

        assert result.returncode == 0
        assert result.stderr == ""

    def should_report_the_failure_when_attached_to_a_terminal(self, load_script, monkeypatch, capsys):
        script = load_script("claude-sync")
        monkeypatch.setattr(script, "interactive", lambda: True)
        monkeypatch.setattr(script.subprocess, "run",
                            lambda *_args, **_kwargs: FailedRsync("Permission denied (publickey)."))

        failures = script.transfer(script.local_home(), [["rsync", "src", "dst"]])

        assert failures == 1
        assert "Permission denied" in capsys.readouterr().err
        assert script.report(failures, "up to date") == 1

    def should_say_when_another_run_holds_the_lock(self, sync, claude_home, rsync_log):
        lock = claude_home / "claude-sync.lock"
        lock.touch()
        with open(lock) as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)

            result = sync(["--push"])

        assert result.returncode == 0
        assert invocations(rsync_log) == []

    def should_stream_progress_when_verbose(self, sync, rsync_log):
        sync(["--push", "--verbose"])

        assert all("--info=progress2" in i for i in invocations(rsync_log))

    def should_swallow_progress_by_default(self, sync, rsync_log):
        sync(["--push"])

        assert all("--info=progress2" not in i for i in invocations(rsync_log))
