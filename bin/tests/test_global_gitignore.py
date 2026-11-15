import subprocess

import pytest

from bin.tests.conftest import BIN_DIR

GLOBAL_GITIGNORE = BIN_DIR.parent / "git" / ".global_gitignore"


@pytest.fixture
def repo(tmp_path):
    directory = tmp_path / "repo"
    directory.mkdir()
    subprocess.run(["git", "init", "-q", str(directory)], check=True)
    return directory


def is_ignored(repo, path):
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", f"core.excludesFile={GLOBAL_GITIGNORE}", "check-ignore", "-q", path],
        capture_output=True, text=True,
    )
    assert result.returncode in (0, 1), result.stderr
    return result.returncode == 0


class TestGlobalGitignore:
    @pytest.mark.parametrize("path", ["target/classes/App.class", "module/target/app.jar", "out/main.o"])
    def should_ignore_the_build_output_directories(self, repo, path):
        assert is_ignored(repo, path)

    def should_not_ignore_a_source_file(self, repo):
        assert not is_ignored(repo, "src/main.c")
