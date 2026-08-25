import json
import os
import subprocess
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).parent.parent
BRIDGE_SCRIPT = "bridge-claude-plugin-update"
WRAPPER_SCRIPT = "claude-plugin-update"
SSH_REMOTE = "git@example.invalid:foo/bar.git"


def _git(*args, cwd):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
    }
    return subprocess.run(["git", *args], cwd=str(cwd), env=env,
                          check=True, capture_output=True, text=True)


def _commit(repo, text):
    (repo / "README").write_text(text)
    _git("add", "-A", cwd=repo)
    _git("commit", "-qm", text, cwd=repo)


def _make_upstream(path):
    path.mkdir(parents=True)
    _git("init", "-q", "-b", "main", ".", cwd=path)
    _commit(path, "one")
    return path


def _clone(upstream, marketplaces_dir, name):
    _git("clone", "-q", str(upstream), name, cwd=marketplaces_dir)
    return marketplaces_dir / name


def _short_head(repo):
    return _git("rev-parse", "--short", "HEAD", cwd=repo).stdout.strip()


@pytest.fixture
def marketplaces_dir(tmp_path):
    path = tmp_path / "marketplaces"
    path.mkdir()
    return path


class TestBridgeScriptUsage:
    @pytest.mark.parametrize("flag", ["-h", "--help"])
    def should_show_usage_for_help_flag(self, run_bash, flag):
        result = run_bash(BRIDGE_SCRIPT, [flag])
        assert result.returncode == 0
        assert "Usage:" in result.stdout

    def should_fail_when_marketplaces_directory_is_missing(self, run_bash, tmp_path):
        result = run_bash(BRIDGE_SCRIPT, [str(tmp_path / "absent")])
        assert result.returncode == 1
        assert "No marketplaces directory" in result.stderr


class TestBridgeScriptPull:
    def should_report_up_to_date_when_clone_matches_upstream(
        self, run_bash, tmp_path, marketplaces_dir
    ):
        upstream = _make_upstream(tmp_path / "upstream")
        clone = _clone(upstream, marketplaces_dir, "mp")

        result = run_bash(BRIDGE_SCRIPT, [str(marketplaces_dir)])

        assert result.returncode == 0
        assert f"mp: up to date ({_short_head(clone)})" in result.stdout
        assert "1 marketplace(s), 0 failed" in result.stdout

    def should_fast_forward_clone_when_upstream_moved(
        self, run_bash, tmp_path, marketplaces_dir
    ):
        upstream = _make_upstream(tmp_path / "upstream")
        clone = _clone(upstream, marketplaces_dir, "mp")
        before = _short_head(clone)
        _commit(upstream, "two")

        result = run_bash(BRIDGE_SCRIPT, [str(marketplaces_dir)])

        after = _short_head(clone)
        assert after != before
        assert f"mp: {before} -> {after}" in result.stdout

    def should_skip_directories_that_are_not_git_clones(
        self, run_bash, marketplaces_dir
    ):
        (marketplaces_dir / "plain").mkdir()

        result = run_bash(BRIDGE_SCRIPT, [str(marketplaces_dir)])

        assert "plain: skipped (not a git clone)" in result.stdout
        assert "1 marketplace(s), 0 failed" in result.stdout

    def should_keep_pulling_after_one_marketplace_fails(
        self, run_bash, tmp_path, marketplaces_dir
    ):
        healthy_upstream = _make_upstream(tmp_path / "healthy-upstream")
        healthy = _clone(healthy_upstream, marketplaces_dir, "healthy")
        before = _short_head(healthy)
        _commit(healthy_upstream, "two")
        broken_upstream = _make_upstream(tmp_path / "broken-upstream")
        _clone(broken_upstream, marketplaces_dir, "broken")
        subprocess.run(["rm", "-rf", str(broken_upstream)], check=True)

        result = run_bash(BRIDGE_SCRIPT, [str(marketplaces_dir)])

        assert result.returncode == 0
        assert "broken: FAILED" in result.stdout
        assert f"healthy: {before} -> {_short_head(healthy)}" in result.stdout
        assert "2 marketplace(s), 1 failed" in result.stdout


@pytest.fixture
def fake_claude_home(tmp_path):
    home = tmp_path / "home"
    marketplaces = home / ".claude" / "plugins" / "marketplaces"
    marketplaces.mkdir(parents=True)
    for name, remote in (("mp-ssh", SSH_REMOTE),
                         ("mp-https", "https://example.invalid/foo/bar.git")):
        repo = marketplaces / name
        repo.mkdir()
        _git("init", "-q", "-b", "main", ".", cwd=repo)
        _git("remote", "add", "origin", remote, cwd=repo)
    (marketplaces.parent / "installed_plugins.json").write_text(json.dumps({
        "version": 2,
        "plugins": {
            "wanted@mp-ssh": [{"scope": "user"}],
            "other@mp-https": [{"scope": "user"}],
            "project-only@mp-https": [{"scope": "project"}],
        },
    }))
    return home


class TestWrapperGuards:
    @pytest.mark.parametrize("flag", ["-h", "--help"])
    def should_show_usage_for_help_flag(self, run_bash, flag):
        result = run_bash(WRAPPER_SCRIPT, [flag])
        assert result.returncode == 0
        assert "Usage:" in result.stdout

    def should_refuse_to_run_on_the_mac(self, run_bash):
        result = run_bash(WRAPPER_SCRIPT, mock_bins={"uname": "echo Darwin"})
        assert result.returncode == 2
        assert "Container-only" in result.stderr

    def should_report_a_missing_required_command(self, run_bash):
        result = run_bash(WRAPPER_SCRIPT, mock_bins={"uname": "echo Linux"},
                          isolate_path=True)
        assert result.returncode == 1
        assert "claude" in result.stderr


class TestWrapperRewrites:
    def should_rewrite_only_ssh_marketplace_remotes_to_their_local_clone(
        self, fake_claude_home
    ):
        result = subprocess.run(
            ["bash", "-c", f'source "{BIN_DIR / WRAPPER_SCRIPT}"; build_local_clone_rewrites'],
            env={**os.environ, "HOME": str(fake_claude_home)},
            capture_output=True, text=True,
        )

        clone = fake_claude_home / ".claude" / "plugins" / "marketplaces" / "mp-ssh"
        assert f"GIT_CONFIG_KEY_0=url.{clone}.insteadOf" in result.stdout
        assert f"GIT_CONFIG_VALUE_0={SSH_REMOTE}" in result.stdout
        assert "GIT_CONFIG_COUNT=1" in result.stdout
        assert "mp-https" not in result.stdout


class TestWrapperUpdates:
    def _run(self, run_bash, home, log, args=None):
        return run_bash(
            WRAPPER_SCRIPT, args,
            env_extra={"HOME": str(home), "LOG": str(log)},
            mock_bins={
                "uname": "echo Linux",
                "envify": "echo pulled-on-mac",
                "claude": 'echo "$* count=${GIT_CONFIG_COUNT:-unset}" >> "$LOG"',
            },
        )

    def should_update_every_user_scope_plugin_through_the_bridge(
        self, run_bash, fake_claude_home, tmp_path
    ):
        log = tmp_path / "claude.log"

        result = self._run(run_bash, fake_claude_home, log)

        calls = log.read_text()
        assert "pulled-on-mac" in result.stdout
        assert "plugin marketplace update count=1" in calls
        assert "plugin update wanted@mp-ssh -y count=1" in calls
        assert "plugin update other@mp-https -y count=1" in calls
        assert "project-only@mp-https" not in calls

    def should_update_only_plugins_matching_the_filter(
        self, run_bash, fake_claude_home, tmp_path
    ):
        log = tmp_path / "claude.log"

        self._run(run_bash, fake_claude_home, log, args=["wanted"])

        calls = log.read_text()
        assert "plugin update wanted@mp-ssh -y" in calls
        assert "plugin update other@mp-https" not in calls

    def should_continue_when_the_bridge_call_fails(
        self, run_bash, fake_claude_home, tmp_path
    ):
        log = tmp_path / "claude.log"

        result = run_bash(
            WRAPPER_SCRIPT,
            env_extra={"HOME": str(fake_claude_home), "LOG": str(log)},
            mock_bins={
                "uname": "echo Linux",
                "envify": "exit 1",
                "claude": 'echo "$*" >> "$LOG"',
            },
        )

        assert "Bridge call failed" in result.stderr
        assert "plugin update wanted@mp-ssh -y" in log.read_text()
