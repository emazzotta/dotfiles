import os
import subprocess
import uuid

import pytest

OTHER_PID = "424242"
LISTING = f"""
echo "{OTHER_PID} sleep 31337"
echo "$PPID bash /somewhere/killgrep pattern"
"""
ONLY_THE_SCRIPT = 'echo "$PPID bash /somewhere/killgrep pattern"'
RECORD = 'echo "$(basename "$0") $*" >> "$CALLS_LOG"'


@pytest.fixture
def killgrep(run_bash, tmp_path):
    calls = tmp_path / "calls"

    def _run(answer, pgrep=LISTING):
        return run_bash("killgrep", ["pattern"], stdin=answer, env_extra={"CALLS_LOG": str(calls)},
                        mock_bins={"pgrep": pgrep, "kill": RECORD, "pkill": RECORD})
    _run.calls = lambda: calls.read_text().splitlines() if calls.exists() else []
    return _run


class TestKillgrep:
    def should_kill_the_listed_processes_by_pid_and_never_the_script_itself(self, killgrep):
        result = killgrep("y")

        assert result.returncode == 0, result.stderr
        assert killgrep.calls() == [f"kill {OTHER_PID}"]
        assert "Processes killed." in result.stdout

    def should_not_list_the_script_itself(self, killgrep):
        result = killgrep("n")

        assert f"{OTHER_PID} sleep 31337" in result.stdout
        assert "killgrep" not in result.stdout

    def should_report_no_processes_when_only_the_script_itself_matches(self, killgrep):
        result = killgrep("y", pgrep=ONLY_THE_SCRIPT)

        assert result.returncode == 1
        assert "No processes found" in result.stdout
        assert killgrep.calls() == []

    def should_report_no_processes_when_pgrep_matches_nothing(self, killgrep):
        result = killgrep("y", pgrep="exit 1")

        assert result.returncode == 1
        assert "No processes found" in result.stdout

    def should_leave_the_processes_alone_when_cancelled(self, killgrep):
        result = killgrep("n")

        assert "Operation cancelled." in result.stdout
        assert killgrep.calls() == []


class TestKillgrepWithTheRealPgrep:
    """Read-only: every run answers n or finds nothing, so nothing is killed."""

    @pytest.fixture
    def marker(self):
        return f"killgrep-test-{uuid.uuid4().hex}"

    def should_find_nothing_when_only_the_script_carries_the_pattern(self, run_bash, marker):
        result = run_bash("killgrep", [marker], stdin="n\n")

        assert result.returncode == 1
        assert "No processes found" in result.stdout

    def should_list_only_the_matching_process_and_not_the_script(self, run_bash, marker):
        sleeper = subprocess.Popen(["bash", "-c", f"exec -a {marker} sleep 300"], env=os.environ.copy())
        try:
            result = run_bash("killgrep", [marker], stdin="n\n")
        finally:
            sleeper.kill()
            sleeper.wait()

        listed = result.stdout.split("Found processes:")[1].split("Are you sure")[0].split("\n\n")[0]
        assert [line.split()[0] for line in listed.strip().splitlines()] == [str(sleeper.pid)]
        assert "Operation cancelled." in result.stdout
