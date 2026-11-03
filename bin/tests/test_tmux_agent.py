import os
import plistlib

import pytest

from bin.tests.conftest import BIN_DIR

LABEL = "com.emazzotta.tmux"
SERVICE = f"gui/{os.getuid()}/{LABEL}"
AGENT_PID = "777"
FOREIGN_PID = "4242"


@pytest.fixture
def agent(run_bash, tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    calls = tmp_path / "calls"
    plist = tmp_path / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    flag = tmp_path / "Library" / "Caches" / f"{LABEL}.takeover"
    mocks = {
        "uname": "echo Darwin",
        "plutil": "true",
        "sleep": f'echo "sleep $*" >> "{calls}"',
        "launchctl": (
            f'echo "launchctl $*" >> "{calls}"\n'
            'case "$1" in\n'
            f'  print) [ -e "{state}/loaded" ] || exit 113; printf "\\tpid = {AGENT_PID}\\n" ;;\n'
            f'  bootstrap) touch "{state}/loaded" ;;\n'
            "esac"
        ),
        "tmux": (
            f'echo "tmux $*" >> "{calls}"\n'
            f'[ "$1" = -D ] && echo "$SHELL" >| "{state}/shell"\n'
            'if [ "$1 $2" = "-N display-message" ]; then\n'
            f'  n=$(cat "{state}/answers")\n'
            '  [ "$n" -gt 0 ] || exit 1\n'
            f'  echo $((n - 1)) >| "{state}/answers"\n'
            f'  cat "{state}/server_pid"\n'
            "fi"
        ),
    }

    def _run(command, answers=0, server_pid=FOREIGN_PID, loaded=False, stdin=None, shell="/bin/zsh"):
        (state / "answers").write_text(str(answers))
        (state / "server_pid").write_text(server_pid)
        if loaded:
            (state / "loaded").touch()
        result = run_bash("tmux-agent", [command], env_extra={"HOME": str(tmp_path), "SHELL": shell},
                          mock_bins=mocks, stdin=stdin, isolate_path=True)
        logged = calls.read_text().splitlines() if calls.exists() else []
        calls.unlink(missing_ok=True)
        return result, logged

    _run.plist = plist
    _run.flag = flag
    _run.state = state
    return _run


def tmux_calls(logged):
    return [line for line in logged if line.startswith(("tmux", "sleep"))
            and "display-message" not in line]


class TestServe:
    def should_start_its_server_at_once_when_no_other_one_runs(self, agent):
        result, logged = agent("serve")

        assert result.returncode == 0
        assert tmux_calls(logged) == ["tmux -D"]

    def should_wait_while_another_server_answers(self, agent):
        _, logged = agent("serve", answers=3)

        assert tmux_calls(logged) == ["sleep 5", "sleep 5", "tmux -D"]

    def should_end_the_running_server_first_on_a_takeover(self, agent):
        agent.flag.parent.mkdir(parents=True)
        agent.flag.touch()

        _, logged = agent("serve", answers=2)

        assert tmux_calls(logged) == ["tmux kill-server", "sleep 0.2", "tmux -D"]
        assert not agent.flag.exists()

    def should_hand_tmux_a_shell_when_launchd_sets_none(self, agent):
        agent("serve", shell="")

        assert (agent.state / "shell").read_text().strip() == "/bin/zsh"


class TestInstall:
    def should_run_serve_through_zsh_from_a_launch_agent(self, agent):
        result, logged = agent("install")

        assert result.returncode == 0
        spec = plistlib.loads(agent.plist.read_bytes())
        assert spec["Label"] == LABEL
        assert spec["ProgramArguments"] == ["/bin/zsh", "-c", 'exec "$0" serve',
                                            str((BIN_DIR / "tmux-agent").resolve())]
        assert (spec["RunAtLoad"], spec["KeepAlive"], spec["ProcessType"]) == (True, True, "Interactive")
        assert f"launchctl bootstrap gui/{os.getuid()} {agent.plist}" in logged

    def should_leave_a_loaded_agent_with_the_same_plist_alone(self, agent):
        agent("install")

        result, logged = agent("install")

        assert result.returncode == 0
        assert [line for line in logged if "bootstrap" in line or "bootout" in line] == []

    def should_refuse_to_replace_a_loaded_agent_running_another_plist(self, agent):
        agent.plist.parent.mkdir(parents=True)
        agent.plist.write_text("older")

        result, logged = agent("install", loaded=True)

        assert result.returncode == 1
        assert "uninstall first" in result.stderr
        assert agent.plist.read_text() == "older"


class TestStatus:
    @pytest.mark.parametrize(("server_pid", "verdict"), [(AGENT_PID, f"is {LABEL}'s"),
                                                          (FOREIGN_PID, "takeover ends it")])
    def should_tell_the_agents_server_from_another_one(self, agent, server_pid, verdict):
        result, _ = agent("status", answers=1, server_pid=server_pid, loaded=True)

        assert verdict in result.stdout


class TestTakeover:
    def should_end_a_foreign_server_only_after_a_yes(self, agent):
        result, logged = agent("takeover", answers=1, loaded=True, stdin="y\n")

        assert result.returncode == 0
        assert agent.flag.exists()
        assert f"launchctl kickstart -k {SERVICE}" in logged

    def should_keep_the_server_without_a_yes(self, agent):
        result, logged = agent("takeover", answers=1, loaded=True, stdin="n\n")

        assert result.returncode == 1
        assert not agent.flag.exists()
        assert [line for line in logged if "kickstart" in line] == []

    def should_leave_its_own_server_running(self, agent):
        result, logged = agent("takeover", answers=1, server_pid=AGENT_PID, loaded=True)

        assert result.returncode == 0
        assert [line for line in logged if "kickstart" in line] == []


class TestUninstall:
    @pytest.mark.parametrize(("answer", "removed"), [("y\n", True), ("n\n", False)])
    def should_end_its_own_server_only_after_a_yes(self, agent, answer, removed):
        agent("install")

        _, logged = agent("uninstall", answers=1, server_pid=AGENT_PID, stdin=answer)

        assert (f"launchctl bootout {SERVICE}" in logged) is removed
        assert agent.plist.exists() is not removed

    def should_not_ask_while_the_agent_still_waits_for_another_server(self, agent):
        agent("install")

        result, logged = agent("uninstall", answers=1)

        assert result.returncode == 0
        assert f"launchctl bootout {SERVICE}" in logged


def should_refuse_to_run_off_macos(run_bash):
    result = run_bash("tmux-agent", ["status"], mock_bins={"uname": "echo Linux"}, isolate_path=True)

    assert result.returncode == 1
    assert "macOS only" in result.stderr
