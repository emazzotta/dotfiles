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


def _short_head(repo):
    return _git("rev-parse", "--short", "HEAD", cwd=repo).stdout.strip()


def _plugins_dir(home):
    path = home / ".claude" / "plugins"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_registry(home, marketplaces):
    (_plugins_dir(home) / "known_marketplaces.json").write_text(json.dumps(marketplaces))


def _call_function(home, snippet):
    return subprocess.run(
        ["bash", "-c", f'source "{BIN_DIR / SCRIPT}"; {snippet}'],
        env={**os.environ, "HOME": str(home)}, capture_output=True, text=True,
    )


@pytest.fixture
def home(tmp_path):
    path = tmp_path / "home"
    _plugins_dir(path)
    return path


class TestUsage:
    @pytest.mark.parametrize("flag", ["-h", "--help"])
    def should_show_usage_for_help_flag(self, run_bash, flag):
        result = run_bash(SCRIPT, [flag])
        assert result.returncode == 0
        assert "Usage:" in result.stdout

    def should_fail_when_the_marketplace_registry_is_missing(self, run_bash, tmp_path):
        result = run_bash(SCRIPT, env_extra={"HOME": str(tmp_path / "absent")})
        assert result.returncode == 1
        assert "No marketplace registry" in result.stderr


class TestFindSshMarketplaces:
    def should_list_only_git_sources_reached_over_ssh(self, home):
        _write_registry(home, {
            "ssh-one": {"source": {"source": "git", "url": SSH_REMOTE}},
            "ssh-two": {"source": {"source": "git", "url": "ssh://git@example.invalid/x.git"}},
            "https-git": {"source": {"source": "git", "url": "https://example.invalid/x.git"}},
            "github": {"source": {"source": "github", "repo": "owner/repo"}},
        })

        result = _call_function(home, "find_ssh_marketplaces")

        assert result.stdout == (
            f"ssh-one\t{SSH_REMOTE}\n"
            "ssh-two\tssh://git@example.invalid/x.git\n"
        )

    def should_stay_quiet_when_the_registry_is_unreadable(self, home):
        (_plugins_dir(home) / "known_marketplaces.json").write_text("{ not json")

        result = _call_function(home, "find_ssh_marketplaces")

        assert result.stdout == ""


class TestMirrorMarketplace:
    def _mirror(self, home, name, url):
        (_plugins_dir(home) / "ssh-mirrors").mkdir(exist_ok=True)
        return _call_function(home, f'mirror_marketplace "{name}" "{url}"')

    def should_create_the_mirror_on_first_run(self, tmp_path, home):
        upstream = _make_upstream(tmp_path / "upstream")

        result = self._mirror(home, "mp", str(upstream))

        mirror = _plugins_dir(home) / "ssh-mirrors" / "mp.git"
        assert result.returncode == 0
        assert f"mp: mirrored ({_short_head(upstream)})" in result.stdout
        assert (mirror / "HEAD").exists()

    def should_report_up_to_date_when_upstream_has_not_moved(self, tmp_path, home):
        upstream = _make_upstream(tmp_path / "upstream")
        self._mirror(home, "mp", str(upstream))

        result = self._mirror(home, "mp", str(upstream))

        assert f"mp: up to date ({_short_head(upstream)})" in result.stdout

    def should_fetch_new_commits_into_an_existing_mirror(self, tmp_path, home):
        upstream = _make_upstream(tmp_path / "upstream")
        self._mirror(home, "mp", str(upstream))
        before = _short_head(upstream)
        _commit(upstream, "two")

        result = self._mirror(home, "mp", str(upstream))

        assert f"mp: {before} -> {_short_head(upstream)}" in result.stdout

    def should_report_a_failure_without_creating_a_mirror(self, tmp_path, home):
        result = self._mirror(home, "mp", str(tmp_path / "nowhere"))

        assert result.returncode == 1
        assert "mp: FAILED to mirror" in result.stdout
        assert not (_plugins_dir(home) / "ssh-mirrors" / "mp.git").exists()


@pytest.fixture
def container_home(tmp_path):
    home = tmp_path / "container-home"
    plugins = _plugins_dir(home)
    _write_registry(home, {
        "mp-ssh": {"source": {"source": "git", "url": SSH_REMOTE}},
        "mp-https": {"source": {"source": "github", "repo": "owner/repo"}},
    })
    (plugins / "ssh-mirrors" / "mp-ssh.git").mkdir(parents=True)
    (plugins / "installed_plugins.json").write_text(json.dumps({
        "version": 2,
        "plugins": {
            "wanted@mp-ssh": [{"scope": "user"}],
            "other@mp-https": [{"scope": "user"}],
            "project-only@mp-https": [{"scope": "project"}],
        },
    }))
    return home


class TestGitRewrites:
    def _write(self, run_bash, home, mock_bins=None):
        return run_bash(SCRIPT, ["--write-git-rewrites"],
                        env_extra={"HOME": str(home)},
                        mock_bins=mock_bins or IN_CONTAINER)

    def should_point_each_ssh_marketplace_at_its_mirror(self, run_bash, container_home):
        result = self._write(run_bash, container_home)

        rewrites = (container_home / ".gitconfig-claude-plugins").read_text()
        mirror = _plugins_dir(container_home) / "ssh-mirrors" / "mp-ssh.git"
        assert result.returncode == 0
        assert f'[url "{mirror}"]' in rewrites
        assert f"insteadOf = {SSH_REMOTE}" in rewrites
        assert "mp-https" not in rewrites

    def should_scope_the_include_to_the_plugins_directory(self, run_bash, container_home):
        self._write(run_bash, container_home)

        config = (container_home / ".gitconfig").read_text()
        assert f'includeIf "gitdir:{_plugins_dir(container_home)}/"' in config
        assert str(container_home / ".gitconfig-claude-plugins") in config

    def should_stay_unchanged_when_run_twice(self, run_bash, container_home):
        self._write(run_bash, container_home)
        first = (container_home / ".gitconfig").read_text()

        self._write(run_bash, container_home)

        assert (container_home / ".gitconfig").read_text() == first
        assert first.count("includeIf") == 1

    def should_warn_about_a_marketplace_with_no_mirror(self, run_bash, container_home):
        (_plugins_dir(container_home) / "ssh-mirrors" / "mp-ssh.git").rmdir()

        result = self._write(run_bash, container_home)

        assert "No mirror for mp-ssh" in result.stderr
        assert (container_home / ".gitconfig-claude-plugins").read_text().strip() == ""

    def should_refuse_to_write_rewrites_on_the_mac(self, run_bash, container_home):
        result = self._write(run_bash, container_home, mock_bins=ON_MAC)

        assert result.returncode == 1
        assert "Refusing to write git rewrites on the Mac" in result.stderr
        assert not (container_home / ".gitconfig-claude-plugins").exists()


class TestUpdateInContainer:
    def _run(self, run_bash, home, log, args=None, envify="echo mirrors-refreshed"):
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
        assert "mirrors-refreshed" in result.stdout
        assert "plugin marketplace update" in calls
        assert "wanted@mp-ssh" in calls
        assert "other@mp-https" in calls
        assert "project-only@mp-https" not in calls

    def should_update_only_plugins_matching_the_filter(
        self, run_bash, container_home, tmp_path
    ):
        log = tmp_path / "claude.log"

        self._run(run_bash, container_home, log, args=["wanted"])

        calls = log.read_text()
        assert "wanted@mp-ssh" in calls
        assert "other@mp-https" not in calls

    def should_refuse_to_update_when_a_mirror_is_missing(
        self, run_bash, container_home, tmp_path
    ):
        (_plugins_dir(container_home) / "ssh-mirrors" / "mp-ssh.git").rmdir()
        log = tmp_path / "claude.log"

        result = self._run(run_bash, container_home, log)

        assert result.returncode == 1
        assert "Refusing to update" in result.stderr
        assert not log.exists()

    def should_continue_when_the_bridge_call_fails(
        self, run_bash, container_home, tmp_path
    ):
        log = tmp_path / "claude.log"

        result = self._run(run_bash, container_home, log, envify="exit 1")

        assert "Bridge call failed" in result.stderr
        assert "wanted@mp-ssh" in log.read_text()
