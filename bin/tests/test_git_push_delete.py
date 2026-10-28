import pytest

from bin.tests.conftest import branches


@pytest.fixture
def push_delete(run_cli, git_env, project):
    def _push_delete(*args):
        return run_cli("git-push-delete", list(args), env_extra=git_env, cwd=project)
    return _push_delete


@pytest.fixture
def origin(project):
    return project.parent / "origin.git"


def push_branches(git, project, *names):
    for name in names:
        git(project, "push", "origin", f"main:refs/heads/{name}")


class TestPushDelete:
    def should_delete_the_branch_on_origin(self, push_delete, git, project, origin):
        push_branches(git, project, "feature")

        result = push_delete("feature")

        assert result.returncode == 0, result.stderr
        assert branches(git, origin) == ["main"]

    def should_delete_every_branch_on_origin_a_glob_matches(self, push_delete, git, project, origin):
        push_branches(git, project, "LEO-1-review-a", "LEO-1-review-b/nested", "LEO-1-other")

        result = push_delete("LEO-1-review-*")

        assert result.returncode == 0, result.stderr
        assert branches(git, origin) == ["LEO-1-other", "main"]

    def should_fail_on_a_glob_that_matches_nothing_and_still_delete_the_others(
            self, push_delete, git, project, origin):
        push_branches(git, project, "feature")

        result = push_delete("LEO-1-*", "feature")

        assert result.returncode == 1
        assert "no branch on origin matches 'LEO-1-*'" in result.stderr
        assert branches(git, origin) == ["main"]

    def should_exit_with_usage_when_no_branch_is_given(self, push_delete):
        result = push_delete()

        assert result.returncode == 2
        assert "Usage: git push-delete" in result.stderr


class TestComplete:
    def should_offer_the_branches_origin_had_at_the_last_fetch(self, push_delete, git, project):
        push_branches(git, project, "feature")
        git(project, "fetch", "origin")

        result = push_delete("--complete")

        assert result.stdout.split() == ["feature", "main"]
