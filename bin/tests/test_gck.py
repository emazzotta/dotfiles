import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).parent.parent
TERMINAL_ESCAPES = re.compile(r"\x1b\]8;;[^\x1b]*\x1b\\|\x1b\[[0-9;]*m")

GLAB_MOCK = r'''
printf '%s\n' "$*" >> "${GLAB_CALLS:-/dev/null}"
case "$*" in
    "mr list"*) ;;
    *"pipelines?scope=branches&"*) echo '[
        {"id": 3, "ref": "remote-only", "status": "running", "updated_at": "t3", "web_url": "https://gitlab.example.com/p/3"},
        {"id": 2, "ref": "feature", "status": "failed", "updated_at": "t2", "web_url": "https://gitlab.example.com/p/2"},
        {"id": 1, "ref": "main", "status": "success", "updated_at": "t1", "web_url": "https://gitlab.example.com/p/1"}]' ;;
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
def unpushed_workspace(workspace, git, tmp_path):
    project = workspace / "project"
    spike_worktree = project / ".claude" / "worktrees" / "spike"
    git(project, "remote", "set-url", "origin", str(tmp_path / "origin.git"))
    git(project, "checkout", "-q", "feature")
    git(project, "commit", "--allow-empty", "-m", "Not pushed yet")
    git(project, "checkout", "-q", "-b", "rewritten", "main")
    git(project, "commit", "--allow-empty", "-m", "Pushed once")
    git(project, "push", "-q", "origin", "rewritten")
    git(project, "commit", "--amend", "--allow-empty", "-m", "Pushed once, then amended")
    git(project, "checkout", "-q", "-b", "merged", "main")
    git(project, "commit", "--allow-empty", "-m", "Squash merged upstream")
    git(project, "push", "-q", "-u", "origin", "merged")
    git(project, "push", "-q", "origin", "--delete", "merged")
    git(project, "checkout", "-q", "main")
    git(project, "worktree", "add", "-q", "-b", "spike", str(spike_worktree), "main")
    git(spike_worktree, "commit", "--allow-empty", "-m", "Local experiment")
    git(project, "remote", "set-url", "origin", "git@gitlab.example.com:group/project.git")
    return workspace


@pytest.fixture
def dirty_workspace(workspace, git):
    project = workspace / "project"
    (project / "idea.txt").write_text("maybe\n")
    git(project, "stash", "push", "--include-untracked", "-m", "Half-baked idea")
    (project / "notes.txt").write_text("todo\n")
    (project / "drafts").mkdir()
    (project / "drafts" / "one.txt").write_text("1\n")
    (project / "drafts" / "two.txt").write_text("2\n")
    return workspace


@pytest.fixture
def run_gck(run_bash, tmp_path, git_env):
    def _run_gck(*args):
        return run_bash("gck", list(args), mock_bins={"glab": GLAB_MOCK},
                        env_extra={**git_env, "CUSTOM_BIN_DIR": str(BIN_DIR), "HOME": str(tmp_path / "home"),
                                   "GLAB_CALLS": str(tmp_path / "glab-calls")})
    return _run_gck


@pytest.fixture
def gck(run_gck):
    def _gck(workspace, *options):
        result = run_gck(*options, str(workspace))
        assert result.returncode == 0, result.stderr
        return TERMINAL_ESCAPES.sub("", result.stdout)
    return _gck


def should_list_each_branch_with_its_ci_state_commits_behind_main_and_failure_category(gck, workspace):
    output = gck(workspace)

    assert re.search(r"✗\s+feature\s+↓2\s+tests$", output, re.MULTILINE)
    assert re.search(r"●\s+remote-only\s+running$", output, re.MULTILINE)


def should_mark_a_branch_that_never_had_a_pipeline_and_keep_it_aligned(gck, workspace, git):
    git(workspace / "project", "branch", "spike", "main")

    output = gck(workspace)

    assert re.search(r"^  💤 spike$", output, re.MULTILINE)
    assert re.search(r"^  ✗  feature\s", output, re.MULTILINE)


def should_show_the_ci_state_of_main_next_to_each_repository(gck, workspace):
    output = gck(workspace)

    assert re.search(r"/project\s+main ✓$", output, re.MULTILINE)


def should_still_show_how_far_behind_main_a_branch_is_without_a_ci_host(gck, workspace, git):
    git(workspace / "project", "remote", "set-url", "origin", str(workspace.parent / "origin.git"))

    output = gck(workspace)

    assert re.search(r"^\s+feature\s+↓2$", output, re.MULTILINE)
    assert "✓" not in output
    assert "💤" not in output


def should_skip_the_ci_lookups_but_still_show_the_branches_in_fast_mode(gck, workspace, tmp_path):
    output = gck(workspace, "--fast")

    assert re.search(r"^\s+feature\s+↓2$", output, re.MULTILINE)
    assert not re.search(r"^ +[✓✗●💤]|main [✓✗●💤]", output, re.MULTILINE)
    assert "api" not in (tmp_path / "glab-calls").read_text()


def should_say_how_each_unpushed_branch_differs_from_origin_without_listing_its_commits(gck, unpushed_workspace):
    output = gck(unpushed_workspace)

    assert re.search(r"^feature  1 ahead of origin$", output, re.MULTILINE)
    assert re.search(r"^rewritten  diverged from origin: 1 ahead, 1 behind$", output, re.MULTILINE)
    assert not re.search(r"^  [0-9a-f]+ - Test, ", output, re.MULTILINE)


def should_group_the_unpushed_commits_by_branch_in_verbose_mode(gck, unpushed_workspace):
    output = gck(unpushed_workspace, "--verbose")

    assert re.search(r"^feature  1 ahead of origin\n  [0-9a-f]+ - Test, .+: Not pushed yet$", output, re.MULTILINE)
    assert re.search(r"^rewritten  diverged from origin: 1 ahead, 1 behind\n  .+: Pushed once, then amended$",
                     output, re.MULTILINE)
    assert re.search(r"^merged  gone from origin\n  .+: Squash merged upstream$", output, re.MULTILINE)
    assert re.search(r"^spike  not on origin  worktree \.claude/worktrees/spike\n  .+: Local experiment$",
                     output, re.MULTILINE)


def should_flag_a_worktree_whose_directory_is_missing_on_this_machine(gck, unpushed_workspace):
    shutil.rmtree(unpushed_workspace / "project" / ".claude" / "worktrees" / "spike")

    output = gck(unpushed_workspace)

    assert re.search(r"^spike  not on origin  worktree \.claude/worktrees/spike \(missing here\)$", output, re.MULTILINE)


def should_count_the_uncommitted_files_and_stashes_instead_of_listing_them(gck, dirty_workspace):
    output = gck(dirty_workspace)

    assert re.search(r"\[git uncommitted changes\]\n3 changed files$", output, re.MULTILINE)
    assert re.search(r"\[git stashed changes\]\n1 stash$", output, re.MULTILINE)
    assert "notes.txt" not in output
    assert "Half-baked idea" not in output


def should_list_the_uncommitted_files_and_stashes_in_verbose_mode(gck, dirty_workspace):
    output = gck(dirty_workspace, "--verbose")

    assert re.search(r"^\?\? notes\.txt$", output, re.MULTILINE)
    assert re.search(r"^stash@\{0\}: On main: Half-baked idea$", output, re.MULTILINE)


def should_describe_the_fast_and_verbose_modes_in_the_help(run_gck):
    result = run_gck("--help")

    assert result.returncode == 0
    assert "-f, --fast" in result.stdout
    assert "-v, --verbose" in result.stdout


def should_reject_an_unknown_option(run_gck):
    result = run_gck("--slow")

    assert result.returncode == 2
    assert "unknown option: --slow" in result.stderr
