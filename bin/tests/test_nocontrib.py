import pytest

AUTHOR = "Emanuele"
STRANGER = "Someone Else"


@pytest.fixture
def tree(tmp_path, git):
    root = tmp_path / "tree"
    root.mkdir()

    def _repo(relative, author):
        path = root / relative
        path.mkdir(parents=True, exist_ok=True)
        git(path, "init")
        git(path, "-c", f"user.name={author}", "-c", "user.email=a@example.com", "commit", "--allow-empty", "-m", "work")
        return path
    _repo.root = root
    return _repo


def reported(run_cli, git_env, root):
    result = run_cli("nocontrib", env_extra=git_env, cwd=root)
    assert result.returncode == 0, result.stderr
    return sorted(line.removeprefix("No git contributions in: ") for line in result.stdout.splitlines())


class TestNocontrib:
    def test_should_report_only_repositories_without_a_commit_by_the_author(self, run_cli, git_env, tree):
        tree("mine", AUTHOR)
        tree("theirs", STRANGER)

        assert reported(run_cli, git_env, tree.root) == ["./theirs"]

    def test_should_find_repositories_in_directories_with_spaces(self, run_cli, git_env, tree):
        tree("my work/theirs", STRANGER)
        tree("my work/mine", AUTHOR)

        assert reported(run_cli, git_env, tree.root) == ["./my work/theirs"]

    def test_should_find_repositories_up_to_three_levels_deep(self, run_cli, git_env, tree):
        tree("a/b/theirs", STRANGER)

        assert reported(run_cli, git_env, tree.root) == ["./a/b/theirs"]

    def test_should_not_report_the_working_directory_itself(self, run_cli, git_env, tree):
        tree("", STRANGER)

        assert reported(run_cli, git_env, tree.root) == []

    def test_should_report_nothing_when_no_repository_exists(self, run_cli, git_env, tree):
        (tree.root / "plain").mkdir()

        assert reported(run_cli, git_env, tree.root) == []
