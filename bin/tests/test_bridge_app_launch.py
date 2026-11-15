import pytest


@pytest.fixture
def launch(run_bash, tmp_path):
    calls = tmp_path / "open.calls"

    def _run(body):
        return run_bash("bridge-app-launch", stdin=body, env_extra={"HOME": str(tmp_path)},
                        mock_bins={"open": f'echo "$*" >> "{calls}"'})
    _run.calls = lambda: calls.read_text().splitlines() if calls.exists() else []
    return _run


class TestBridgeAppLaunch:
    def should_ask_for_an_app_name_when_the_body_is_empty(self, launch):
        result = launch("")

        assert result.returncode == 1
        assert "app name required in POST body" in result.stderr
        assert launch.calls() == []

    @pytest.mark.parametrize("body", ["Notes\n", "Notes"])
    def should_launch_the_named_app_with_or_without_a_trailing_newline(self, launch, body):
        result = launch(body)

        assert result.returncode == 0, result.stderr
        assert "Launched: Notes" in result.stdout
        assert launch.calls() == ["-a Notes"]
