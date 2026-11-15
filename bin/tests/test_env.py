import os
import shutil
import subprocess

import pytest

from bin.tests.conftest import BIN_DIR, requires_tool

ENV_FILE = BIN_DIR.parent / "bash" / ".bashrc.d" / "00-env.sh"
ZSHRC = BIN_DIR.parent / "zsh" / ".zshrc"
BASH_PROFILE = BIN_DIR.parent / "bash" / ".bash_profile"
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


class TestStartupFilePath:
    @pytest.fixture
    def home(self, tmp_path):
        directory = tmp_path / "home"
        directory.mkdir()
        (directory / ".bashrc").write_text(f'. "{ENV_FILE}"\n')
        return directory

    def path_entries(self, command, home):
        env = {"PATH": "/usr/bin:/bin", "HOME": str(home)}
        result = subprocess.run(command, capture_output=True, text=True, env=env)
        return result.stdout.split()

    @requires_tool("zsh")
    def should_keep_the_custom_bin_dir_ahead_of_the_yarn_dirs_in_zsh(self, home):
        command = [shutil.which("zsh"), "-f", "-c",
                   f'source "{ZSHRC}" 2>/dev/null; print -rl -- ${{(s.:.)PATH}}']

        entries = self.path_entries(command, home)

        assert entries.index(f"{home}/dotfiles/bin") < entries.index(f"{home}/.yarn/bin")

    def should_add_the_docker_bin_dir_only_once_in_a_login_shell(self, home):
        command = [shutil.which("bash"), "--norc", "-c",
                   f'. "{BASH_PROFILE}"; echo "$PATH" | tr : "\\n"']

        entries = self.path_entries(command, home)

        assert [entry for entry in entries if entry.endswith("/.docker/bin")] == [f"{home}/.docker/bin"]


class TestCmakeMakeProgram:
    @pytest.fixture
    def tools(self, tmp_path):
        directory = tmp_path / "tools"
        directory.mkdir()
        return directory

    @pytest.fixture
    def which_calls(self, tools, tmp_path):
        log = tmp_path / "which.log"
        which = tools / "which"
        which.write_text(f'#!/bin/bash\necho "$*" >> "{log}"\n')
        which.chmod(0o755)
        return log

    @pytest.fixture
    def exported(self, shell, tools, tmp_path):
        script = (f'OSTYPE=darwin24\n. "{ENV_FILE}"\n'
                  '/bin/sh -c \'printf "%s" "${CMAKE_MAKE_PROGRAM-unset}"\'')

        def _exported():
            result = subprocess.run([*shell, "-c", script], capture_output=True, text=True,
                                    env={"HOME": str(tmp_path), "PATH": str(tools)})
            assert result.returncode == 0, result.stderr
            return result.stdout
        return _exported

    def should_stay_unset_without_ninja(self, exported):
        assert exported() == "unset"

    def should_export_the_path_of_ninja(self, exported, tools):
        ninja = tools / "ninja"
        ninja.write_text("#!/bin/bash\n")
        ninja.chmod(0o755)

        assert exported() == str(ninja)

    def should_not_start_which(self, exported, which_calls, tools):
        (tools / "ninja").write_text("#!/bin/bash\n")
        (tools / "ninja").chmod(0o755)

        exported()

        assert not which_calls.exists()
