import os
import re
import subprocess
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).parent.parent
TERMINAL_ESCAPES = re.compile(r"\x1b\]8;;[^\x1b]*\x1b\\|\x1b\[[0-9;]*m")

GLAB_MOCK = r'''
case "$*" in
    "mr list"*) ;;
    *"pipelines?ref=main&"*) echo '[{"id": 1, "status": "success", "updated_at": "t1", "web_url": "https://gitlab.example.com/p/1"}]' ;;
    *"pipelines?ref=feature&"*) echo '[{"id": 2, "status": "failed", "updated_at": "t2", "web_url": "https://gitlab.example.com/p/2"}]' ;;
    *"pipelines?ref=remote-only&"*) echo '[{"id": 3, "status": "running", "updated_at": "t3", "web_url": "https://gitlab.example.com/p/3"}]' ;;
    *"pipelines/2/jobs"*) echo '[{"id": 20, "name": "Test", "failure_reason": "script_failure", "allow_failure": false}]' ;;
    *"jobs/20/trace"*) echo '[ERROR] There are test failures.' ;;
    *) echo '[]' ;;
esac
'''


@pytest.fixture
def git_env(tmp_path):
    config = tmp_path / "gitconfig"
    config.write_text("[user]\n\tname = Test\n\temail = test@example.com\n"
                      "[init]\n\tdefaultBranch = main\n"
                      "[safe]\n\tdirectory = *\n")
    return {"GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1"}


@pytest.fixture
def git(git_env):
    def _git(cwd, *args):
        result = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                                env={**os.environ, **git_env})
        assert result.returncode == 0, result.stderr
    return _git


@pytest.fixture
def workspace(tmp_path, git):
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", str(origin))
    project = tmp_path / "workspace" / "project"
    git(tmp_path, "clone", str(origin), str(project))
    git(project, "commit", "--allow-empty", "-m", "Start")
    git(project, "branch", "feature")
    git(project, "commit", "--allow-empty", "-m", "Advance main")
    git(project, "commit", "--allow-empty", "-m", "Advance main again")
    git(project, "push", "origin", "main", "feature", "main:remote-only")
    git(project, "remote", "set-head", "origin", "main")
    git(project, "remote", "set-url", "origin", "git@gitlab.example.com:group/project.git")
    return tmp_path / "workspace"


@pytest.fixture
def gck(run_bash, tmp_path, git_env):
    def _gck(workspace):
        result = run_bash("gck", [str(workspace)], mock_bins={"glab": GLAB_MOCK},
                          env_extra={**git_env, "CUSTOM_BIN_DIR": str(BIN_DIR), "WDIR": str(workspace),
                                     "HOME": str(tmp_path / "home")})
        assert result.returncode == 0, result.stderr
        return TERMINAL_ESCAPES.sub("", result.stdout)
    return _gck


def should_list_each_branch_with_its_ci_state_commits_behind_main_and_failure_category(gck, workspace):
    output = gck(workspace)

    assert re.search(r"✗ feature\s+↓2\s+tests$", output, re.MULTILINE)
    assert re.search(r"● remote-only\s+running$", output, re.MULTILINE)


def should_show_the_ci_state_of_main_next_to_each_repository(gck, workspace):
    output = gck(workspace)

    assert re.search(r"/project\s+main ✓$", output, re.MULTILINE)


def should_still_show_how_far_behind_main_a_branch_is_without_a_ci_host(gck, workspace, git):
    git(workspace / "project", "remote", "set-url", "origin", str(workspace.parent / "origin.git"))

    output = gck(workspace)

    assert re.search(r"^\s+feature\s+↓2$", output, re.MULTILINE)
    assert "✓" not in output
