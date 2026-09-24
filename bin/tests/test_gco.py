import os
import subprocess

import pytest

from bin.tests.conftest import BIN_DIR, requires_tool

FUNCTIONS = BIN_DIR.parent / "bash" / ".bashrc.d" / "20-functions.sh"
SHELLS = {"bash": ["bash"], "zsh": ["zsh", "-f"]}


@pytest.fixture(params=["bash", pytest.param("zsh", marks=requires_tool("zsh"))])
def gco(request, git_env):
    def _gco(cwd, *args):
        script = f'source "{FUNCTIONS}"; gco "$@"; rc=$?; pwd; exit $rc'
        env = {**os.environ, **git_env, "PATH": f"{BIN_DIR}:{os.environ['PATH']}"}
        return subprocess.run([*SHELLS[request.param], "-c", script, "gco", *args],
                              capture_output=True, text=True, cwd=cwd, env=env)
    return _gco


def final_dir(result):
    return result.stdout.splitlines()[-1]


class TestGco:
    def should_enter_the_checkout_of_a_branch_that_a_worktree_holds(self, gco, added, project):
        path = added("feature")

        result = gco(project, "feature")

        assert result.returncode == 0, result.stderr
        assert final_dir(result) == str(path)

    def should_return_to_the_main_checkout_for_its_branch(self, gco, added, project):
        path = added("feature")

        result = gco(path, "main")

        assert result.returncode == 0, result.stderr
        assert final_dir(result) == str(project)

    def should_stay_in_the_current_worktree_for_its_own_branch(self, gco, added):
        path = added("feature")
        (path / "src").mkdir()

        result = gco(path / "src", "feature")

        assert result.returncode == 0, result.stderr
        assert final_dir(result) == str(path / "src")
        assert "Already on 'feature'" in result.stderr

    def should_check_out_a_branch_that_no_worktree_holds(self, gco, git, project):
        git(project, "branch", "plain")

        result = gco(project, "plain")

        assert result.returncode == 0, result.stderr
        assert final_dir(result) == str(project)
        assert git(project, "symbolic-ref", "--short", "HEAD") == "plain"

    def should_pass_several_arguments_to_git_checkout(self, gco, git, project):
        result = gco(project, "-b", "fresh")

        assert result.returncode == 0, result.stderr
        assert git(project, "symbolic-ref", "--short", "HEAD") == "fresh"
