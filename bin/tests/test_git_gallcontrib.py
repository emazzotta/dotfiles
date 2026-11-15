import pytest

from bin.tests.conftest import WORKTREES, commit_file


@pytest.fixture
def scan(run_cli, git_env):
    def _scan(root):
        result = run_cli("git_gallcontrib", [str(root)], env_extra={**git_env, "NO_COLOR": "1"})
        assert result.returncode == 0, result.stderr
        return result.stdout.splitlines()
    return _scan


@pytest.fixture
def init_repo(git):
    def _init_repo(repo, commits):
        repo.mkdir(parents=True)
        git(repo, "init", "-q")
        for number in range(commits):
            commit_file(git, repo, f"file{number}.txt", str(number))
        return repo
    return _init_repo


class TestRepositoryDiscovery:
    def should_count_a_linked_worktree_once_with_its_main_checkout(self, scan, init_repo, git, tmp_path):
        repo = init_repo(tmp_path / "projects" / "app", commits=2)
        git(repo, "worktree", "add", "-q", "-b", "feature", str(repo / WORKTREES / "feature"))

        lines = scan(tmp_path / "projects")

        assert lines[lines.index("Repositories (1)") + 1:] == ["2 app"]

    def should_count_a_separate_repository_on_its_own(self, scan, init_repo, tmp_path):
        init_repo(tmp_path / "projects" / "app", commits=2)
        init_repo(tmp_path / "projects" / "lib", commits=1)

        lines = scan(tmp_path / "projects")

        assert lines[lines.index("Repositories (2)") + 1:] == ["2 app", "1 lib"]
