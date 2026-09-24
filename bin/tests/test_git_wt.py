import os
import shutil
import subprocess
from pathlib import Path

import pytest

WORKTREES = Path(".claude") / "worktrees"


@pytest.fixture
def gitconfig(tmp_path):
    config = tmp_path / "gitconfig"
    config.write_text("[user]\n\tname = Test\n\temail = test@example.com\n"
                      "[init]\n\tdefaultBranch = main\n"
                      "[safe]\n\tdirectory = *\n")
    return config


@pytest.fixture
def git_env(gitconfig):
    return {"GIT_CONFIG_GLOBAL": str(gitconfig), "GIT_CONFIG_NOSYSTEM": "1"}


@pytest.fixture
def git(git_env):
    def _git(cwd, *args):
        result = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                                env={**os.environ, **git_env})
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()
    return _git


@pytest.fixture
def project(tmp_path, git):
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", str(origin))
    project = tmp_path / "project"
    git(tmp_path, "clone", str(origin), str(project))
    git(project, "commit", "--allow-empty", "-m", "Initial commit")
    git(project, "push", "origin", "main")
    git(project, "remote", "set-head", "origin", "main")
    return project


@pytest.fixture
def wt(run_cli, git_env, project):
    def _wt(*args, cwd=None):
        return run_cli("git-wt", list(args), env_extra=git_env, cwd=cwd or project)
    return _wt


@pytest.fixture
def added(wt):
    def _added(branch, *start):
        result = wt("add", branch, *start)
        assert result.returncode == 0, result.stderr
        return Path(result.stdout.strip())
    return _added


def branches(git, repo):
    return git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split("\n")


def registered_paths(git, repo):
    porcelain = git(repo, "worktree", "list", "--porcelain")
    return [line[len("worktree "):] for line in porcelain.split("\n") if line.startswith("worktree ")]


def commit_file(git, checkout, name, content, message="Add file"):
    (checkout / name).write_text(content)
    git(checkout, "add", name)
    git(checkout, "commit", "-m", message)


def finish_upstream(git, project, worktree, branch):
    git(worktree, "commit", "--allow-empty", "-m", "Work")
    git(worktree, "push", "-u", "origin", branch)
    git(project, "push", "origin", "--delete", branch)
    git(project, "fetch", "--prune", "origin")


def move_to_other_mount(project, tmp_path):
    other_side = tmp_path / "other-mount"
    shutil.move(str(project), str(other_side))
    return other_side


class TestAdd:
    def should_create_a_branch_off_origin_head_inside_claude_worktrees(self, wt, git, project):
        result = wt("add", "feature")

        path = project / WORKTREES / "feature"
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(path)
        assert git(path, "rev-parse", "--abbrev-ref", "HEAD") == "feature"
        assert git(path, "rev-parse", "HEAD") == git(project, "rev-parse", "origin/main")

    def should_leave_a_new_branch_without_upstream_until_it_is_pushed(self, added, git, project):
        added("feature")

        assert git(project, "for-each-ref", "--format=%(upstream)", "refs/heads/feature") == ""

    def should_start_a_new_branch_from_the_given_start_point(self, added, git, project):
        git(project, "commit", "--allow-empty", "-m", "Local only")

        path = added("feature", "main")

        assert git(path, "rev-parse", "HEAD") == git(project, "rev-parse", "main")

    def should_check_out_an_existing_local_branch(self, added, git, project):
        git(project, "branch", "existing")
        git(project, "commit", "--allow-empty", "-m", "Main moves on")

        path = added("existing")

        assert git(path, "rev-parse", "HEAD") == git(project, "rev-parse", "existing")

    def should_track_a_branch_that_only_exists_on_origin(self, added, git, project):
        git(project, "push", "origin", "main:refs/heads/remote-only")
        git(project, "fetch", "origin")

        added("remote-only")

        upstream = git(project, "for-each-ref", "--format=%(upstream:short)", "refs/heads/remote-only")
        assert upstream == "origin/remote-only"

    def should_keep_worktrees_out_of_the_main_checkout_status(self, added, git, project):
        added("feature")
        added("second")

        exclude = (project / ".git" / "info" / "exclude").read_text().split("\n")
        assert git(project, "status", "--porcelain") == ""
        assert exclude.count("/.claude/worktrees/") == 1

    def should_trust_the_worktree_when_the_main_checkout_is_trusted_by_path(
            self, added, git, gitconfig, project):
        git(project, "config", "--global", "--add", "safe.directory", str(project))

        path = added("feature")

        assert str(path) in git(project, "config", "--global", "--get-all", "safe.directory").split("\n")

    def should_leave_trust_alone_when_the_main_checkout_is_not_trusted_by_path(
            self, added, git, project):
        added("feature")

        assert git(project, "config", "--global", "--get-all", "safe.directory") == "*"

    @pytest.mark.parametrize("branch", ["feature", "renovate/junit"])
    def should_keep_the_worktree_usable_from_another_mount_path(
            self, added, git, tmp_path, project, branch):
        added(branch)
        other_side = move_to_other_mount(project, tmp_path)

        head = git(other_side / WORKTREES / branch, "rev-parse", "--abbrev-ref", "HEAD")

        assert head == branch

    def should_exit_with_usage_when_the_branch_is_missing(self, wt):
        result = wt("add")

        assert result.returncode == 2
        assert "Usage" in result.stderr


class TestRm:
    def should_remove_the_worktree_and_delete_the_branch(self, wt, added, git, project):
        path = added("feature")

        result = wt("rm", "feature")

        assert result.returncode == 0, result.stderr
        assert not path.exists()
        assert "feature" not in branches(git, project)

    def should_keep_a_worktree_with_uncommitted_changes_and_its_branch(self, wt, added, git, project):
        path = added("feature")
        (path / "draft.txt").write_text("work in progress")

        result = wt("rm", "feature")

        assert result.returncode == 1
        assert (path / "draft.txt").exists()
        assert "feature" in branches(git, project)

    def should_drop_the_registration_of_a_worktree_this_machine_cannot_see(
            self, wt, git, tmp_path, project):
        scratchpad = tmp_path / "scratchpad" / "feature"
        git(project, "worktree", "add", "-b", "feature", str(scratchpad))
        shutil.move(str(scratchpad), str(tmp_path / "other-machine"))

        result = wt("rm", "feature")

        assert result.returncode == 0, result.stderr
        assert str(scratchpad) not in registered_paths(git, project)
        assert "feature" not in branches(git, project)

    def should_remove_a_worktree_registered_under_another_mount_path(
            self, wt, added, git, tmp_path, project):
        added("feature")
        other_side = move_to_other_mount(project, tmp_path)

        result = wt("rm", "feature", cwd=other_side)

        assert result.returncode == 0, result.stderr
        assert not (other_side / WORKTREES / "feature").exists()
        assert registered_paths(git, other_side) == [str(other_side)]
        assert "feature" not in branches(git, other_side)

    def should_keep_a_dirty_worktree_registered_under_another_mount_path(
            self, wt, added, git, tmp_path, project):
        path = added("feature")
        (path / "draft.txt").write_text("work in progress")
        other_side = move_to_other_mount(project, tmp_path)

        result = wt("rm", "feature", cwd=other_side)

        twin = other_side / WORKTREES / "feature"
        assert result.returncode == 1
        assert (twin / "draft.txt").exists()
        assert str(project / WORKTREES / "feature") in registered_paths(git, other_side)
        assert "feature" in branches(git, other_side)

    def should_delete_a_branch_that_no_worktree_holds(self, wt, git, project):
        git(project, "branch", "plain")

        result = wt("rm", "plain")

        assert result.returncode == 0, result.stderr
        assert "plain" not in branches(git, project)


class TestSweep:
    def should_remove_a_clean_worktree_whose_upstream_is_gone_and_keep_its_branch(
            self, wt, added, git, project):
        path = added("feature")
        finish_upstream(git, project, path, "feature")

        result = wt("sweep")

        assert result.returncode == 0, result.stderr
        assert f"removed {path} (upstream gone)" in result.stdout
        assert not path.exists()
        assert "feature" in branches(git, project)

    def should_only_list_on_a_dry_run(self, wt, added, git, project):
        path = added("feature")
        finish_upstream(git, project, path, "feature")

        result = wt("sweep", "-n")

        assert f"would remove {path} (upstream gone)" in result.stdout
        assert path.exists()

    def should_keep_a_worktree_with_uncommitted_changes_when_its_upstream_is_gone(
            self, wt, added, git, project):
        path = added("feature")
        finish_upstream(git, project, path, "feature")
        (path / "draft.txt").write_text("work in progress")

        result = wt("sweep")

        assert result.stdout == ""
        assert (path / "draft.txt").exists()

    def should_remove_a_clean_worktree_whose_branch_was_squash_merged(self, wt, added, git, project):
        path = added("feature")
        commit_file(git, path, "feature.txt", "done")
        commit_file(git, project, "feature.txt", "done", "Squash-merge feature")
        git(project, "push", "origin", "main")

        result = wt("sweep")

        assert f"removed {path} (merged)" in result.stdout
        assert "feature" in branches(git, project)

    def should_keep_a_worktree_whose_branch_was_never_pushed(self, wt, added, git, project):
        path = added("feature")
        commit_file(git, path, "feature.txt", "local work")

        result = wt("sweep")

        assert result.stdout == ""
        assert path.exists()

    def should_keep_a_new_worktree_that_has_no_commits_yet(self, wt, added):
        path = added("feature")

        result = wt("sweep")

        assert result.stdout == ""
        assert path.exists()

    def should_drop_the_registration_when_the_worktree_directory_was_deleted(
            self, wt, added, git, project):
        path = added("feature")
        shutil.rmtree(path)

        result = wt("sweep")

        assert f"removed {path} (directory gone)" in result.stdout
        assert registered_paths(git, project) == [str(project)]
        assert "feature" in branches(git, project)

    def should_keep_a_missing_registration_outside_claude_worktrees(
            self, wt, git, tmp_path, project):
        scratchpad = tmp_path / "scratchpad" / "feature"
        git(project, "worktree", "add", "-b", "feature", str(scratchpad))
        shutil.move(str(scratchpad), str(tmp_path / "other-machine"))

        result = wt("sweep")

        assert result.stdout == ""
        assert str(scratchpad) in registered_paths(git, project)

    def should_remove_a_finished_worktree_registered_under_another_mount_path(
            self, wt, added, git, tmp_path, project):
        path = added("feature")
        finish_upstream(git, project, path, "feature")
        other_side = move_to_other_mount(project, tmp_path)

        result = wt("sweep", cwd=other_side)

        assert result.returncode == 0, result.stderr
        assert not (other_side / WORKTREES / "feature").exists()
        assert registered_paths(git, other_side) == [str(other_side)]


class TestComplete:
    def should_offer_the_commands_when_none_is_typed_yet(self, wt):
        result = wt("--complete")

        assert result.stdout.split() == ["add", "rm", "sweep"]

    def should_offer_every_local_branch_to_each_rm_argument(self, wt, git, project):
        git(project, "branch", "plain")
        git(project, "push", "origin", "main:refs/heads/remote-only")
        git(project, "fetch", "origin")

        result = wt("--complete", "rm", "plain")

        assert result.stdout.split() == ["main", "plain"]

    def should_offer_local_and_origin_branches_once_each_to_add(self, wt, git, project):
        git(project, "branch", "local-only")
        git(project, "push", "origin", "main:refs/heads/remote-only")
        git(project, "fetch", "origin")

        result = wt("--complete", "add")

        assert result.stdout.split() == ["local-only", "main", "remote-only"]

    def should_offer_nothing_once_add_has_its_branch(self, wt):
        result = wt("--complete", "add", "feature")

        assert result.returncode == 0, result.stderr
        assert result.stdout == ""

    def should_offer_the_dry_run_flag_to_sweep(self, wt):
        result = wt("--complete", "sweep")

        assert result.stdout.split() == ["-n"]
