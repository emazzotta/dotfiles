import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bin.tests.conftest import commit_file

BIN_DIR = Path(__file__).parent.parent
TERMINAL_ESCAPES = re.compile(r"\x1b\]8;;[^\x1b]*\x1b\\|\x1b\[[0-9;]*[A-Za-z]")
CURL_MOCK = 'case "$*" in *unreachable*) exit 7 ;; esac'
UNREACHABLE_REMOTE = "git@unreachable.example.com:group/offline.git"
SLOW_CURL_MOCK = f"sleep 1.6\n{CURL_MOCK}"
UTF8_LOCALE = {"LC_ALL": "en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8"}
GIT_SPY = r'''
printf '%s\n' "$*" >> "${GIT_CALLS}"
if [ "${3:-}" = pull ]; then
    printf '%s on %s\n' "$5" "$("${REAL_GIT}" -C "$2" symbolic-ref -q --short HEAD)" >> "${PULL_MODES}"
fi
exec "${REAL_GIT}" "$@"
'''
SPINNER_GLYPHS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
# subprocess text mode turns each \r the spinner prints into \n
SPINNER_FRAME = re.compile(r"\x1b\[2K\n  \x1b\[33m(\S)\x1b\[0m  ([^\x1b\n]*)")
SPINNER_CLEAR = "\n" + " " * 100 + "\n"


def plain(text):
    return TERMINAL_ESCAPES.sub("", text)


@pytest.fixture
def origin(tmp_path, git):
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", str(origin))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", str(origin), str(seed))
    git(seed, "commit", "--allow-empty", "-m", "Start")
    git(seed, "push", "origin", "main", "main:25.4.x", "main:feature")
    return origin


@pytest.fixture
def workspace(tmp_path):
    return tmp_path / "workspace"


@pytest.fixture
def clone(git, origin, workspace):
    def _clone(path, remote=None):
        repo = workspace / path
        git(workspace.parent, "clone", str(origin), str(repo))
        if remote:
            git(repo, "remote", "set-url", "origin", remote)
        return repo
    return _clone


@pytest.fixture
def broken_clone(clone, tmp_path):
    def _broken_clone(path):
        return clone(path, remote=str(tmp_path / "gone.git"))
    return _broken_clone


@pytest.fixture
def gupallin(run_bash, git_env, tmp_path):
    def _gupallin(directory):
        result = run_bash("gupallin", [str(directory)], mock_bins={"curl": CURL_MOCK},
                          env_extra={**git_env, "CUSTOM_BIN_DIR": str(BIN_DIR), "HOME": str(tmp_path / "home")})
        assert result.returncode == 0, result.stderr
        return result
    return _gupallin


def should_pull_the_default_and_release_branches_and_return_to_the_checked_out_branch(gupallin, clone, workspace,
                                                                                         origin, git, tmp_path):
    project = clone("project")
    git(project, "checkout", "-q", "feature")
    git(tmp_path / "seed", "commit", "--allow-empty", "-m", "Advance")
    git(tmp_path / "seed", "push", "origin", "main", "main:25.4.x")

    gupallin(workspace)

    assert git(project, "rev-parse", "main", "25.4.x") == git(origin, "rev-parse", "main", "25.4.x")
    assert git(project, "rev-parse", "--abbrev-ref", "HEAD") == "feature"


def should_skip_only_the_repositories_listed_under_gupallin_in_the_ignore_list(gupallin, clone, workspace, origin,
                                                                               git, tmp_path, repo_ignore):
    project = clone("project")
    archive = clone("private/archive")
    stale = git(archive, "rev-parse", "main")
    git(tmp_path / "seed", "commit", "--allow-empty", "-m", "Advance")
    git(tmp_path / "seed", "push", "origin", "main")
    repo_ignore("[gck]", "project", "[gupallin]", "private/archive")

    gupallin(workspace)

    assert git(project, "rev-parse", "main") == git(origin, "rev-parse", "main")
    assert git(archive, "rev-parse", "main") == stale


def should_not_enter_a_directory_listed_under_prune_in_the_ignore_list(gupallin, clone, workspace, origin, git,
                                                                       tmp_path, repo_ignore, locked_dir):
    project = clone("project")
    git(tmp_path / "seed", "commit", "--allow-empty", "-m", "Advance")
    git(tmp_path / "seed", "push", "origin", "main")
    locked_dir(workspace / "Library")
    repo_ignore("[prune]", "Library")

    result = gupallin(workspace)

    assert "Permission denied" not in result.stderr
    assert git(project, "rev-parse", "main") == git(origin, "rev-parse", "main")


def should_keep_an_unpushed_merge_of_main_on_the_checked_out_branch(gupallin, clone, workspace, git, tmp_path):
    project = clone("project")
    git(project, "checkout", "-q", "feature")
    commit_file(git, tmp_path / "seed", "main.txt", "main\n", "Main moves")
    git(tmp_path / "seed", "push", "origin", "main")
    git(project, "fetch", "-q", "origin")
    git(project, "merge", "--no-ff", "origin/main", "-m", "Merge main into feature")
    merge = git(project, "rev-parse", "HEAD")

    gupallin(workspace)

    assert git(project, "rev-parse", "HEAD") == merge


def should_pull_only_branches_named_like_a_release_version(gupallin, clone, workspace, git, tmp_path):
    git(tmp_path / "seed", "push", "origin", "main:535", "main:1a2")
    project = clone("project")

    gupallin(workspace)

    assert git(project, "for-each-ref", "--format=%(refname:short)", "refs/heads/").splitlines() == ["25.4.x", "main"]


def should_leave_a_repository_without_commits_alone(gupallin, workspace, git, tmp_path):
    empty_origin = tmp_path / "empty.git"
    git(tmp_path, "init", "--bare", str(empty_origin))
    git(tmp_path, "clone", "-q", str(empty_origin), str(workspace / "fresh"))

    result = gupallin(workspace)

    assert plain(result.stdout) == "\n● Done.\n"
    assert "fatal" not in result.stderr


def should_only_report_done_when_every_pull_succeeds(gupallin, clone, workspace):
    clone("project")

    result = gupallin(workspace)

    assert plain(result.stdout) == "\n● Done.\n"
    assert "No remote access" not in plain(result.stderr)


def should_list_each_branch_whose_pull_failed_as_an_aligned_row_under_its_repository(gupallin, broken_clone,
                                                                                     workspace, git):
    project = broken_clone("project")
    git(project, "checkout", "-q", "feature")

    output = plain(gupallin(workspace).stdout)

    assert output.startswith("project\n"
                             "  main     pull failed\n"
                             "  25.4.x   pull failed\n"
                             "  feature  pull failed\n"), output


def should_list_the_checked_out_branch_once_when_it_is_also_a_release_branch(gupallin, broken_clone, workspace, git):
    project = broken_clone("project")
    git(project, "checkout", "-q", "25.4.x")

    output = plain(gupallin(workspace).stdout)

    assert output.count("25.4.x") == 1, output


def should_name_a_repository_by_its_path_below_the_scanned_directory(gupallin, broken_clone, workspace):
    broken_clone("group/project")

    output = plain(gupallin(workspace).stdout)

    assert output.startswith("group/project\n"), output


def should_name_a_repository_after_its_directory_when_it_is_the_scanned_directory(gupallin, broken_clone):
    project = broken_clone("project")

    output = plain(gupallin(project).stdout)

    assert output.startswith("project\n"), output


def should_link_the_repository_name_to_its_directory(gupallin, broken_clone, workspace):
    project = broken_clone("project")

    output = gupallin(workspace).stdout

    assert f"\x1b]8;;file://{project.resolve()}\x1b\\" in output


def should_warn_about_repositories_without_remote_access_after_the_failed_pulls(gupallin, clone, broken_clone,
                                                                                workspace):
    broken_clone("project")
    clone("offline", remote=UNREACHABLE_REMOTE)

    result = gupallin(workspace)

    assert "offline" not in plain(result.stdout)
    assert plain(result.stderr).endswith("● No remote access:\n  · offline\n")


def rebase_in_progress(git, repo):
    git_dir = Path(git(repo, "rev-parse", "--absolute-git-dir"))
    return (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()


def should_abort_a_conflicting_pull_of_another_branch_and_return_to_the_checked_out_branch(
        gupallin, clone, workspace, git, tmp_path):
    project = clone("project")
    git(project, "checkout", "-q", "main")
    commit_file(git, project, "conflict.txt", "local\n", "Local main")
    git(project, "checkout", "-q", "feature")
    commit_file(git, tmp_path / "seed", "conflict.txt", "remote\n", "Remote main")
    git(tmp_path / "seed", "push", "origin", "main")

    output = plain(gupallin(workspace).stdout)

    assert git(project, "rev-parse", "--abbrev-ref", "HEAD") == "feature"
    assert not rebase_in_progress(git, project)
    assert "main" in output and "pull failed" in output


def should_abort_a_conflicting_pull_of_the_checked_out_branch(gupallin, clone, workspace, git, tmp_path):
    project = clone("project")
    git(project, "checkout", "-q", "feature")
    commit_file(git, project, "conflict.txt", "local\n", "Local feature")
    commit_file(git, tmp_path / "seed", "conflict.txt", "remote\n", "Remote feature")
    git(tmp_path / "seed", "push", "origin", "main:feature", "--force")

    output = plain(gupallin(workspace).stdout)

    assert git(project, "rev-parse", "--abbrev-ref", "HEAD") == "feature"
    assert not rebase_in_progress(git, project)
    assert "feature" in output and "pull failed" in output


def should_not_abort_a_rebase_the_user_has_in_progress(gupallin, clone, workspace, git, git_env, tmp_path):
    project = clone("project")
    git(project, "checkout", "-q", "-b", "topic")
    commit_file(git, project, "conflict.txt", "topic\n", "Topic")
    git(project, "checkout", "-q", "main")
    commit_file(git, project, "conflict.txt", "local\n", "Local main")
    git(project, "checkout", "-q", "topic")
    subprocess.run(["git", "-C", str(project), "rebase", "main"], capture_output=True, env={**os.environ, **git_env})
    (project / "conflict.txt").write_text("resolved\n")
    git(project, "add", "conflict.txt")
    commit_file(git, tmp_path / "seed", "other.txt", "remote\n", "Remote main")
    git(tmp_path / "seed", "push", "origin", "main")

    gupallin(workspace)

    assert rebase_in_progress(git, project)


def link(path, label):
    return f"\x1b]8;;file://{Path(path).resolve()}\x1b\\\x1b[33m{label}\x1b[0m\x1b]8;;\x1b\\"


def after_spinner(stderr):
    return stderr.partition(SPINNER_CLEAR)[2]


def repository_blocks(stdout):
    listing = plain(stdout).split("● Done.")[0].rstrip("\n")
    return sorted(block.rstrip("\n") + "\n" for block in re.split(r"(?m)^(?=\S)", listing) if block)


@pytest.fixture
def run_gupallin(run_bash, git_env, tmp_path):
    def _run(directory, curl=CURL_MOCK, spy_git=False, extra_env=None):
        mock_bins = {"curl": curl}
        env = {**git_env, "CUSTOM_BIN_DIR": str(BIN_DIR), "HOME": str(tmp_path / "home"), **(extra_env or {})}
        if spy_git:
            mock_bins["git"] = GIT_SPY
            env.update(GIT_CALLS=str(tmp_path / "git-calls"), PULL_MODES=str(tmp_path / "pull-modes"),
                       REAL_GIT=shutil.which("git"))
        result = run_bash("gupallin", [str(directory)], mock_bins=mock_bins, env_extra=env)
        assert result.returncode == 0, result.stderr
        return result
    return _run


@pytest.fixture
def pull_modes(tmp_path):
    return lambda: (tmp_path / "pull-modes").read_text().splitlines()


def should_pull_the_default_branches_without_keeping_merges_and_every_other_branch_keeping_them(
        run_gupallin, clone, workspace, git, tmp_path, pull_modes):
    git(tmp_path / "seed", "push", "origin", "main:master")
    project = clone("project")
    git(project, "checkout", "-q", "feature")

    run_gupallin(workspace, spy_git=True)

    assert pull_modes() == ["--rebase=true on main", "--rebase=true on master", "--rebase=merges on 25.4.x",
                            "--rebase=merges on feature"]


def should_keep_merges_when_the_checked_out_branch_only_starts_like_a_default_branch(
        run_gupallin, clone, workspace, git, pull_modes):
    project = clone("project")
    git(project, "checkout", "-q", "-b", "mainline")

    run_gupallin(workspace, spy_git=True)

    assert pull_modes()[-1] == "--rebase=merges on mainline"


def should_not_pull_the_checked_out_default_branch_a_second_time(run_gupallin, clone, workspace, pull_modes):
    clone("project")

    run_gupallin(workspace, spy_git=True)

    assert pull_modes() == ["--rebase=true on main", "--rebase=merges on 25.4.x"]


def should_pad_the_failed_pull_rows_of_each_repository_to_its_longest_branch_name(
        run_gupallin, broken_clone, workspace, git):
    git(broken_clone("project"), "checkout", "-q", "-b", "a-much-longer-branch")
    broken_clone("group/deep")

    stdout = run_gupallin(workspace).stdout

    assert plain(stdout).endswith("\n● Done.\n")
    assert repository_blocks(stdout) == [
        "group/deep\n  main    pull failed\n  25.4.x  pull failed\n",
        "project\n  main                  pull failed\n  25.4.x                pull failed\n"
        "  a-much-longer-branch  pull failed\n"]


def should_not_pad_the_only_row_of_a_repository_beyond_its_branch_name(run_gupallin, workspace, git, tmp_path):
    server = tmp_path / "short.git"
    git(tmp_path, "init", "--bare", str(server))
    short = workspace / "short"
    git(tmp_path, "clone", "-q", str(server), str(short))
    git(short, "commit", "--allow-empty", "-m", "Start")
    git(short, "branch", "-m", "x")
    git(short, "remote", "set-url", "origin", str(tmp_path / "gone.git"))

    stdout = run_gupallin(workspace).stdout

    assert repository_blocks(stdout) == ["short\n  x  pull failed\n"]


def should_colour_each_failed_pull_in_bold_red_and_link_the_repository_name_in_yellow(
        run_gupallin, broken_clone, workspace):
    project = broken_clone("project")

    stdout = run_gupallin(workspace).stdout

    assert stdout == (f"{link(project, 'project')}\n"
                      "  main    \x1b[1m\x1b[31mpull failed\x1b[0m\n"
                      "  25.4.x  \x1b[1m\x1b[31mpull failed\x1b[0m\n"
                      "\n\x1b[1m\x1b[32m●\x1b[0m Done.\n")


@pytest.mark.parametrize("suffix", ["", "/"])
def should_name_a_nested_repository_by_its_path_whether_or_not_the_scanned_directory_ends_in_a_slash(
        run_gupallin, broken_clone, workspace, suffix):
    broken_clone("group/deep")

    stdout = run_gupallin(f"{workspace}{suffix}").stdout

    assert repository_blocks(stdout) == ["group/deep\n  main    pull failed\n  25.4.x  pull failed\n"]
    assert link(workspace / "group" / "deep", "group/deep") in stdout


def should_name_the_scanned_repository_after_its_directory_even_when_the_path_ends_in_a_slash(
        run_gupallin, broken_clone):
    project = broken_clone("project")

    stdout = run_gupallin(f"{project}/").stdout

    assert stdout.startswith(f"{link(project, 'project')}\n")


def should_list_the_repositories_without_remote_access_as_linked_substeps_on_stderr(
        run_gupallin, clone, workspace):
    clone("offline", remote=UNREACHABLE_REMOTE)
    clone("group/second", remote=UNREACHABLE_REMOTE)

    result = run_gupallin(workspace)

    heading, *rows = after_spinner(result.stderr).splitlines(keepends=True)
    assert heading == "\x1b[1m\x1b[31m●\x1b[0m No remote access:\n"
    assert sorted(rows) == sorted(f"  \x1b[1m\x1b[31m·\x1b[0m {link(workspace / path, path)}\n"
                                  for path in ("offline", "group/second"))
    assert plain(result.stdout) == "\n\n● Done.\n"


def should_print_no_warning_block_and_no_extra_blank_line_when_every_repository_is_reachable(
        run_gupallin, clone, workspace):
    clone("project")

    result = run_gupallin(workspace)

    assert after_spinner(result.stderr) == ""
    assert plain(result.stdout) == "\n● Done.\n"


def should_draw_a_spinner_frame_every_tenth_of_a_second_with_the_repository_being_updated(
        run_gupallin, clone, workspace):
    project = clone("project")

    result = run_gupallin(workspace, curl=SLOW_CURL_MOCK, extra_env=UTF8_LOCALE)

    frames = SPINNER_FRAME.findall(result.stderr)
    assert len(frames) > len(SPINNER_GLYPHS)
    assert [glyph for glyph, _ in frames] == [SPINNER_GLYPHS[i % 10] for i in range(len(frames))]
    assert frames[-1][1] == str(project)
    assert result.stderr.rindex(SPINNER_CLEAR) > result.stderr.rindex(frames[-1][1])
    assert "\x1b[2K" not in result.stdout
