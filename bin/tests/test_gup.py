import re

import pytest

from bin.tests.conftest import WORKTREES, branches, commit_file, move_to_other_mount, ship_by_squash_merge

GIT_STAND_IN = r'''
printf '%s\n' "$*" >> "${GIT_CALLS}"
case "$*" in
    *"rev-parse --is-inside-git-dir") echo "${STAND_IN_INSIDE_GIT_DIR}" ;;
    "rev-parse --absolute-git-dir") echo /stand-in/worktree-git-dir ;;
    "rev-parse --path-format=absolute --git-common-dir") echo /stand-in/common-git-dir ;;
    "symbolic-ref -q HEAD") echo "refs/heads/${STAND_IN_BRANCH}" ;;
    "wt path "*) echo /stand-in/checkout ;;
    *"symbolic-ref -q --short HEAD") [ -n "${STAND_IN_BRANCH}" ] && echo "${STAND_IN_BRANCH}" ;;
    *" pull "*) exit "${STAND_IN_PULL_STATUS}" ;;
esac
'''


@pytest.fixture
def gup(run_cli, git_env):
    def _gup(cwd, *args):
        return run_cli("gup", list(args), env_extra=git_env, cwd=cwd)
    return _gup


@pytest.fixture
def checkout(git, project, added):
    (project / "notes.txt").write_text("draft\n")
    git(project, "add", "notes.txt")
    git(project, "commit", "-m", "Add notes")
    git(project, "push", "origin", "main", "main:feature")
    git(project, "fetch", "origin")
    return added("feature")


def push_from_elsewhere(git, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    git(tmp_path, "clone", "--branch", "feature", str(tmp_path / "origin.git"), str(elsewhere))
    git(elsewhere, "commit", "--allow-empty", "-m", "Pushed from elsewhere")
    git(elsewhere, "push", "origin", "feature")
    return git(elsewhere, "rev-parse", "HEAD")


def merge_new_main(git, project, checkout):
    commit_file(git, project, "main.txt", "main\n", "Main moves")
    git(project, "push", "origin", "main")
    git(checkout, "merge", "--no-ff", "origin/main", "-m", "Merge main into feature")
    return git(checkout, "rev-parse", "HEAD")


class TestPull:
    def should_rebase_local_commits_onto_the_upstream_and_keep_uncommitted_changes(
            self, gup, git, tmp_path, checkout):
        (checkout / "local.txt").write_text("local\n")
        git(checkout, "add", "local.txt")
        git(checkout, "commit", "-m", "Local work")
        (checkout / "notes.txt").write_text("edited\n")
        pushed = push_from_elsewhere(git, tmp_path)

        result = gup(checkout)

        assert result.returncode == 0, result.stderr
        assert git(checkout, "rev-parse", "HEAD~1") == pushed
        assert (checkout / "notes.txt").read_text() == "edited\n"

    def should_update_the_checkout_when_run_inside_its_worktree_git_dir(
            self, gup, git, tmp_path, project, checkout):
        pushed = push_from_elsewhere(git, tmp_path)

        result = gup(project / ".git" / "worktrees" / "feature")

        assert result.returncode == 0, result.stderr
        assert git(checkout, "rev-parse", "HEAD") == pushed

    def should_update_the_local_checkout_from_its_worktree_git_dir_on_another_mount(
            self, gup, git, tmp_path, project, checkout):
        pushed = push_from_elsewhere(git, tmp_path)
        other_side = move_to_other_mount(project, tmp_path)
        twin = other_side / WORKTREES / "feature"

        result = gup(other_side / ".git" / "worktrees" / "feature")

        assert result.returncode == 0, result.stderr
        assert f"gup: updating {twin}" in result.stderr
        assert git(twin, "rev-parse", "HEAD") == pushed

    def should_keep_an_unpushed_merge_of_main_while_the_upstream_stands_still(
            self, gup, git, project, checkout):
        merge = merge_new_main(git, project, checkout)

        result = gup(checkout)

        assert result.returncode == 0, result.stderr
        assert git(checkout, "rev-parse", "HEAD") == merge

    def should_replay_an_unpushed_merge_of_main_as_a_merge_onto_the_moved_upstream(
            self, gup, git, tmp_path, project, checkout):
        merge_new_main(git, project, checkout)
        pushed = push_from_elsewhere(git, tmp_path)

        result = gup(checkout)

        assert result.returncode == 0, result.stderr
        assert git(checkout, "rev-parse", "HEAD^1") == pushed
        assert git(checkout, "show", "HEAD^2:main.txt") == "main"

    def should_flatten_a_local_merge_on_main_so_main_stays_a_straight_line(self, gup, git, project, added):
        side = added("side")
        commit_file(git, side, "side.txt", "side\n", "Side work")
        git(project, "merge", "--no-ff", "side", "-m", "Merge side into main")

        result = gup(project)

        assert result.returncode == 0, result.stderr
        assert git(project, "rev-list", "--merges", "origin/main..HEAD") == ""

    @pytest.mark.usefixtures("checkout")
    def should_leave_the_main_git_dir_to_git_pull(self, gup, project):
        result = gup(project / ".git")

        assert result.returncode == 128
        assert "must be run in a work tree" in result.stderr
        assert "gup:" not in result.stderr


class TestCleanUp:
    def should_delete_the_branches_and_worktrees_merged_on_origin_after_pulling(
            self, gup, git, tmp_path, project, added):
        shipped = added("shipped")
        ship_by_squash_merge(git, tmp_path, shipped, "shipped")

        result = gup(project)

        assert result.returncode == 0, result.stderr
        assert git(project, "rev-parse", "HEAD") == git(project, "rev-parse", "origin/main")
        assert not shipped.exists()
        assert "shipped" not in branches(git, project)

    def should_also_clean_up_when_run_inside_a_worktree_git_dir(
            self, gup, git, tmp_path, project, checkout, added):
        shipped = added("shipped")
        ship_by_squash_merge(git, tmp_path, shipped, "shipped")

        result = gup(project / ".git" / "worktrees" / "feature")

        assert result.returncode == 0, result.stderr
        assert checkout.exists()
        assert not shipped.exists()
        assert "shipped" not in branches(git, project)

    def should_leave_merged_branches_alone_when_the_pull_fails(
            self, gup, git, tmp_path, project, added):
        shipped = added("shipped")
        ship_by_squash_merge(git, tmp_path, shipped, "shipped")
        unpushed = added("unpushed")

        result = gup(unpushed)

        assert result.returncode != 0
        assert shipped.exists()
        assert "shipped" in branches(git, project)


class TestComplete:
    def should_offer_the_remotes_first(self, gup, project):
        result = gup(project, "--complete")

        assert result.stdout.split() == ["origin"]

    @pytest.mark.usefixtures("checkout")
    def should_offer_the_branches_of_the_chosen_remote(self, gup, project):
        result = gup(project, "--complete", "origin")

        assert result.stdout.split() == ["feature", "main"]


@pytest.fixture
def stand_in_gup(run_bash, tmp_path):
    def _gup(branch, *args, inside_git_dir=False, pull_status=0):
        calls_file = tmp_path / "git-calls"
        result = run_bash("gup", list(args), mock_bins={"git": GIT_STAND_IN}, cwd=tmp_path, env_extra={
            "GIT_CALLS": str(calls_file), "STAND_IN_BRANCH": branch, "STAND_IN_PULL_STATUS": str(pull_status),
            "STAND_IN_INSIDE_GIT_DIR": "true" if inside_git_dir else "false"})
        return result, [re.sub(r"^-C \S+ ", "", call) for call in calls_file.read_text().splitlines()]
    return _gup


class TestRebaseMode:
    @pytest.mark.parametrize("branch", ["main", "master"])
    def should_rebase_the_default_branches_without_keeping_merges(self, stand_in_gup, branch):
        result, calls = stand_in_gup(branch)

        assert result.returncode == 0, result.stderr
        assert calls == ["rev-parse --is-inside-git-dir", "symbolic-ref -q --short HEAD",
                         "pull --rebase=true --autostash", "wt rm --merged"]

    @pytest.mark.parametrize("branch", ["feature", "mainline", "release/main", "master-old", ""])
    def should_keep_merges_when_rebasing_any_other_branch_or_a_detached_head(self, stand_in_gup, branch):
        result, calls = stand_in_gup(branch)

        assert result.returncode == 0, result.stderr
        assert "pull --rebase=merges --autostash" in calls
        assert not [call for call in calls if call.startswith("pull --rebase=true")]

    def should_hand_the_pull_arguments_to_git_after_the_autostash_flag(self, stand_in_gup):
        _, calls = stand_in_gup("feature", "origin", "release")

        assert "pull --rebase=merges --autostash origin release" in calls

    def should_skip_the_cleanup_and_return_the_status_of_a_failed_pull(self, stand_in_gup):
        result, calls = stand_in_gup("main", pull_status=3)

        assert result.returncode == 3
        assert calls[-1] == "pull --rebase=true --autostash"

    def should_pick_the_mode_of_the_checkout_branch_inside_a_worktree_git_dir(self, stand_in_gup):
        result, calls = stand_in_gup("main", inside_git_dir=True)

        assert result.returncode == 0, result.stderr
        assert result.stderr == "gup: updating /stand-in/checkout\n"
        assert calls == ["rev-parse --is-inside-git-dir", "rev-parse --absolute-git-dir",
                         "rev-parse --path-format=absolute --git-common-dir", "symbolic-ref -q HEAD", "wt path main",
                         "symbolic-ref -q --short HEAD", "pull --rebase=true --autostash", "wt rm --merged"]
