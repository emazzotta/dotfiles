import pytest

LEORUN_PS1 = r"\\Mac\Home\Projects\private\dotfiles\bin\leorun.ps1"


@pytest.fixture
def calls(tmp_path):
    return tmp_path / "calls"


@pytest.fixture
def recorded(calls):
    def _recorded():
        return calls.read_text().splitlines() if calls.exists() else []
    return _recorded


@pytest.fixture
def wleorun(run_cli, calls):
    def _wleorun(*args, branch="LEO-1-focus"):
        answer = f"echo {branch}" if branch else 'echo "Error: no branch" >&2; exit 1'
        mocks = {"leorun": f'echo "leorun $*" >> "{calls}"\n{answer}',
                 "vmup": f'echo vmup >> "{calls}"',
                 "ssh": f'printf "ssh %s\\n" "$*" >> "{calls}"'}
        return run_cli("wleorun", list(args), mock_bins=mocks)
    return _wleorun


def ssh_running(ps_args):
    return f'ssh wlocal pwsh -Command "{LEORUN_PS1}{ps_args}"'


class TestWleorun:
    def should_run_leorun_ps1_on_the_vm_for_the_branch_leorun_resolves(self, wleorun, recorded):
        result = wleorun("-f", "focus")

        assert result.returncode == 0, result.stderr
        assert recorded() == ["leorun --print-branch focus", "vmup",
                              ssh_running(" -f 'LEO-1-focus'")]

    def should_keep_the_install_projects_apart_from_the_branch(self, wleorun, recorded):
        result = wleorun("-i", "updater[feature]", "focus", "--quick")

        assert result.returncode == 0, result.stderr
        assert recorded()[0] == "leorun --print-branch focus"
        assert recorded()[-1] == ssh_running(" -i 'updater[feature]' --quick 'LEO-1-focus'")

    def should_run_the_branch_leorun_would_run_without_a_target(self, wleorun, recorded):
        result = wleorun("--fast", branch="main")

        assert result.returncode == 0, result.stderr
        assert recorded()[0] == "leorun --print-branch"
        assert recorded()[-1] == ssh_running(" --fast 'main'")

    def should_leave_the_vm_alone_when_the_branch_does_not_resolve(self, wleorun, recorded):
        result = wleorun("typo", branch=None)

        assert result.returncode == 1
        assert recorded() == ["leorun --print-branch typo"]

    def should_reject_a_second_target_before_touching_the_vm(self, wleorun, recorded):
        result = wleorun("focus", "main")

        assert result.returncode == 1
        assert recorded() == []
