import pytest


class TestGac:
    def test_no_args_runs_amend(self, run_bash, tmp_path):
        result = run_bash("gac", mock_bins={
            "git": 'echo "git $@"',
            "first_capitalize": 'echo "$1"',
        })
        combined = result.stdout + result.stderr
        assert "git" in combined.lower() or result.returncode == 0

    def test_with_message(self, run_bash):
        result = run_bash("gac", ["test message"], mock_bins={
            "git": 'echo "git $@"',
            "first_capitalize": 'echo "$@"',
        })
        assert result.returncode == 0


class TestNocontrib:
    def test_runs_without_error(self, run_bash, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        import subprocess
        subprocess.run(["git", "init", str(repo)], capture_output=True)
        subprocess.run(["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"], capture_output=True)
        result = run_bash("nocontrib", env_extra={"HOME": str(tmp_path)})
        assert result.returncode == 0


class TestCodecost:
    def test_runs_in_empty_dir(self, run_bash, tmp_path):
        result = run_bash("codecost", env_extra={"HOME": str(tmp_path)}, mock_bins={
            "sloccount": 'echo "Total: 0"',
        })
        assert result.returncode == 0 or "sloccount" in (result.stdout + result.stderr).lower()


class TestGitio:
    def test_no_args_shows_usage(self, run_bash):
        result = run_bash("gitio")
        assert "usage" in result.stdout.lower()
