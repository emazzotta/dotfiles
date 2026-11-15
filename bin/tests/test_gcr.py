import pytest

ENVIFY_MOCK = 'export LEO_GIT_CRYPT="$(printf "decoded key" | base64)"'
GIT_CRYPT_MOCK = """
case "$PWD" in *broken*) exit 1 ;; esac
if [ "$1" = unlock ]; then cat "$2" >> "$UNLOCK_LOG"; echo >> "$UNLOCK_LOG"; fi
"""


@pytest.fixture
def gcr(run_bash, tmp_path, git_env):
    wdir = tmp_path / "wdir"
    key_dir = tmp_path / "keys"
    outside = tmp_path / "outside"
    for folder in (wdir / "leo-productions", key_dir, outside):
        folder.mkdir(parents=True)

    def add_repo(name):
        (wdir / "leo-productions" / name / ".git").mkdir(parents=True)

    def _run(*args):
        return run_bash(
            "gcr", list(args),
            env_extra={**git_env, "WDIR": str(wdir), "TMPDIR": str(key_dir),
                       "UNLOCK_LOG": str(tmp_path / "unlock.log"),
                       "GIT_CEILING_DIRECTORIES": str(tmp_path)},
            mock_bins={"envify": ENVIFY_MOCK, "git-crypt": GIT_CRYPT_MOCK},
            cwd=outside,
        )
    _run.add_repo = add_repo
    _run.key_files = lambda: list(key_dir.iterdir())
    _run.unlock_log = tmp_path / "unlock.log"
    return _run


class TestGcr:
    def should_leave_no_decoded_key_behind_after_unlocking_several_repos(self, gcr):
        for name in ("alpha", "bravo", "charlie"):
            gcr.add_repo(name)

        result = gcr("unlock")

        assert gcr.unlock_log.read_text().split() == ["decoded", "key"] * 3
        assert gcr.key_files() == []
        assert result.returncode == 0, result.stderr

    def should_remove_the_decoded_key_and_fail_when_git_crypt_cannot_unlock(self, gcr):
        gcr.add_repo("broken")

        result = gcr("unlock")

        assert result.returncode == 1
        assert gcr.key_files() == []

    def should_exit_zero_when_every_repo_succeeded(self, gcr):
        gcr.add_repo("alpha")
        gcr.add_repo("bravo")

        result = gcr("lock")

        assert result.returncode == 0, result.stderr

    def should_exit_nonzero_when_one_repo_failed(self, gcr):
        gcr.add_repo("alpha")
        gcr.add_repo("broken")

        result = gcr("lock")

        assert result.returncode == 1
