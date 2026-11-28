import pytest


@pytest.fixture
def bridge(run_cli, tmp_path):
    calls = tmp_path / "agent-desktop.calls"

    def _run(body, args=None, mock_body=None):
        record = f'printf "%s\\n" "$@" > "{calls}"'
        return run_cli("agent-desktop-bridge", args=args, stdin=body,
                       mock_bins={"agent-desktop": mock_body or record})
    _run.calls = lambda: calls.read_text().splitlines() if calls.exists() else None
    return _run


class TestAgentDesktopBridge:
    @pytest.mark.parametrize("body", ["", "\n", "   \n"])
    def should_ask_for_a_command_when_the_body_is_empty(self, bridge, body):
        result = bridge(body)

        assert result.returncode == 1
        assert "agent-desktop arguments required in POST body" in result.stderr
        assert bridge.calls() is None

    @pytest.mark.parametrize("body", [
        "snapshot --app 'System Settings' -i\n",
        'snapshot --app "System Settings" -i',
    ])
    def should_split_the_body_into_arguments_like_a_shell(self, bridge, body):
        result = bridge(body)

        assert result.returncode == 0, result.stderr
        assert bridge.calls() == ["snapshot", "--app", "System Settings", "-i"]

    def should_refuse_a_body_of_more_than_one_line(self, bridge):
        result = bridge("permissions\nlaunch Terminal\n")

        assert result.returncode == 1
        assert "one line" in result.stderr
        assert bridge.calls() is None

    def should_refuse_a_line_the_approval_prompt_would_cut(self, bridge):
        result = bridge("type @s1:e8 '" + "x" * 100 + "'\n")

        assert result.returncode == 1
        assert "100 characters" in result.stderr
        assert bridge.calls() is None

    def should_refuse_unbalanced_quotes(self, bridge):
        result = bridge("snapshot --app 'System Settings\n")

        assert result.returncode == 1
        assert "No closing quotation" in result.stderr
        assert bridge.calls() is None

    def should_return_the_output_and_exit_status_of_agent_desktop(self, bridge):
        result = bridge("click @s1:e8\n", mock_body='echo \'{"ok": false}\'; exit 3')

        assert result.returncode == 3
        assert result.stdout.strip() == '{"ok": false}'

    def should_print_usage_without_running_agent_desktop(self, bridge):
        result = bridge("", args=["--help"])

        assert result.returncode == 0
        assert "shell-quoted" in result.stdout
        assert bridge.calls() is None
