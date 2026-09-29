import fcntl
import json
from types import SimpleNamespace

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
MAC_SETTINGS = {
    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "stop-bell"}]}]},
    "theme": "light",
    "enabledPlugins": {"leonardo@leonardo-skills": True, "superpowers@claude-plugins-official": False},
}
BOX_SETTINGS = {"theme": "dark", "tui": "fullscreen", "enabledPlugins": {"old@marketplace": True}}
SYNC_OFF = {"syncClaudeAiPlugins": False, "syncClaudeAiSkills": False, "disableClaudeAiConnectors": True}
EXPECTED_BOX = {"theme": "dark", "tui": "fullscreen", "enabledPlugins": MAC_SETTINGS["enabledPlugins"], **SYNC_OFF}
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
        for name in ("CLAUDE_SYNC_REMOTE", "CLAUDE_SYNC_REMOTE_HOME", "CLAUDE_SYNC_REMOTE_WORKSPACE"):
            monkeypatch.delenv(name, raising=False)
        return load_script("claude-sync")

    def should_reach_the_dev_box_through_its_ssh_alias(self, script):
        assert script.remote_base().startswith("devbox:")

    def should_mirror_into_the_dev_box_workspace(self, script):
        assert script.remote_workspace() == "devbox:/workspace"

    def should_not_request_a_tty_for_a_binary_transfer(self, script):
        assert "RequestTTY=no" in script.SSH_COMMAND


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

    def should_take_enabled_plugins_from_the_mac_and_keep_the_box_own_keys(self, merged_settings):
        assert merged_settings(MAC_SETTINGS, BOX_SETTINGS) == EXPECTED_BOX

    def should_keep_the_box_list_when_the_mac_has_none(self, merged_settings):
        assert merged_settings({"theme": "light"}, BOX_SETTINGS)["enabledPlugins"] == BOX_SETTINGS["enabledPlugins"]

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

    def should_write_the_owned_keys_into_the_box_settings(self, run):
        run.file.write_text(json.dumps(BOX_SETTINGS))

        assert run.sync() == 0
        assert json.loads(run.file.read_text()) == EXPECTED_BOX

    def should_create_the_box_settings_when_missing(self, run):
        assert run.sync() == 0
        assert json.loads(run.file.read_text()) == {"enabledPlugins": MAC_SETTINGS["enabledPlugins"], **SYNC_OFF}

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
