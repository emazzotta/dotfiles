import json
import os
import subprocess
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).parent.parent
SCRIPT = "claude-plugin-update"
SSH_REMOTE = "git@example.invalid:foo/bar.git"
ON_MAC = {"uname": "echo Darwin"}
IN_CONTAINER = {"uname": "echo Linux"}


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


def _marketplaces_dir(home):
    path = home / ".claude" / "plugins" / "marketplaces"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _clone(upstream, home, name):
    marketplaces = _marketplaces_dir(home)
    _git("clone", "-q", str(upstream), name, cwd=marketplaces)
    return marketplaces / name


def _short_head(repo):
    return _git("rev-parse", "--short", "HEAD", cwd=repo).stdout.strip()


@pytest.fixture
def home(tmp_path):
    path = tmp_path / "home"
    _marketplaces_dir(path)
    return path


class TestUsage:
    @pytest.mark.parametrize("flag", ["-h", "--help"])
    def should_show_usage_for_help_flag(self, run_bash, flag):
        result = run_bash(SCRIPT, [flag])
        assert result.returncode == 0
        assert "Usage:" in result.stdout

    def should_fail_when_marketplaces_directory_is_missing(self, run_bash, tmp_path):
        result = run_bash(SCRIPT, env_extra={"HOME": str(tmp_path / "absent")})
        assert result.returncode == 1
        assert "No marketplaces directory" in result.stderr


class TestPullOnMac:
    def should_report_up_to_date_when_clone_matches_upstream(
        self, run_bash, tmp_path, home
    ):
        upstream = _make_upstream(tmp_path / "upstream")
        clone = _clone(upstream, home, "mp")

        result = run_bash(SCRIPT, env_extra={"HOME": str(home)}, mock_bins=ON_MAC)

        assert result.returncode == 0
        assert f"mp: up to date ({_short_head(clone)})" in result.stdout
        assert "1 marketplace(s), 0 failed" in result.stdout

    def should_fast_forward_clone_when_upstream_moved(self, run_bash, tmp_path, home):
        upstream = _make_upstream(tmp_path / "upstream")
        clone = _clone(upstream, home, "mp")
        before = _short_head(clone)
        _commit(upstream, "two")

        result = run_bash(SCRIPT, env_extra={"HOME": str(home)}, mock_bins=ON_MAC)

        after = _short_head(clone)
        assert after != before
        assert f"mp: {before} -> {after}" in result.stdout

    def should_skip_directories_that_are_not_git_clones(self, run_bash, home):
        (_marketplaces_dir(home) / "plain").mkdir()

        result = run_bash(SCRIPT, env_extra={"HOME": str(home)}, mock_bins=ON_MAC)

        assert "plain: skipped (not a git clone)" in result.stdout
        assert "1 marketplace(s), 0 failed" in result.stdout

    def should_keep_pulling_after_one_marketplace_fails(self, run_bash, tmp_path, home):
        healthy_upstream = _make_upstream(tmp_path / "healthy-upstream")
        healthy = _clone(healthy_upstream, home, "healthy")
        before = _short_head(healthy)
        _commit(healthy_upstream, "two")
        broken_upstream = _make_upstream(tmp_path / "broken-upstream")
        _clone(broken_upstream, home, "broken")
        subprocess.run(["rm", "-rf", str(broken_upstream)], check=True)

        result = run_bash(SCRIPT, env_extra={"HOME": str(home)}, mock_bins=ON_MAC)

        assert result.returncode == 0
        assert "broken: FAILED" in result.stdout
        assert f"healthy: {before} -> {_short_head(healthy)}" in result.stdout
        assert "2 marketplace(s), 1 failed" in result.stdout


@pytest.fixture
def container_home(tmp_path):
    home = tmp_path / "container-home"
    marketplaces = _marketplaces_dir(home)
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


class TestContainerGuards:
    def should_report_a_missing_required_command(self, run_bash, container_home):
        result = run_bash(SCRIPT, env_extra={"HOME": str(container_home)},
                          mock_bins=IN_CONTAINER, isolate_path=True)
        assert result.returncode == 1
        assert "claude" in result.stderr


class TestGitRewrites:
    def _write(self, run_bash, home, mock_bins=None):
        return run_bash(SCRIPT, ["--write-git-rewrites"],
                        env_extra={"HOME": str(home)},
                        mock_bins=mock_bins or IN_CONTAINER)

    def should_rewrite_only_ssh_marketplace_remotes_to_their_local_clone(
        self, run_bash, container_home
    ):
        result = self._write(run_bash, container_home)

        rewrites = (container_home / ".gitconfig-claude-plugins").read_text()
        clone = container_home / ".claude" / "plugins" / "marketplaces" / "mp-ssh"
        assert result.returncode == 0
        assert f'[url "{clone}"]' in rewrites
        assert f"insteadOf = {SSH_REMOTE}" in rewrites
        assert "mp-https" not in rewrites

    def should_scope_the_include_to_the_plugins_directory(
        self, run_bash, container_home
    ):
        self._write(run_bash, container_home)

        config = (container_home / ".gitconfig").read_text()
        plugins_dir = container_home / ".claude" / "plugins"
        assert f'includeIf "gitdir:{plugins_dir}/"' in config
        assert str(container_home / ".gitconfig-claude-plugins") in config

    def should_stay_unchanged_when_run_twice(self, run_bash, container_home):
        self._write(run_bash, container_home)
        first = (container_home / ".gitconfig").read_text()

        self._write(run_bash, container_home)

        assert (container_home / ".gitconfig").read_text() == first
        assert first.count("includeIf") == 1

    def should_refuse_to_write_rewrites_on_the_mac(self, run_bash, container_home):
        result = self._write(run_bash, container_home, mock_bins=ON_MAC)

        assert result.returncode == 1
        assert "Refusing to write git rewrites on the Mac" in result.stderr
        assert not (container_home / ".gitconfig-claude-plugins").exists()


class TestUpdateInContainer:
    def _run(self, run_bash, home, log, args=None, envify="echo pulled-on-mac"):
        return run_bash(
            SCRIPT, args,
            env_extra={"HOME": str(home), "LOG": str(log)},
            mock_bins={
                **IN_CONTAINER,
                "envify": envify,
                "claude": 'echo "$*" >> "$LOG"',
            },
        )

    def should_update_every_user_scope_plugin_through_the_bridge(
        self, run_bash, container_home, tmp_path
    ):
        log = tmp_path / "claude.log"

        result = self._run(run_bash, container_home, log)

        calls = log.read_text()
        assert "pulled-on-mac" in result.stdout
        assert "plugin marketplace update" in calls
        assert "plugin update wanted@mp-ssh -y" in calls
        assert "plugin update other@mp-https -y" in calls
        assert (container_home / ".gitconfig-claude-plugins").exists()
        assert "project-only@mp-https" not in calls

    def should_update_only_plugins_matching_the_filter(
        self, run_bash, container_home, tmp_path
    ):
        log = tmp_path / "claude.log"

        self._run(run_bash, container_home, log, args=["wanted"])

        calls = log.read_text()
        assert "plugin update wanted@mp-ssh -y" in calls
        assert "plugin update other@mp-https" not in calls

    def should_continue_when_the_bridge_call_fails(
        self, run_bash, container_home, tmp_path
    ):
        log = tmp_path / "claude.log"

        result = self._run(run_bash, container_home, log, envify="exit 1")

        assert "Bridge call failed" in result.stderr
        assert "plugin update wanted@mp-ssh -y" in log.read_text()
