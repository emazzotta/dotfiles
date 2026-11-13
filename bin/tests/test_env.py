import os
import shutil
import subprocess

import pytest

from bin.tests.conftest import BIN_DIR, requires_tool

ENV_FILE = BIN_DIR.parent / "bash" / ".bashrc.d" / "00-env.sh"
SHELLS = {"bash": ["bash", "--norc"], "zsh": ["zsh", "-f"]}
PANE = "%171"
UNRELATED_PROCESS_SECONDS = "60"


@pytest.fixture(params=["bash", pytest.param("zsh", marks=requires_tool("zsh"))])
def shell(request):
    name, *flags = SHELLS[request.param]
    return [shutil.which(name), *flags]


@pytest.fixture
def unrelated_server():
    process = subprocess.Popen(["sleep", UNRELATED_PROCESS_SECONDS])
    yield process.pid
    process.kill()
    process.wait()


@pytest.fixture
def startup(tmp_path):
    script = tmp_path / "startup.sh"
    script.write_text(f'. "{ENV_FILE}"\necho "${{TMUX-unset}} ${{TMUX_PANE-unset}}"\n')
    return script


def tmux_vars_after(command, tmp_path, **env_extra):
    env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE")}
    env.update(HOME=str(tmp_path), **env_extra)
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


def tmux_value(server_pid):
    return f"/tmp/tmux-501/default,{server_pid},12"


class TestEnv:
    def should_drop_the_tmux_vars_a_shell_inherits_from_outside_tmux(self, shell, startup, tmp_path,
                                                                       unrelated_server):
        tmux_vars = tmux_vars_after([*shell, str(startup)], tmp_path,
                                    TMUX=tmux_value(unrelated_server), TMUX_PANE=PANE)

        assert tmux_vars == ["unset", "unset"]

    def should_keep_the_tmux_vars_in_a_shell_that_descends_from_the_tmux_server(self, shell, startup,
                                                                                  tmp_path):
        server = tmp_path / "server.sh"
        server.write_text(f'export TMUX="{tmux_value("$$")}" TMUX_PANE={PANE}\n'
                          'bash -c \'"$@"; exit $?\' _ "$@"\n'
                          'exit $?\n')

        tmux_vars = tmux_vars_after(["bash", str(server), *shell, str(startup)], tmp_path)

        assert tmux_vars[1] == PANE
        assert tmux_vars[0].endswith(",12")

    def should_keep_the_tmux_vars_when_the_parent_processes_cannot_be_read(self, shell, startup, tmp_path,
                                                                            unrelated_server):
        no_ps = tmp_path / "no_ps"
        no_ps.mkdir()
        (no_ps / "tr").symlink_to(shutil.which("tr"))

        tmux_vars = tmux_vars_after([*shell, str(startup)], tmp_path, PATH=str(no_ps),
                                    TMUX=tmux_value(unrelated_server), TMUX_PANE=PANE)

        assert tmux_vars == [tmux_value(unrelated_server), PANE]
