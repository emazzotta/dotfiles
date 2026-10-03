import pytest

APPROVE_LINE = "Approve on your phone: https://unlock.example/approve?id=Ab12"


@pytest.fixture
def envify_as(run_bash):
    def _run(envify_body, *pairs):
        return run_bash("envify-as", list(pairs), mock_bins={"envify": envify_body}, isolate_path=True)
    return _run


class TestEnvifyAs:
    def test_should_export_each_secret_under_its_new_name(self, envify_as):
        result = envify_as("export JIRA_TOKEN=t0ken", "ATLASSIAN_TOKEN=JIRA_TOKEN")

        assert (result.returncode, result.stdout) == (0, "export ATLASSIAN_TOKEN=t0ken\n")

    def test_should_keep_envify_output_out_of_the_exports(self, envify_as):
        result = envify_as("echo noise\nexport JIRA_TOKEN=t0ken", "ATLASSIAN_TOKEN=JIRA_TOKEN")

        assert result.stdout == "export ATLASSIAN_TOKEN=t0ken\n"

    def test_should_pass_on_what_envify_said_when_a_secret_comes_back_empty(self, envify_as):
        result = envify_as(f'echo "{APPROVE_LINE}" >&2', "ATLASSIAN_TOKEN=JIRA_TOKEN")

        assert result.returncode == 1
        assert APPROVE_LINE in result.stderr
        assert "source var 'JIRA_TOKEN' is empty" in result.stderr
