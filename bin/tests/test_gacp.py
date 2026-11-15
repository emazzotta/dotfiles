import stat

import pytest

PUSH_RECORDER = 'echo gp >> "$CALLS"'
REJECTING_HOOK = "#!/bin/sh\nexit 1\n"


@pytest.fixture
def gacp(run_cli, tmp_path, project, git_env):
    calls = tmp_path / "calls"
    calls.touch()

    def _run(*args):
        return run_cli(
            "gacp", list(args), env_extra={**git_env, "CALLS": str(calls)},
            mock_bins={"gp": PUSH_RECORDER}, cwd=project,
        )
    _run.project = project
    _run.pushes = lambda: calls.read_text().splitlines()
    return _run


class TestGacp:
    def test_should_push_after_a_successful_commit(self, gacp, git):
        (gacp.project / "new.txt").write_text("content\n")

        result = gacp("add new file")

        assert result.returncode == 0, result.stderr
        assert git(gacp.project, "log", "-1", "--format=%s") == "Add new file"
        assert gacp.pushes() == ["gp"]

    def test_should_stop_without_pushing_when_a_hook_rejects_the_commit(self, gacp):
        (gacp.project / "new.txt").write_text("content\n")
        hook = gacp.project / ".git" / "hooks" / "pre-commit"
        hook.write_text(REJECTING_HOOK)
        hook.chmod(hook.stat().st_mode | stat.S_IEXEC)

        result = gacp("add new file")

        assert result.returncode != 0
        assert gacp.pushes() == []

    def test_should_stop_without_pushing_when_staging_fails(self, gacp, git):
        git(gacp.project, "config", "filter.broken.clean", "false")
        git(gacp.project, "config", "filter.broken.required", "true")
        (gacp.project / ".gitattributes").write_text("*.bin filter=broken\n")
        (gacp.project / "data.bin").write_text("content\n")

        result = gacp("add data")

        assert result.returncode != 0
        assert gacp.pushes() == []

    def test_should_push_the_existing_commits_when_there_is_nothing_to_commit(self, gacp, git):
        head = git(gacp.project, "rev-parse", "HEAD")

        result = gacp("add new file")

        assert result.returncode == 0, result.stderr
        assert git(gacp.project, "rev-parse", "HEAD") == head
        assert gacp.pushes() == ["gp"]
