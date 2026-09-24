import re
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).parent.parent
TERMINAL_ESCAPES = re.compile(r"\x1b\]8;;[^\x1b]*\x1b\\|\x1b\[[0-9;]*[A-Za-z]")
CURL_MOCK = 'case "$*" in *unreachable*) exit 7 ;; esac'
UNREACHABLE_REMOTE = "git@unreachable.example.com:group/offline.git"


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
def gupallin(run_bash, git_env):
    def _gupallin(directory):
        result = run_bash("gupallin", [str(directory)], mock_bins={"curl": CURL_MOCK},
                          env_extra={**git_env, "CUSTOM_BIN_DIR": str(BIN_DIR)})
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
