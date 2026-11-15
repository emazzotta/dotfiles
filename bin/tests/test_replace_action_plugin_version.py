import pytest

PLUGIN = "actions/checkout"


def make_repo(root):
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)

    def _workflow(name, content):
        path = workflows / name
        path.write_text(content)
        return path
    _workflow.root = root
    return _workflow


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path / "project")


def run_replace(run_cli, repo, version):
    return run_cli("replace_action_plugin_version", [PLUGIN, version], cwd=repo.root)


class TestReplaceActionPluginVersion:
    def test_should_update_the_pin_of_a_workflow(self, run_cli, repo):
        workflow = repo("ci.yml", f"steps:\n  - uses: {PLUGIN}@v3\n")

        result = run_replace(run_cli, repo, "v7")

        assert result.returncode == 0, result.stderr
        assert workflow.read_text() == f"steps:\n  - uses: {PLUGIN}@v7\n"
        assert f"Updated {workflow}" in result.stdout

    def test_should_update_a_workflow_in_a_directory_with_spaces(self, run_cli, tmp_path):
        spaced = make_repo(tmp_path / "my project")
        workflow = spaced("ci.yml", f"- uses: {PLUGIN}@v3\n")

        result = run_replace(run_cli, spaced, "v7")

        assert result.returncode == 0, result.stderr
        assert workflow.read_text() == f"- uses: {PLUGIN}@v7\n"

    def test_should_update_an_old_pin_when_another_job_already_uses_the_target(self, run_cli, repo):
        workflow = repo("ci.yml", f"- uses: {PLUGIN}@v3\n- uses: {PLUGIN}@v7\n")

        result = run_replace(run_cli, repo, "v7")

        assert result.returncode == 0, result.stderr
        assert workflow.read_text() == f"- uses: {PLUGIN}@v7\n- uses: {PLUGIN}@v7\n"

    def test_should_replace_a_pin_that_only_starts_with_the_target(self, run_cli, repo):
        workflow = repo("ci.yml", f"- uses: {PLUGIN}@v7.1.0\n")

        result = run_replace(run_cli, repo, "v7")

        assert result.returncode == 0, result.stderr
        assert workflow.read_text() == f"- uses: {PLUGIN}@v7\n"

    def test_should_not_report_a_workflow_that_is_already_up_to_date(self, run_cli, repo):
        repo("current.yml", f"- uses: {PLUGIN}@v7\n")
        stale = repo("stale.yml", f"- uses: {PLUGIN}@v3\n")

        result = run_replace(run_cli, repo, "v7")

        assert result.returncode == 0, result.stderr
        assert f"Updated {stale}" in result.stdout
        assert "current.yml" not in result.stdout

    def test_should_leave_a_workflow_without_the_plugin_untouched(self, run_cli, repo):
        other = repo("other.yml", "- uses: actions/cache@v4\n")

        result = run_replace(run_cli, repo, "v7")

        assert result.returncode == 0, result.stderr
        assert other.read_text() == "- uses: actions/cache@v4\n"
        assert "other.yml" not in result.stdout

    def test_should_leave_no_backup_files_behind(self, run_cli, repo):
        repo("ci.yml", f"- uses: {PLUGIN}@v3\n")

        run_replace(run_cli, repo, "v7")

        assert sorted(path.name for path in (repo.root / ".github" / "workflows").iterdir()) == ["ci.yml"]
