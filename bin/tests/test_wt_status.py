from pathlib import Path

import pytest

PANE = "%7"


@pytest.fixture
def tmux_calls(tmp_path: Path) -> Path:
    return tmp_path / "tmux-calls"


@pytest.fixture
def wt_status(run_cli, tmux_calls):
    def _run(*args, pane=PANE):
        return run_cli("wt-status", list(args), env_extra={"TMUX_PANE": pane or ""},
                       mock_bins={"tmux": f'printf "%s\\n" "$*" >> "{tmux_calls}"'})
    return _run


def calls(tmux_calls: Path) -> list[str]:
    return tmux_calls.read_text().splitlines() if tmux_calls.exists() else []


class TestReport:
    def should_set_the_words_then_the_state_on_its_own_pane(self, wt_status, tmux_calls):
        result = wt_status("waiting", "Approve the plan")

        assert (result.returncode, calls(tmux_calls)) == (0, [
            f"set-option -p -t {PANE} @wt_label Approve the plan",
            f"set-option -p -t {PANE} @wt_state waiting",
        ])

    def should_report_no_words_when_none_are_given(self, wt_status, tmux_calls):
        wt_status("busy")

        assert calls(tmux_calls) == [f"set-option -p -t {PANE} @wt_label ", f"set-option -p -t {PANE} @wt_state busy"]

    def should_unset_both_options_when_cleared(self, wt_status, tmux_calls):
        wt_status("clear")

        assert calls(tmux_calls) == [f"set-option -p -u -t {PANE} @wt_state", f"set-option -p -u -t {PANE} @wt_label"]

    def should_refuse_to_report_outside_a_tmux_pane(self, wt_status, tmux_calls):
        result = wt_status("idle", pane=None)

        assert (result.returncode, "not in a tmux pane" in result.stderr, calls(tmux_calls)) == (1, True, [])

    def should_refuse_an_unknown_command_with_its_usage(self, wt_status, tmux_calls):
        result = wt_status("done")

        assert (result.returncode, "unknown command: done" in result.stderr, calls(tmux_calls)) == (2, True, [])


class TestRun:
    def should_report_busy_while_the_command_runs_then_idle(self, wt_status, tmux_calls):
        result = wt_status("run", "Deploying", "--", "sh", "-c", f'echo ran >> "{tmux_calls}"')

        assert (result.returncode, calls(tmux_calls)) == (0, [
            f"set-option -p -t {PANE} @wt_label Deploying", f"set-option -p -t {PANE} @wt_state busy", "ran",
            f"set-option -p -t {PANE} @wt_label Deploying", f"set-option -p -t {PANE} @wt_state idle",
        ])

    def should_name_the_exit_code_of_a_failed_command_and_exit_with_it(self, wt_status, tmux_calls):
        result = wt_status("run", "Deploying", "--", "sh", "-c", "exit 3")

        assert (result.returncode, calls(tmux_calls)[-2:]) == (3, [
            f"set-option -p -t {PANE} @wt_label Deploying failed (3)", f"set-option -p -t {PANE} @wt_state idle",
        ])

    def should_run_the_command_without_reporting_outside_a_tmux_pane(self, wt_status, tmux_calls):
        result = wt_status("run", "Deploying", "--", "sh", "-c", "echo out; exit 4", pane=None)

        assert (result.returncode, result.stdout, calls(tmux_calls)) == (4, "out\n", [])

    def should_refuse_run_without_a_command(self, wt_status, tmux_calls):
        result = wt_status("run", "Deploying", "--")

        assert (result.returncode, "run needs a command" in result.stderr, calls(tmux_calls)) == (2, True, [])


def should_list_its_commands_for_completion_in_its_help(wt_status):
    result = wt_status("--help")

    assert (result.returncode, "{busy,idle,waiting,clear,run}" in result.stdout) == (0, True)
