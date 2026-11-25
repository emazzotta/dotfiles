import contextlib
import fcntl
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from bin.tests.conftest import requires_tool

UUID_A = "11111111-2222-3333-4444-555555555555"
UUID_B = "66666666-7777-8888-9999-000000000000"

CAPTURE = 'printf "%s\\n" "$*" >> "$RSYNC_LOG"'


class FailedRsync:
    returncode = 255
    stdout = ""

    def __init__(self, stderr):
        self.stderr = stderr


@pytest.fixture(autouse=True)
def _never_touch_the_real_home(tmp_path, monkeypatch):
    """Without this a test that forgets CLAUDE_HOME writes into the user's live ~/.claude."""
    monkeypatch.setenv("CLAUDE_HOME", str(tmp_path / "isolated"))
    monkeypatch.setenv("CLAUDE_SYNC_WORKSPACE_REPO", str(tmp_path / "no-workspace-repo"))
    monkeypatch.setenv("CLAUDE_SYNC_RSYNC", "rsync")
    (tmp_path / "isolated").mkdir()


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
def state_home(tmp_path):
    """The script's HOME, under which cl keeps one record per run."""
    return tmp_path / "home"


@pytest.fixture
def start_run(load_module, state_home):
    """A cl run as cl leaves it: a record naming the run's own folder, which holds Claude's state file."""
    registry = load_module("session_registry")

    def _start(session_id, status="busy"):
        run_dir = state_home / ".local/state/cl/claude-sessions" / uuid4().hex
        run_dir.mkdir(parents=True)
        (run_dir / "1.json").write_text(json.dumps({"pid": 1, "sessionId": session_id, "status": status}))
        record = state_home / ".local/state/cl/sessions" / f"{uuid4()}.json"
        record.parent.mkdir(parents=True, exist_ok=True)
        started = datetime.now(timezone.utc)
        record.write_text(registry.SessionRecord(None, state_home, (), None, started, claude_sessions=run_dir).to_json())
        return record
    return _start


@contextlib.contextmanager
def holding(records):
    """A running cl keeps its record locked; the kernel drops the lock however cl dies."""
    with contextlib.ExitStack() as stack:
        for record in records:
            fcntl.flock(stack.enter_context(record.open("r")), fcntl.LOCK_EX)
        yield


@pytest.fixture
def sync(run_cli, claude_home, rsync_log, state_home, start_run):
    def _run(args=None, stdin=None, live=(), rsync_exit=0):
        with holding([start_run(session) for session in live]):
            return run_cli(
                "claude-sync",
                args=args or [],
                stdin=stdin,
                env_extra={
                    "HOME": str(state_home),
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


def mirror_runs(rsync_log):
    return [line for line in invocations(rsync_log) if line.rstrip().endswith(":/workspace/")]


def plugin_runs(rsync_log):
    return [line for line in invocations(rsync_log) if "/./plugins/" in line]


def settings_runs(rsync_log):
    return [line for line in invocations(rsync_log) if "settings.json" in line]


WORKSPACE_FILES = {
    "CLAUDE.md": "instructions\n",
    ".claude/skills/demo/SKILL.md": "demo skill\n",
    ".claude/knowledge/code/notes.md": "code notes\n",
    ".claude/knowledge/memory/MEMORY.md": "curated\n",
    ".claude/knowledge/private/identity.md": "passport\n",
    ".claude/knowledge/work/customers.md": "customers\n",
    ".claude/knowledge/sources/vendor.pdf": "vendor\n",
    ".claude/knowledge/secreviews/infra.md": "weaknesses\n",
    ".claude/knowledge/vault/key.md": "encrypted at rest\n",
    ".claude/hooks/stop.sh": "exit 0\n",
    ".claude/plugins/marketplace.json": "{}\n",
    ".claude/settings.json": "{}\n",
    ".claude/ref-reference/skills/ref/SKILL.md": "pinned upstream\n",
}
WORKSPACE_LINKS = {
    ".claude/skills/ref": "../ref-reference/skills/ref",
    ".claude/skills/leak": "../knowledge/private",
    ".claude/skills/leak.md": "../knowledge/private/identity.md",
    ".claude/skills/dangling": "../nowhere",
}
MIRRORED = {"CLAUDE.md", ".claude/skills/demo/SKILL.md", ".claude/knowledge/code/notes.md",
            ".claude/knowledge/memory/MEMORY.md", ".claude/skills/ref/SKILL.md"}
NEVER_SENT = {".claude/knowledge/private/identity.md", ".claude/knowledge/work/customers.md",
              ".claude/knowledge/sources/vendor.pdf", ".claude/knowledge/secreviews/infra.md",
              ".claude/knowledge/vault/key.md", ".claude/hooks/stop.sh", ".claude/plugins/marketplace.json",
              ".claude/settings.json", ".claude/skills/demo/draft.md", ".claude/vendored/README"}
MAC_PLUGINS = {
    "installed_plugins.json": '{"plugins": {"leonardo@leonardo-skills": []}}\n',
    "known_marketplaces.json": json.dumps({
        "leonardo-skills": {"source": {"source": "git", "url": "git@gitlab.example:ai.git"}, "autoUpdate": True},
        "claude-plugins-official": {"source": {"source": "github", "repo": "anthropics/claude-plugins-official"}},
    }) + "\n",
    "marketplaces/leonardo-skills/README.md": "marketplace\n",
    "cache/leonardo-skills/leonardo/1.16.2/SKILL.md": "installed skill\n",
    "synced/finance/SKILL.md": "account synced\n",
    "data/leonardo/state": "mac runtime state\n",
    "ssh-mirrors/ai.git/HEAD": "ref: refs/heads/main\n",
    "cache/leonardo-skills/leonardo/1.16.2/.in_use/1": "mac session\n",
}
DEVBOX_PLUGINS_OWN = {
    "synced/own.json": "devbox synced\n",
    "data/leonardo/state": "devbox runtime state\n",
    "cache/leonardo-skills/leonardo/1.16.2/.in_use/2": "devbox session\n",
}
MARKETPLACE_SOURCE = {"source": "git", "url": "git@gitlab.example:ai.git"}
MAC_SETTINGS = {
    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "stop-bell"}]}]},
    "env": {"EDITOR": "vim"},
    "theme": "light",
    "autoCompactWindow": 400000,
    "enabledPlugins": {"leonardo@leonardo-skills": True, "superpowers@claude-plugins-official": False},
    "extraKnownMarketplaces": {"leonardo-skills": {"source": MARKETPLACE_SOURCE, "autoUpdate": True}},
}
BOX_SETTINGS = {
    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "box-bell"}]}]},
    "env": {"GIT_SSH_COMMAND": "keyguard-ssh"},
    "theme": "dark",
    "tui": "fullscreen",
    "enabledPlugins": {"old@marketplace": True},
}
SYNC_OFF = {"syncClaudeAiPlugins": False, "syncClaudeAiSkills": False, "disableClaudeAiConnectors": True}
MAC_SETTINGS_ON_THE_BOX = {
    "env": MAC_SETTINGS["env"],
    "theme": "light",
    "autoCompactWindow": 400000,
    "enabledPlugins": MAC_SETTINGS["enabledPlugins"],
    "extraKnownMarketplaces": {"leonardo-skills": {"source": MARKETPLACE_SOURCE, "autoUpdate": False}},
    **SYNC_OFF,
}
EXPECTED_BOX = {
    "hooks": BOX_SETTINGS["hooks"], "tui": "fullscreen", **MAC_SETTINGS_ON_THE_BOX,
    "env": {**MAC_SETTINGS["env"], **BOX_SETTINGS["env"]},
}
DEVBOX_OWN = {
    "checkout-gitlab.sh": "devbox\n",
    "projects/app/README": "devbox\n",
    ".claude/settings.local.json": "devbox\n",
    ".claude/knowledge/memory/2026-09-29.md": "devbox log\n",
    ".claude/ecc-reference/README": "devbox clone\n",
}


def write_tree(root, files):
    for relative, content in files.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(content)


@pytest.fixture
def fake_ssh(tmp_path):
    """Drops the host and runs rsync's server side locally, so a real rsync reaches a directory."""
    script = tmp_path / "fake-ssh"
    script.write_text('#!/bin/sh\nshift\nexec "$@"\n')
    script.chmod(0o755)
    return script


@pytest.fixture
def workspace_repo(tmp_path, git):
    repo = tmp_path / "opencode"
    tree = repo / "opencode/workspace"
    write_tree(tree, WORKSPACE_FILES)
    for relative, target in {**WORKSPACE_LINKS, ".claude/skills/outside": str(tmp_path / "outside")}.items():
        (tree / relative).symlink_to(target)
    write_tree(tmp_path / "outside", {"secret.txt": "outside the tree\n"})
    write_tree(tree / ".claude/vendored", {"README": "a submodule\n"})
    git(tree / ".claude/vendored", "init", "-q")
    git(tree / ".claude/vendored", "add", "README")
    git(tree / ".claude/vendored", "commit", "-q", "-m", "Vendored")
    write_tree(repo, {
        ".gitignore": "opencode/workspace/.claude/*-reference/\n",
        ".gitattributes": "opencode/workspace/.claude/knowledge/vault/** filter=git-crypt diff=git-crypt\n",
    })
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "Workspace")
    write_tree(tree, {".claude/skills/demo/draft.md": "untracked\n"})
    return repo


class TestScope:
    def should_sync_only_the_allowlisted_paths(self, sync, rsync_log):
        sync(["--push"])

        synced = " ".join(invocations(rsync_log))
        for allowed in ("projects/", "file-history/", "tasks/", "paste-cache/"):
            assert allowed in synced
        for excluded in ("shell-snapshots", "history.jsonl", "sessions/", "credentials"):
            assert excluded not in synced

    def should_push_every_path_in_one_invocation(self, sync, claude_home, rsync_log):
        sync(["--push"])

        assert len(invocations(rsync_log)) == 1
        pushed = invocations(rsync_log)[0]
        assert "--relative" in pushed
        for name in ("projects", "file-history", "tasks", "paste-cache"):
            assert f"{claude_home}/./{name}/" in pushed
        assert pushed.rstrip().endswith("opencode@devbox.example.ts.net:/home/opencode/.claude/")

    def should_pull_every_path_in_one_invocation(self, sync, claude_home, rsync_log):
        sync(["--pull"])

        assert len(invocations(rsync_log)) == 1
        pulled = invocations(rsync_log)[0]
        for name in ("projects", "file-history", "tasks", "paste-cache"):
            assert f"/home/opencode/.claude/{name} " in pulled + " "
        assert pulled.rstrip().endswith(f"{claude_home}/")

    def should_keep_each_pulled_path_in_its_own_directory(self, sync, rsync_log):
        """A trailing slash on a multi-source pull flattens every path into the config root."""
        sync(["--pull"])

        assert "/home/opencode/.claude/projects/ " not in invocations(rsync_log)[0] + " "

    def should_run_both_directions_by_default(self, sync, rsync_log):
        sync()

        assert len(invocations(rsync_log)) == 2

    def should_reuse_one_ssh_connection(self, sync, rsync_log):
        sync(["--push"])

        assert "ControlMaster=auto" in invocations(rsync_log)[0]


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

    def should_count_an_idle_session_as_live(self, sync, start_run, rsync_log):
        with holding([start_run(UUID_A, status="idle")]):
            sync(["--push"])

        assert f"--exclude={UUID_A}*" in invocations(rsync_log)[0]

    def should_ignore_the_state_file_a_dead_run_left_behind(self, sync, start_run, rsync_log):
        start_run(UUID_B)

        sync(["--push"])

        assert all(UUID_B not in i for i in invocations(rsync_log))

    def should_ignore_a_state_file_in_the_shared_sessions_folder(self, sync, claude_home, rsync_log):
        (claude_home / "sessions" / "1.json").write_text(json.dumps({"pid": 1, "sessionId": UUID_B, "status": "busy"}))

        sync(["--push"])

        assert all(UUID_B not in i for i in invocations(rsync_log))


class TestFailureIsNeverFatal:
    def should_exit_zero_when_the_remote_is_unreachable(self, sync, rsync_log):
        result = sync(["--push"], rsync_exit=255)

        assert result.returncode == 0

    def should_skip_a_state_file_it_cannot_read(self, sync, start_run, rsync_log):
        record = start_run(UUID_A)
        (Path(json.loads(record.read_text())["claudeSessions"]) / "1.json").write_text("{not json")

        with holding([record]):
            result = sync(["--push"])

        assert result.returncode == 0
        assert all("--exclude=" not in i for i in invocations(rsync_log))

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

    def should_push_the_session_directory_with_its_subagents_and_tool_results(self, sync, claude_home, rsync_log):
        session_dir = claude_home / "projects/-workspace" / UUID_A
        (session_dir / "subagents").mkdir(parents=True)
        (session_dir / "tool-results").mkdir()

        sync(["--session", UUID_A])

        assert f"{claude_home}/./projects/-workspace/{UUID_A}/ " in invocations(rsync_log)[0]

    def should_skip_session_dirs_that_do_not_exist(self, sync, rsync_log):
        sync(["--session", UUID_A])

        assert all(f"tasks/{UUID_A}" not in i for i in invocations(rsync_log))
        assert all(f"-workspace/{UUID_A}/" not in i for i in invocations(rsync_log))

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
        for name in ("CLAUDE_SYNC_REMOTE", "CLAUDE_SYNC_REMOTE_HOME", "CLAUDE_SYNC_REMOTE_WORKSPACE"):
            monkeypatch.delenv(name, raising=False)
        return load_script("claude-sync")

    def should_reach_the_dev_box_through_its_ssh_alias(self, script):
        assert script.remote_base().startswith("devbox:")

    def should_mirror_into_the_dev_box_workspace(self, script):
        assert script.remote_workspace() == "devbox:/workspace"

    def should_not_request_a_tty_for_a_binary_transfer(self, script):
        assert "RequestTTY=no" in script.SSH_COMMAND


SSH_E = ("ssh -o BatchMode=yes -o ConnectTimeout=5 -o RequestTTY=no"
         " -o ControlMaster=auto -o ControlPath=~/.ssh/claude-sync-%C -o ControlPersist=60")
BOX = "devbox:/home/opencode/.claude"


class Ran:
    returncode = 0
    stdout = ""
    stderr = ""


class TestSshArgv:
    """claude-move opens the same ssh control master, so none of these commands may drift."""

    @pytest.fixture
    def script(self, load_script, monkeypatch, claude_home, tmp_path):
        for name in ("CLAUDE_SYNC_REMOTE", "CLAUDE_SYNC_REMOTE_HOME", "CLAUDE_SYNC_REMOTE_WORKSPACE"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("CLAUDE_HOME", str(claude_home))
        (claude_home / "plugins" / "cache").mkdir(parents=True)
        (claude_home / "plugins" / "installed_plugins.json").write_text("{}\n")
        (claude_home / "settings.json").write_text('{"theme": "light"}\n')
        script = load_script("claude-sync")
        staging = tmp_path / "staging"
        staging.mkdir()
        monkeypatch.setattr(script, "wrong_host", lambda: False)
        monkeypatch.setattr(script, "find_live_sessions", lambda *_args: [])
        monkeypatch.setattr(script, "tempfile",
                            SimpleNamespace(TemporaryDirectory=lambda: contextlib.nullcontext(str(staging))))
        return script

    @pytest.fixture
    def commands(self, script, monkeypatch):
        calls = []
        monkeypatch.setattr(script.subprocess, "run", lambda command, **_kwargs: calls.append(command) or Ran())

        def _run(args):
            script.main(args)
            return calls
        return _run

    def should_push_with_the_shared_ssh_options(self, commands, claude_home, tmp_path):
        staging = tmp_path / "staging"

        sent = commands(["--push"])

        assert sent == [
            ["rsync", "--relative", "-a", "--update", "--timeout=20", "-e", SSH_E, f"{claude_home}/./projects/",
             f"{claude_home}/./file-history/", f"{claude_home}/./tasks/", f"{claude_home}/./paste-cache/", f"{BOX}/"],
            ["rsync", "--relative", "-a", "--delete", "--timeout=20", "-e", SSH_E, "--exclude=.in_use/",
             f"{claude_home}/./plugins/installed_plugins.json", f"{claude_home}/./plugins/cache/", f"{BOX}/"],
            ["rsync", "-a", "--delete", "--timeout=20", "-e", SSH_E, f"{BOX}/settings.json", f"{staging}/settings.json"],
            ["rsync", "-a", "--delete", "--timeout=20", "-e", SSH_E, f"{staging}/settings.json", f"{BOX}/settings.json"],
        ]

    def should_pull_with_the_shared_ssh_options(self, commands, claude_home):
        sent = commands(["--pull"])

        assert sent == [
            ["rsync", "-a", "--update", "--timeout=20", "-e", SSH_E, f"{BOX}/projects", f"{BOX}/file-history",
             f"{BOX}/tasks", f"{BOX}/paste-cache", f"{claude_home}/"],
        ]

    def should_push_one_session_with_the_shared_ssh_options(self, commands, claude_home, tmp_path):
        staging = tmp_path / "staging"

        sent = commands(["--session", UUID_A])

        assert sent == [
            ["rsync", "--relative", "-a", "--update", "--timeout=20", "-e", SSH_E,
             f"{claude_home}/./projects/-workspace/{UUID_A}.jsonl", f"{claude_home}/./paste-cache/", f"{BOX}/"],
            ["rsync", "--relative", "-a", "--delete", "--timeout=20", "-e", SSH_E, "--exclude=.in_use/",
             f"{claude_home}/./plugins/installed_plugins.json", f"{claude_home}/./plugins/cache/", f"{BOX}/"],
            ["rsync", "-a", "--delete", "--timeout=20", "-e", SSH_E, f"{BOX}/settings.json", f"{staging}/settings.json"],
            ["rsync", "-a", "--delete", "--timeout=20", "-e", SSH_E, f"{staging}/settings.json", f"{BOX}/settings.json"],
        ]

    def should_mirror_the_workspace_with_the_shared_ssh_options(self, script, tmp_path):
        staging = tmp_path / "staging"
        (staging / "CLAUDE.md").write_text("instructions\n")
        excludes = [f"--exclude=/{pattern}" for pattern in script.LEFT_OUT + script.DEVBOX_STATE]

        sent = script.mirror_transfers(staging)

        assert sent == [["rsync", "--relative", "-a", "--delete", "--timeout=20", "-e", SSH_E, *excludes,
                         f"{staging}/./CLAUDE.md", "devbox:/workspace/"]]

    def should_take_a_remote_from_the_environment_as_a_sign_of_the_right_host(self, load_script, monkeypatch):
        monkeypatch.setenv("CLAUDE_SYNC_REMOTE", "opencode@box.example")

        assert load_script("claude-sync").wrong_host() is False


class TestVisibility:
    def should_stay_silent_when_not_attached_to_a_terminal(self, sync):
        result = sync(["--push"], rsync_exit=255)

        assert result.returncode == 0
        assert result.stderr == ""

    def should_report_the_failure_when_attached_to_a_terminal(self, load_script, monkeypatch, capsys, tmp_path):
        script = load_script("claude-sync")
        monkeypatch.setattr(script, "interactive", lambda: True)
        monkeypatch.setattr(script.subprocess, "run",
                            lambda *_args, **_kwargs: FailedRsync("Permission denied (publickey)."))

        failures = script.transfer(tmp_path, [["rsync", "src", "dst"]])

        assert failures == 1
        assert "Permission denied" in capsys.readouterr().err
        assert script.report(tmp_path, failures, "up to date") == 1

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

    def should_refuse_to_run_inside_the_container(self, load_script, monkeypatch, capsys):
        script = load_script("claude-sync")
        monkeypatch.setattr(script, "wrong_host", lambda: True)
        monkeypatch.setattr(script, "interactive", lambda: True)

        assert script.main(["--push"]) == 0
        assert "Mac host" in capsys.readouterr().err

    def should_name_the_invoker_in_a_failure(self, sync, claude_home, monkeypatch):
        monkeypatch.delenv("SSH_AUTH_SOCK", raising=False)

        sync(["--push"], rsync_exit=255)

        assert "no-agent" in (claude_home / "claude-sync.log").read_text()


NOW = datetime(2026, 11, 25, 12, 0, 0)
HOST_KEY_FAILURE = ("rsync exit 255 [/usr/sbin/cron, no-agent, home=/Users/someone]"
                    " -> devbox:/home/opencode/.claude/projects/: Host key verification failed.")


def write_log(home, *entries):
    lines = [f"{when:%Y-%m-%d %H:%M:%S} {message}" for when, message in entries]
    (home / "claude-sync.log").write_text("\n".join(lines) + "\n")


def mark_success_at(home, when):
    marker = home / "claude-sync.ok"
    marker.touch()
    os.utime(marker, (when.timestamp(), when.timestamp()))


class TestFailureWarning:
    @pytest.fixture
    def script(self, load_script):
        return load_script("claude-sync")

    def should_record_a_run_that_reached_the_box(self, sync, claude_home):
        sync(["--push"])

        assert (claude_home / "claude-sync.ok").is_file()

    def should_still_finish_when_the_success_cannot_be_recorded(self, script, tmp_path):
        assert script.report(tmp_path / "missing", 0, "up to date") == 0

    def should_not_record_a_run_that_failed(self, sync, claude_home):
        sync(["--push"], rsync_exit=255)

        assert not (claude_home / "claude-sync.ok").exists()

    def should_stay_quiet_without_failures(self, script, tmp_path):
        assert script.failing_since(tmp_path, NOW) is None

    def should_stay_quiet_while_failures_are_younger_than_an_hour(self, script, tmp_path):
        write_log(tmp_path, (NOW - timedelta(minutes=59), HOST_KEY_FAILURE))

        assert script.failing_since(tmp_path, NOW) is None

    def should_report_the_first_failure_and_the_latest_reason_once_they_outlast_an_hour(self, script, tmp_path):
        write_log(tmp_path,
                  (NOW - timedelta(hours=26), "settings sync skipped: rsync exit 255: Connection reset by peer"),
                  (NOW - timedelta(minutes=5), HOST_KEY_FAILURE + "\nrsync: connection unexpectedly closed"))

        failing = script.failing_since(tmp_path, NOW)

        assert failing == (NOW - timedelta(hours=26), "Host key verification failed.")

    def should_forget_failures_before_the_last_success(self, script, tmp_path):
        write_log(tmp_path, (NOW - timedelta(hours=3), HOST_KEY_FAILURE))
        mark_success_at(tmp_path, NOW - timedelta(hours=2))

        assert script.failing_since(tmp_path, NOW) is None

    def should_count_from_the_first_failure_after_the_last_success(self, script, tmp_path):
        write_log(tmp_path,
                  (NOW - timedelta(hours=3), "settings sync skipped: rsync exit 255: Connection reset by peer"),
                  (NOW - timedelta(minutes=90), HOST_KEY_FAILURE))
        mark_success_at(tmp_path, NOW - timedelta(hours=2))

        failing = script.failing_since(tmp_path, NOW)

        assert failing.since == NOW - timedelta(minutes=90)

    def should_keep_a_reason_that_names_no_destination(self, script, tmp_path):
        reason = "settings sync skipped: rsync exit 255: Connection reset by peer"
        write_log(tmp_path, (NOW - timedelta(hours=2), reason))

        assert script.failing_since(tmp_path, NOW).reason == reason


class TestLeftOut:
    @pytest.mark.parametrize("relative, expected", [
        (".claude/knowledge/private/identity.md", True),
        (".claude/knowledge/private", True),
        (".claude/knowledge", True),
        (".", True),
        (".claude/settings.json", True),
        (".claude/settings.jsonc", False),
        (".claude/knowledge/code/notes.md", False),
    ])
    def should_cover_left_out_parts_and_every_directory_holding_one(self, load_script, relative, expected):
        assert load_script("claude-sync").left_out(relative) is expected


class TestMirrorSelection:
    def should_pick_tracked_paths_minus_left_out_filtered_and_submodules(
            self, load_script, monkeypatch, git_env, workspace_repo):
        for name, value in git_env.items():
            monkeypatch.setenv(name, value)

        selected = load_script("claude-sync").mirrorable(workspace_repo)

        assert set(selected) == {"CLAUDE.md", ".claude/skills/demo/SKILL.md", ".claude/knowledge/code/notes.md",
                                 ".claude/knowledge/memory/MEMORY.md", ".claude/skills/outside",
                                 *WORKSPACE_LINKS}


@requires_tool("rsync")
class TestWorkspaceMirror:
    @pytest.fixture
    def devbox(self, tmp_path):
        root = tmp_path / "devbox-workspace"
        write_tree(root, {**DEVBOX_OWN, ".claude/skills/removed/SKILL.md": "deleted on the Mac\n"})
        return root

    @pytest.fixture
    def mirrored(self, load_script, monkeypatch, tmp_path, git_env, workspace_repo, devbox, fake_ssh):
        monkeypatch.delenv("CLAUDE_SYNC_RSYNC")
        for name, value in {**git_env, "CLAUDE_SYNC_REMOTE": "devbox", "CLAUDE_SYNC_REMOTE_WORKSPACE": str(devbox),
                            "CLAUDE_SYNC_WORKSPACE_REPO": str(workspace_repo)}.items():
            monkeypatch.setenv(name, value)
        script = load_script("claude-sync")
        monkeypatch.setattr(script, "SSH_COMMAND", str(fake_ssh))

        failures = script.mirror_workspace(tmp_path / "isolated", stream=False)

        files = {path.relative_to(devbox).as_posix() for path in devbox.rglob("*") if not path.is_dir()}
        return SimpleNamespace(failures=failures, files=files)

    def should_send_every_tracked_workspace_file(self, mirrored):
        assert mirrored.failures == 0
        assert MIRRORED <= mirrored.files

    def should_never_send_a_left_out_filtered_untracked_or_submodule_file(self, mirrored):
        assert NEVER_SENT & mirrored.files == set()

    def should_carry_a_linked_pinned_reference_as_content(self, mirrored, devbox):
        assert (devbox / ".claude/skills/ref/SKILL.md").read_text() == "pinned upstream\n"

    def should_not_follow_a_link_into_a_left_out_part_or_out_of_the_tree(self, mirrored):
        linked = (".claude/skills/leak", ".claude/skills/outside", ".claude/skills/dangling")
        assert {path for path in mirrored.files if path.startswith(linked)} == set()

    def should_delete_what_the_mac_no_longer_has(self, mirrored):
        assert ".claude/skills/removed/SKILL.md" not in mirrored.files

    def should_leave_the_dev_box_own_files_alone(self, mirrored, devbox):
        assert {relative: (devbox / relative).read_text() for relative in DEVBOX_OWN} == DEVBOX_OWN


class TestMirrorWiring:
    @pytest.fixture
    def workspace(self, monkeypatch, git_env, workspace_repo):
        for name, value in {**git_env, "CLAUDE_SYNC_WORKSPACE_REPO": str(workspace_repo)}.items():
            monkeypatch.setenv(name, value)

    @pytest.mark.usefixtures("workspace")
    def should_mirror_on_a_full_push(self, sync, rsync_log):
        sync(["--push"])

        assert len(mirror_runs(rsync_log)) == 1

    @pytest.mark.usefixtures("workspace")
    def should_mirror_after_a_session_push(self, sync, rsync_log):
        sync(["--push-stdin"], stdin=f"{UUID_A}\n")

        assert len(mirror_runs(rsync_log)) == 1

    @pytest.mark.usefixtures("workspace")
    def should_never_mirror_on_a_pull(self, sync, rsync_log):
        sync(["--pull"])

        assert mirror_runs(rsync_log) == []

    @pytest.mark.usefixtures("workspace")
    def should_let_the_mac_win_over_a_newer_dev_box_file(self, sync, rsync_log):
        sync(["--push"])

        assert "--update" not in mirror_runs(rsync_log)[0].split()

    def should_skip_the_mirror_when_the_workspace_repo_is_missing(self, sync, rsync_log):
        sync(["--push"])

        assert mirror_runs(rsync_log) == []


@requires_tool("rsync")
class TestPluginMirror:
    @pytest.fixture
    def mirrored(self, load_script, monkeypatch, tmp_path, fake_ssh):
        monkeypatch.delenv("CLAUDE_SYNC_RSYNC")
        mac = tmp_path / "mac-claude"
        write_tree(mac / "plugins", MAC_PLUGINS)
        devbox = tmp_path / "devbox-claude" / "plugins"
        write_tree(devbox, {**DEVBOX_PLUGINS_OWN, "cache/old/1.0/SKILL.md": "uninstalled on the Mac\n"})
        monkeypatch.setenv("CLAUDE_SYNC_REMOTE", "devbox")
        monkeypatch.setenv("CLAUDE_SYNC_REMOTE_HOME", str(devbox.parent))
        script = load_script("claude-sync")
        monkeypatch.setattr(script, "SSH_COMMAND", str(fake_ssh))

        failures = script.mirror_plugins(mac, stream=False)

        files = {path.relative_to(devbox).as_posix() for path in devbox.rglob("*") if not path.is_dir()}
        return SimpleNamespace(failures=failures, files=files, root=devbox)

    def should_send_what_makes_a_plugin_installed(self, mirrored):
        assert mirrored.failures == 0
        assert {"installed_plugins.json", "known_marketplaces.json", "marketplaces/leonardo-skills/README.md",
                "cache/leonardo-skills/leonardo/1.16.2/SKILL.md"} <= mirrored.files

    def should_keep_per_machine_plugin_state_apart(self, mirrored):
        assert {"synced/finance/SKILL.md", "ssh-mirrors/ai.git/HEAD",
                "cache/leonardo-skills/leonardo/1.16.2/.in_use/1"} & mirrored.files == set()
        assert {relative: (mirrored.root / relative).read_text() for relative in DEVBOX_PLUGINS_OWN} == DEVBOX_PLUGINS_OWN

    def should_drop_a_plugin_the_mac_no_longer_has(self, mirrored):
        assert "cache/old/1.0/SKILL.md" not in mirrored.files

    def should_switch_off_marketplace_updates_on_the_dev_box(self, mirrored):
        registry = json.loads((mirrored.root / "known_marketplaces.json").read_text())

        assert {name: entry["autoUpdate"] for name, entry in registry.items()} == {
            "leonardo-skills": False, "claude-plugins-official": False}
        assert registry["leonardo-skills"]["source"]["url"] == "git@gitlab.example:ai.git"


class TestPluginWiring:
    @pytest.fixture
    def plugins(self, claude_home):
        write_tree(claude_home / "plugins", {"installed_plugins.json": "{}\n", "cache/p/1.0/SKILL.md": "skill\n"})

    @pytest.mark.usefixtures("plugins")
    def should_mirror_plugins_on_a_full_push(self, sync, rsync_log):
        sync(["--push"])

        assert len(plugin_runs(rsync_log)) == 1

    @pytest.mark.usefixtures("plugins")
    def should_mirror_plugins_after_a_session_push(self, sync, rsync_log):
        sync(["--push-stdin"], stdin=f"{UUID_A}\n")

        assert len(plugin_runs(rsync_log)) == 1

    @pytest.mark.usefixtures("plugins")
    def should_never_mirror_plugins_on_a_pull(self, sync, rsync_log):
        sync(["--pull"])

        assert plugin_runs(rsync_log) == []

    def should_skip_the_plugin_mirror_without_plugins(self, sync, rsync_log):
        sync(["--push"])

        assert plugin_runs(rsync_log) == []

    def should_log_and_skip_a_broken_marketplace_registry(self, load_script, tmp_path):
        home = tmp_path / "isolated"
        write_tree(home / "plugins", {"known_marketplaces.json": "{not json\n"})

        assert load_script("claude-sync").mirror_plugins(home, stream=False) == 1
        assert "plugin mirror skipped" in (home / "claude-sync.log").read_text()


class TestSettingsMerge:
    @pytest.fixture
    def merged_settings(self, load_script):
        return load_script("claude-sync").merged_settings

    def should_take_every_mac_key_but_the_box_owned_ones(self, merged_settings):
        assert merged_settings(MAC_SETTINGS, BOX_SETTINGS) == EXPECTED_BOX

    def should_keep_a_key_only_the_box_has(self, merged_settings):
        assert merged_settings({"theme": "light"}, BOX_SETTINGS)["enabledPlugins"] == BOX_SETTINGS["enabledPlugins"]

    def should_never_send_the_mac_hooks(self, merged_settings):
        assert "hooks" not in merged_settings(MAC_SETTINGS, {})

    def should_send_a_mac_env_variable_the_box_lacks(self, merged_settings):
        mac = {"env": {"CLAUDE_CODE_SUBAGENT_MODEL": "sonnet"}}

        merged = merged_settings(mac, BOX_SETTINGS)

        assert merged["env"] == {"GIT_SSH_COMMAND": "keyguard-ssh", "CLAUDE_CODE_SUBAGENT_MODEL": "sonnet"}

    def should_keep_an_env_variable_the_box_sets(self, merged_settings):
        mac = {"env": {"GIT_SSH_COMMAND": "ssh"}}

        assert merged_settings(mac, BOX_SETTINGS)["env"] == BOX_SETTINGS["env"]

    def should_keep_marketplaces_from_updating_themselves(self, merged_settings):
        box = {"extraKnownMarketplaces": {"box-only": {"source": MARKETPLACE_SOURCE, "autoUpdate": True}}}

        merged = merged_settings({}, box)

        assert merged["extraKnownMarketplaces"]["box-only"]["autoUpdate"] is False

    def should_keep_claude_ai_out_whatever_the_mac_says(self, merged_settings):
        mac = {"syncClaudeAiPlugins": True, "syncClaudeAiSkills": True, "disableClaudeAiConnectors": False}

        assert merged_settings(mac, {}) == SYNC_OFF

    def should_change_nothing_once_applied(self, merged_settings):
        assert merged_settings(MAC_SETTINGS, EXPECTED_BOX) == EXPECTED_BOX

    def should_not_push_when_the_box_already_matches(self, load_script, monkeypatch, tmp_path):
        script = load_script("claude-sync")
        home = tmp_path / "isolated"
        (home / "settings.json").write_text(json.dumps(MAC_SETTINGS))

        def pull_matching(_home, target):
            target.write_text(json.dumps(EXPECTED_BOX))
            return True

        pushes = []
        monkeypatch.setattr(script, "pull_devbox_settings", pull_matching)
        monkeypatch.setattr(script, "transfer", lambda _home, commands, _stream=False: pushes.append(commands) or 0)

        assert script.sync_devbox_settings(home, stream=False) == 0
        assert pushes == []


@requires_tool("rsync")
class TestSettingsSync:
    @pytest.fixture
    def run(self, load_script, monkeypatch, tmp_path, fake_ssh):
        monkeypatch.delenv("CLAUDE_SYNC_RSYNC")
        mac = tmp_path / "mac-claude"
        write_tree(mac, {"settings.json": json.dumps(MAC_SETTINGS)})
        box = tmp_path / "devbox-claude"
        box.mkdir()
        monkeypatch.setenv("CLAUDE_SYNC_REMOTE", "devbox")
        monkeypatch.setenv("CLAUDE_SYNC_REMOTE_HOME", str(box))
        script = load_script("claude-sync")
        monkeypatch.setattr(script, "SSH_COMMAND", str(fake_ssh))
        return SimpleNamespace(sync=lambda: script.sync_devbox_settings(mac, stream=False), file=box / "settings.json")

    def should_write_the_mac_settings_into_the_box_settings(self, run):
        run.file.write_text(json.dumps(BOX_SETTINGS))

        assert run.sync() == 0
        assert json.loads(run.file.read_text()) == EXPECTED_BOX

    def should_create_the_box_settings_when_missing(self, run):
        assert run.sync() == 0
        assert json.loads(run.file.read_text()) == MAC_SETTINGS_ON_THE_BOX

    def should_skip_a_box_file_it_cannot_parse(self, run):
        run.file.write_text("{broken")

        assert run.sync() == 1
        assert run.file.read_text() == "{broken"


class TestSettingsWiring:
    @pytest.fixture
    def mac_settings(self, claude_home):
        (claude_home / "settings.json").write_text(json.dumps(MAC_SETTINGS))

    @pytest.mark.usefixtures("mac_settings")
    def should_pull_and_push_the_box_settings_on_a_push(self, sync, rsync_log):
        sync(["--push"])

        assert len(settings_runs(rsync_log)) == 2

    @pytest.mark.usefixtures("mac_settings")
    def should_never_touch_the_box_settings_on_a_pull(self, sync, rsync_log):
        sync(["--pull"])

        assert settings_runs(rsync_log) == []

    @pytest.mark.usefixtures("mac_settings")
    @pytest.mark.parametrize("rsync_exit", [255, 23])
    def should_not_push_when_the_pull_did_not_prove_the_file_missing(self, sync, rsync_log, rsync_exit):
        sync(["--push"], rsync_exit=rsync_exit)

        assert len(settings_runs(rsync_log)) == 1

    def should_skip_the_settings_without_mac_settings(self, sync, rsync_log):
        sync(["--push"])

        assert settings_runs(rsync_log) == []


class TestRsyncBinary:
    @pytest.fixture
    def script(self, load_script, monkeypatch):
        monkeypatch.delenv("CLAUDE_SYNC_RSYNC")
        return load_script("claude-sync")

    def should_prefer_homebrew_gnu_rsync_over_the_path(self, script, monkeypatch, tmp_path):
        gnu = tmp_path / "rsync"
        gnu.write_text("#!/bin/sh\n")
        gnu.chmod(0o755)
        monkeypatch.setattr(script, "RSYNC_CANDIDATES", (str(tmp_path / "missing"), str(gnu)))

        assert script.rsync_binary() == str(gnu)

    def should_fall_back_to_rsync_on_the_path(self, script, monkeypatch, tmp_path):
        monkeypatch.setattr(script, "RSYNC_CANDIDATES", (str(tmp_path / "missing"),))

        assert script.rsync_binary() == "rsync"

    def should_honour_an_explicit_override(self, script, monkeypatch):
        monkeypatch.setenv("CLAUDE_SYNC_RSYNC", "/custom/rsync")

        assert script.rsync_binary() == "/custom/rsync"

    def should_build_every_command_with_the_chosen_rsync(self, script, monkeypatch):
        monkeypatch.setenv("CLAUDE_SYNC_RSYNC", "/custom/rsync")

        assert script.rsync_command(["a"], "b", [])[0] == "/custom/rsync"
        assert script.mirror_rsync()[0] == "/custom/rsync"
