import pytest

SCRIPT = "ops/scripts/gitlab/build_variables.sh"


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "ws"
    for project in ("alpha", "beta", "gamma"):
        target = root / project / SCRIPT
        target.parent.mkdir(parents=True)
        target.write_text(f"old {project}\n")
    (root / "alpha" / SCRIPT).write_text("new content\n")
    return root


class TestSyncFile:
    def test_should_update_every_matching_file_and_print_the_summary(self, run_cli, workspace):
        result = run_cli("sync_file", [f"alpha/{SCRIPT}"], cwd=workspace)

        assert result.returncode == 0, result.stderr
        assert (workspace / "beta" / SCRIPT).read_text() == "new content\n"
        assert (workspace / "gamma" / SCRIPT).read_text() == "new content\n"
        assert "2 file(s) updated, 0 file(s) failed" in result.stdout

    def test_should_report_no_match_when_no_other_file_has_the_path(self, run_cli, workspace):
        lonely = workspace / "lonely"
        (lonely / "tools").mkdir(parents=True)
        (lonely / "tools" / "only.sh").write_text("x\n")

        result = run_cli("sync_file", ["lonely/tools/only.sh"], cwd=workspace)

        assert result.returncode == 0, result.stderr
        assert "No matching files found" in result.stdout
        assert "Found 1 matching" not in result.stdout
