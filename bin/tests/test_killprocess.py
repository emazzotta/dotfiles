import pytest

OTHER_PID = "424242"
PS_STAND_IN = f"""
echo "user {OTHER_PID} 1 0 00:00 ? 00:00:00 sleep 31337"
echo "user 424243 1 0 00:00 ? 00:00:00 unrelated"
"""
RECORD_KILL = 'echo "kill $*" >> "$CALLS_LOG"'


@pytest.fixture
def killprocess(run_bash, tmp_path):
    calls = tmp_path / "calls"

    def _run(args, answer=None):
        return run_bash("killprocess", args, stdin=answer, env_extra={"CALLS_LOG": str(calls)},
                        mock_bins={"ps": PS_STAND_IN, "kill": RECORD_KILL})
    _run.calls = lambda: calls.read_text().splitlines() if calls.exists() else []
    return _run


class TestKillprocess:
    def should_show_the_usage_when_given_no_argument(self, killprocess):
        result = killprocess([])

        assert "usage: killprocess" in result.stdout
        assert "unbound variable" not in result.stderr
        assert killprocess.calls() == []

    def should_kill_the_matching_process_by_pid_after_confirmation(self, killprocess):
        result = killprocess(["31337"], "y\n")

        assert "Processes killed." in result.stdout
        assert killprocess.calls() == [f"kill {OTHER_PID}"]

    def should_not_kill_when_the_answer_is_no(self, killprocess):
        killprocess(["31337"], "n\n")

        assert killprocess.calls() == []

    def should_report_when_no_process_matches(self, killprocess):
        result = killprocess(["no-such-process"])

        assert result.returncode == 1
        assert "No such process found." in result.stdout
