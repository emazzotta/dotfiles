import pytest

from bin.tests.conftest import branches, commit_file

SCRIPT = "git_squash_commits_x_y"
COMMITS = 6


@pytest.fixture
def repo(tmp_path, git):
    repo = tmp_path / "repo"
    git(tmp_path, "init", str(repo))
    for number in range(1, COMMITS + 1):
        commit_file(git, repo, f"f{number}.txt", f"{number}\n", f"Commit {number}")
    return repo


@pytest.fixture
def sha(git, repo):
    originals = {number: git(repo, "rev-parse", f"main~{COMMITS - number}") for number in range(1, COMMITS + 1)}
    return originals.__getitem__


@pytest.fixture
def squash(run_bash, git_env, repo):
    def _squash(first, last, answer="n\n"):
        return run_bash(SCRIPT, ["main", first, last], env_extra={**git_env, "GIT_EDITOR": "true"},
                        stdin=answer, cwd=repo)
    return _squash


def subjects(git, repo):
    return git(repo, "log", "--format=%s", "main").splitlines()


class TestGitSquashCommitsXY:
    def should_replace_the_range_by_one_commit_and_keep_the_commits_after_it(self, squash, sha, git, repo):
        tree = git(repo, "rev-parse", "main^{tree}")

        result = squash(sha(2), sha(4))

        assert result.returncode == 0, result.stderr
        history = subjects(git, repo)
        assert len(history) == 4
        assert history[:2] == ["Commit 6", "Commit 5"]
        assert history[3] == "Commit 1"
        assert git(repo, "log", "--merges", "--format=%h", "main") == ""
        assert git(repo, "rev-parse", "main^{tree}") == tree

    def should_keep_a_merge_commit_after_the_range_together_with_the_commits_it_merged(self, squash, sha, git, repo):
        git(repo, "checkout", "-q", "-b", "side", sha(4))
        commit_file(git, repo, "side.txt", "s\n", "Side work")
        git(repo, "checkout", "-q", "main")
        git(repo, "merge", "--no-ff", "side", "-m", "Merge side")

        result = squash(sha(2), sha(4))

        assert result.returncode == 0, result.stderr
        assert "Side work" in subjects(git, repo)
        assert git(repo, "log", "--merges", "--format=%s", "main") == "Merge side"
        assert len(subjects(git, repo)) == 6

    def should_combine_the_messages_of_the_squashed_commits(self, squash, sha, git, repo):
        squash(sha(2), sha(4))

        message = git(repo, "log", "-1", "--format=%B", "main~2")
        assert all(f"Commit {number}" in message for number in (2, 3, 4))

    def should_squash_up_to_the_tip_of_the_branch(self, squash, sha, git, repo):
        result = squash(sha(4), sha(6))

        assert result.returncode == 0, result.stderr
        assert len(subjects(git, repo)) == 4
        assert git(repo, "status", "--porcelain") == ""

    def should_resolve_relative_references_before_it_moves_head(self, squash, git, repo):
        result = squash("main~4", "main~2")

        assert result.returncode == 0, result.stderr
        assert len(subjects(git, repo)) == 4

    def should_leave_the_repository_on_the_branch_without_the_temporary_branch(self, squash, sha, git, repo):
        squash(sha(2), sha(4))

        assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"
        assert branches(git, repo) == ["main"]

    @pytest.mark.parametrize("answer", ["n\n", "\n"])
    def should_not_push_unless_asked(self, squash, sha, answer):
        result = squash(sha(2), sha(4), answer)

        assert "Changes not pushed" in result.stdout

    def should_refuse_a_range_that_is_not_in_the_branch(self, squash, sha, git, repo):
        git(repo, "checkout", "-q", "-b", "other", sha(2))
        commit_file(git, repo, "other.txt", "x\n", "Other work")
        other_tip = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "-q", "main")
        before = git(repo, "rev-parse", "main")

        result = squash(sha(2), other_tip)

        assert result.returncode != 0
        assert git(repo, "rev-parse", "main") == before
        assert branches(git, repo) == ["main", "other"]

    def should_refuse_a_range_that_contains_a_merge_commit(self, squash, sha, git, repo):
        git(repo, "checkout", "-q", "-b", "side", sha(2))
        commit_file(git, repo, "side.txt", "s\n", "Side work")
        git(repo, "checkout", "-q", "main")
        git(repo, "merge", "--no-ff", "side", "-m", "Merge side")
        commit_file(git, repo, "after.txt", "a\n", "After merge")
        before = git(repo, "rev-parse", "main")

        result = squash(sha(2), "main~1")

        assert result.returncode != 0
        assert git(repo, "rev-parse", "main") == before

    def should_refuse_a_dirty_working_tree(self, squash, sha, git, repo):
        (repo / "f1.txt").write_text("changed\n")
        before = git(repo, "rev-parse", "main")

        result = squash(sha(2), sha(4))

        assert result.returncode != 0
        assert git(repo, "rev-parse", "main") == before
        assert (repo / "f1.txt").read_text() == "changed\n"

    def should_not_delete_a_temporary_branch_that_holds_other_commits(self, squash, sha, git, repo):
        git(repo, "checkout", "-q", "-b", "temp_squash_branch")
        commit_file(git, repo, "mine.txt", "m\n", "Only on the temp branch")
        git(repo, "checkout", "-q", "main")
        before = git(repo, "rev-parse", "main")

        result = squash(sha(2), sha(4))

        assert result.returncode != 0
        assert git(repo, "log", "-1", "--format=%s", "temp_squash_branch") == "Only on the temp branch"
        assert git(repo, "rev-parse", "main") == before
