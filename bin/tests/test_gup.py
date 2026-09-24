import pytest

from bin.tests.conftest import WORKTREES, move_to_other_mount


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

    @pytest.mark.usefixtures("checkout")
    def should_leave_the_main_git_dir_to_git_pull(self, gup, project):
        result = gup(project / ".git")

        assert result.returncode == 128
        assert "must be run in a work tree" in result.stderr
        assert "gup:" not in result.stderr


class TestComplete:
    def should_offer_the_remotes_first(self, gup, project):
        result = gup(project, "--complete")

        assert result.stdout.split() == ["origin"]

    @pytest.mark.usefixtures("checkout")
    def should_offer_the_branches_of_the_chosen_remote(self, gup, project):
        result = gup(project, "--complete", "origin")

        assert result.stdout.split() == ["feature", "main"]
