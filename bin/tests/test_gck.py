import os
import re
import shutil
import subprocess
import time
import unicodedata
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).parent.parent
TERMINAL_ESCAPES = re.compile(r"\x1b\]8;;[^\x1b]*\x1b\\|\x1b\[[0-9;]*m")
DIM = "\x1b[2m"
GREEN = "\x1b[32m"
RESET = "\x1b[0m"
LOCAL = "💻"
REMOTE_ONLY = "⛅"
HOUR = 3600
DAY = 24 * HOUR
WEEK = 7 * DAY
YEAR = 365 * DAY

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
    def _git(cwd, *args, env=None):
        result = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                                env={**os.environ, **git_env, **(env or {})})
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
def ignore(tmp_path):
    def _ignore(*entries):
        ignore_file = tmp_path / "home" / ".config" / "gck" / "ignore"
        ignore_file.parent.mkdir(parents=True)
        ignore_file.write_text("\n".join(entries) + "\n")
    return _ignore


@pytest.fixture
def now():
    return int(time.time())


@pytest.fixture
def aged_branch(git, now):
    def _aged_branch(project, branch, age):
        git(project, "checkout", "-q", "-b", branch, "main")
        git(project, "commit", "--allow-empty", "-m", f"Work on {branch}",
            env={"GIT_COMMITTER_DATE": f"{now - age} +0000"})
        git(project, "checkout", "-q", "main")
        git(project, "update-ref", f"refs/remotes/origin/{branch}", branch)
    return _aged_branch


@pytest.fixture
def run_gck(run_bash, tmp_path, git_env, now):
    def _run_gck(*args):
        return run_bash("gck", list(args), mock_bins={"glab": GLAB_MOCK, "date": f"echo {now}"},
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

    assert re.search(r"✗\s+feature\s+now\s+↓2\s+tests$", output, re.MULTILINE)
    assert re.search(r"●\s+remote-only\s+now\s+running$", output, re.MULTILINE)


def should_show_a_repository_as_one_block_with_local_and_remote_only_branches_aligned(gck, workspace):
    output = gck(workspace)

    rows = re.match(rf"project  main ✓\n  {LOCAL} (✗  feature.*)\n  {REMOTE_ONLY} (●  remote-only.*)\n", output)
    assert rows, output
    local_row, remote_only_row = rows.groups()
    assert local_row.index("tests") == remote_only_row.index("running")


def should_mark_where_a_branch_lives_with_emoji_every_terminal_draws_two_columns_wide(gck, workspace):
    output = gck(workspace)

    marks = set(re.findall(r"^  (\S+) ", output, re.MULTILINE))
    assert marks == {LOCAL, REMOTE_ONLY}
    assert all(len(mark) == 1 and unicodedata.east_asian_width(mark) == "W" for mark in marks)


def should_mark_a_branch_that_never_had_a_pipeline_and_keep_it_aligned(gck, workspace, git):
    git(workspace / "project", "branch", "spike", "main")

    output = gck(workspace)

    assert re.search(rf"^  {LOCAL} 💤 spike\s+now$", output, re.MULTILINE)
    assert re.search(rf"^  {LOCAL} ✗  feature\s", output, re.MULTILINE)


def should_show_the_ci_state_of_main_next_to_each_repository(gck, workspace):
    output = gck(workspace)

    assert re.search(r"^project  main ✓$", output, re.MULTILINE)


def should_name_a_repository_after_its_directory_when_it_is_the_scanned_directory(gck, workspace):
    output = gck(workspace / "project")

    assert output.startswith("project  main ✓\n")


def should_still_show_how_far_behind_main_a_branch_is_without_a_ci_host(gck, workspace, git):
    git(workspace / "project", "remote", "set-url", "origin", str(workspace.parent / "origin.git"))

    output = gck(workspace)

    assert re.search(rf"^  {LOCAL}\s+feature\s+now\s+↓2$", output, re.MULTILINE)
    assert "✓" not in output
    assert "💤" not in output


def should_skip_the_ci_lookups_but_still_show_the_branches_in_fast_mode(gck, workspace, tmp_path):
    output = gck(workspace, "--fast")

    assert re.search(rf"^  {LOCAL}\s+feature\s+now\s+↓2$", output, re.MULTILINE)
    assert not re.search(rf"^  (?:{LOCAL}|{REMOTE_ONLY}) [✓✗●💤]|main [✓✗●💤]", output, re.MULTILINE)
    assert "api" not in (tmp_path / "glab-calls").read_text()


def should_show_how_long_ago_each_branch_was_last_committed_to(gck, workspace, aged_branch):
    ages = {"minutes": (HOUR - 1, "now"), "hours": (5 * HOUR, "5h"), "days": (WEEK - 1, "6d"),
            "weeks": (WEEK, "1w"), "months": (YEAR - 1, "11mo"), "years": (YEAR, "1y")}
    for branch, (age, _) in ages.items():
        aged_branch(workspace / "project", branch, age)

    output = gck(workspace, "--fast")

    for branch, (_, shown) in ages.items():
        assert re.search(rf"^  {LOCAL}\s+{branch}\s+{shown}$", output, re.MULTILINE), output


def should_color_the_age_green_until_the_branch_is_a_week_old(run_gck, workspace, aged_branch):
    aged_branch(workspace / "project", "recent", WEEK - 1)
    aged_branch(workspace / "project", "cooling", WEEK)

    lines = run_gck("--fast", str(workspace)).stdout.splitlines()

    assert f"{GREEN}6d" in next(line for line in lines if "recent" in line)
    assert GREEN not in next(line for line in lines if "cooling" in line)


def should_mark_how_each_branch_differs_from_origin_without_listing_its_commits(gck, unpushed_workspace):
    output = gck(unpushed_workspace)

    assert re.search(rf"^  {LOCAL} ✗  feature\s+now\s+↓2\s+↑1  tests$", output, re.MULTILINE)
    assert re.search(rf"^  {LOCAL} 💤 rewritten\s+now\s+↑1 diverged$", output, re.MULTILINE)
    assert re.search(rf"^  {LOCAL} 💤 merged\s+now\s+↑1 gone from origin$", output, re.MULTILINE)
    assert re.search(rf"^  {LOCAL} 💤 spike\s+now\s+↑1 not on origin$", output, re.MULTILINE)
    assert " - Test, " not in output


def should_list_the_unpushed_commits_under_their_branch_in_verbose_mode(gck, unpushed_workspace):
    output = gck(unpushed_workspace, "--verbose")

    assert re.search(r"feature\s+now\s+↓2\s+↑1  tests\n {8}[0-9a-f]+ - Test, .+: Not pushed yet$", output, re.MULTILINE)
    assert re.search(r"rewritten\s+now\s+↑1 diverged\n {8}[0-9a-f]+ - Test, .+: Pushed once, then amended$",
                     output, re.MULTILINE)
    assert re.search(r"merged\s+now\s+↑1 gone from origin\n {8}.+: Squash merged upstream$", output, re.MULTILINE)
    assert re.search(r"spike\s+now\s+↑1 not on origin\n {8}.+: Local experiment$", output, re.MULTILINE)


def should_flag_a_worktree_whose_directory_is_missing_on_this_machine(gck, unpushed_workspace):
    shutil.rmtree(unpushed_workspace / "project" / ".claude" / "worktrees" / "spike")

    output = gck(unpushed_workspace)

    assert re.search(r"spike\s+now\s+↑1 not on origin  worktree missing here$", output, re.MULTILINE)


def should_count_the_uncommitted_files_of_a_worktree_on_its_branch(gck, unpushed_workspace):
    (unpushed_workspace / "project" / ".claude" / "worktrees" / "spike" / "draft.txt").write_text("wip\n")

    output = gck(unpushed_workspace)

    assert re.search(r"spike\s+now\s+↑1 not on origin  ✎1$", output, re.MULTILINE)


def should_find_a_worktree_registered_from_the_other_side_of_a_container_mount(gck, unpushed_workspace):
    project = unpushed_workspace / "project"
    (project / ".claude" / "worktrees" / "spike" / "draft.txt").write_text("wip\n")
    registration = next((project / ".git" / "worktrees").glob("*/gitdir"))
    registration.write_text("/elsewhere/project/.claude/worktrees/spike/.git\n")

    output = gck(unpushed_workspace)

    assert re.search(r"spike\s+now\s+↑1 not on origin  ✎1$", output, re.MULTILINE)


def should_count_the_uncommitted_files_and_stashes_instead_of_listing_them(gck, dirty_workspace):
    output = gck(dirty_workspace)

    assert re.search(r"^project  main ✓  ✎3  ✭1$", output, re.MULTILINE)
    assert "notes.txt" not in output
    assert "Half-baked idea" not in output


def should_count_the_uncommitted_files_on_the_branch_the_main_checkout_is_on(gck, dirty_workspace, git):
    git(dirty_workspace / "project", "checkout", "-q", "feature")

    output = gck(dirty_workspace)

    assert re.search(r"^project  main ✓  ✭1$", output, re.MULTILINE)
    assert re.search(rf"^  {LOCAL} ✗  feature\s+now\s+↓2\s+✎3  tests$", output, re.MULTILINE)


def should_list_the_uncommitted_files_and_stashes_under_the_repository_in_verbose_mode(gck, dirty_workspace):
    output = gck(dirty_workspace, "--verbose")

    assert re.search(r"^project  main ✓  ✎3  ✭1\n {8}\?\? drafts/one\.txt$", output, re.MULTILINE)
    assert re.search(r"^ {8}\?\? notes\.txt$", output, re.MULTILINE)
    assert re.search(r"^ {8}stash@\{0\}: On main: Half-baked idea$", output, re.MULTILINE)


def should_list_the_repositories_that_need_action_first_and_set_the_others_apart(gck, workspace, git, tmp_path):
    busy = workspace / "busy"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(busy))
    (busy / "notes.txt").write_text("todo\n")

    output = gck(workspace)

    assert re.match(r"busy  main  ✎1\n(?:  .+\n)+\nproject  main ✓\n", output), output


def is_dimmed_throughout(line):
    return line.startswith(DIM) and all(part.startswith(DIM) for part in line.split(RESET)[1:-1])


def should_dim_the_branches_that_need_no_action(run_gck, unpushed_workspace):
    lines = run_gck(str(unpushed_workspace)).stdout.splitlines()

    assert not lines[0].startswith(DIM)
    assert not next(line for line in lines if "feature" in line).startswith(DIM)
    assert is_dimmed_throughout(next(line for line in lines if "remote-only" in line))


def should_dim_a_repository_that_needs_no_action(run_gck, workspace):
    lines = run_gck(str(workspace)).stdout.splitlines()

    assert all(is_dimmed_throughout(line) for line in lines[:3])


def should_leave_out_an_ignored_repository_without_work_to_save_or_looking_up_its_ci(gck, workspace, ignore, tmp_path):
    ignore("project")

    output = gck(workspace)

    assert "project" not in output
    assert not (tmp_path / "glab-calls").exists()


def should_show_only_the_work_to_save_of_an_ignored_repository(gck, unpushed_workspace, ignore):
    ignore("project")

    output = gck(unpushed_workspace)

    assert re.search(rf"^  {LOCAL}\s+spike\s+now\s+↑1 not on origin$", output, re.MULTILINE)
    assert re.search(rf"^  {LOCAL}\s+feature\s+now\s+↓2\s+↑1$", output, re.MULTILINE)
    assert "remote-only" not in output


def should_read_each_ignore_line_as_a_glob_for_the_end_of_the_repository_path(gck, workspace, ignore):
    ignore("# bots only", "", "  workspace/proj*  ")

    output = gck(workspace)

    assert "project" not in output


def should_keep_a_repository_whose_path_only_starts_like_an_ignore_entry(gck, workspace, ignore):
    ignore("proj")

    output = gck(workspace)

    assert output.startswith("project  main ✓\n")


def should_describe_the_fast_and_verbose_modes_in_the_help(run_gck):
    result = run_gck("--help")

    assert result.returncode == 0
    assert "-f, --fast" in result.stdout
    assert "-v, --verbose" in result.stdout


def should_reject_an_unknown_option(run_gck):
    result = run_gck("--slow")

    assert result.returncode == 2
    assert "unknown option: --slow" in result.stderr
