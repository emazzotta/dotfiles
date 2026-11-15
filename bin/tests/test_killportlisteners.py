import pytest

LISTENER = "41000"
CLIENT = "41001"
LSOF_MOCK = f"""
case "$*" in *:3000*) ;; *) exit 1 ;; esac
echo {LISTENER}
case "$*" in *-sTCP:LISTEN*) ;; *) echo {CLIENT} ;; esac
"""
KILL_MOCK = 'echo "$*" >> "$KILL_LOG"'


@pytest.fixture
def killportlisteners(run_bash, tmp_path):
    kill_log = tmp_path / "kill.log"

    def _run():
        return run_bash("killportlisteners", env_extra={"KILL_LOG": str(kill_log)},
                        mock_bins={"lsof": LSOF_MOCK, "kill": KILL_MOCK})
    _run.kill_log = kill_log
    return _run


class TestKillportlisteners:
    def should_kill_the_listener_and_leave_a_connected_client_alone(self, killportlisteners):
        result = killportlisteners()

        assert result.returncode == 0, result.stderr
        assert killportlisteners.kill_log.read_text().split() == ["-9", LISTENER]

    def should_report_the_ports_nobody_listens_on(self, killportlisteners):
        result = killportlisteners()

        assert "No processes listening on port 8080" in result.stdout
        assert "Killing processes listening on port 3000" in result.stdout
