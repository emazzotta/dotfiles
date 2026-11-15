import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).parent.parent
REPO_URL = "https://github.com/samuelgursky/davinci-resolve-mcp.git"
ANSI_COLOUR = re.compile(r"\x1b\[[0-9;]*m")
LOG_PREFIX = re.compile(r"\[[^\]]+\] (?:(WARN|ERROR): )?(.*)")
LEVELS = {"WARN": "warn", "ERROR": "error", None: "log"}
DEPENDS_ON_THE_HOST = ("Resolve scripting API not found", "  scripting API:", "  fusionscript.so:")
GIT_STAND_IN = r'''
printf '%s\n' "$*" >> "${GIT_CALLS}"
case "$*" in
    *" pull "*) exit "${STAND_IN_PULL_STATUS}" ;;
    "clone "*) exit "${STAND_IN_CLONE_STATUS}" ;;
esac
'''
PYTHON_STAND_IN = r'''
if [ "$1" = --version ]; then
    echo "Python ${STAND_IN_PYTHON_VERSION}"
    exit 0
fi
printf '%s\n' "$*" >> "${PYTHON_CALLS}"
if [ "${STAND_IN_INSTALL_STATUS}" = 0 ]; then
    mkdir -p "${RESOLVE_MCP_HOME}/venv/bin"
    : > "${RESOLVE_MCP_HOME}/venv/bin/python"
    chmod u+x "${RESOLVE_MCP_HOME}/venv/bin/python"
fi
exit "${STAND_IN_INSTALL_STATUS}"
'''
READINESS = [("plain", ""), ("log", "Setup complete. Readiness:")]
INSTRUCTIONS = [
    ("plain", ""), ("plain", "Once Resolve Studio is installed:"),
    ("plain", "  1. Resolve > Preferences > System > General > External scripting using = Local"),
    ("plain", "  2. Start Resolve and open a project"),
]


def messages(stream):
    """Each line as (level, text), without the timestamp and without the lines that depend on the host."""
    lines = []
    for line in ANSI_COLOUR.sub("", stream).splitlines():
        logged = LOG_PREFIX.fullmatch(line)
        lines.append((LEVELS[logged[1]], logged[2]) if logged else ("plain", line))
    return [line for line in lines if not line[1].startswith(DEPENDS_ON_THE_HOST)]


class Machine:
    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.home = tmp_path / "home"
        self.config_dir = tmp_path / "opencode-config"
        self.repo = tmp_path / "checkout"
        self.token = self.config_dir / "davinci-resolve-mcp" / "mcp-token"
        self.launcher = self.home / ".local" / "bin" / "resolve-mcp-serve"
        self.python = tmp_path / "mock_bin" / "python3.12"
        self.git_calls = tmp_path / "git-calls"
        self.python_calls = tmp_path / "python-calls"
        self.home.mkdir()
        self.config_dir.mkdir()

    def environment(self, **overrides):
        environment = {
            "HOME": str(self.home), "OPENCODE_CONFIG_DIR": str(self.config_dir), "RESOLVE_MCP_HOME": str(self.repo),
            "GIT_CALLS": str(self.git_calls), "PYTHON_CALLS": str(self.python_calls), "STAND_IN_PULL_STATUS": "0",
            "STAND_IN_CLONE_STATUS": "0", "STAND_IN_INSTALL_STATUS": "0", "STAND_IN_PYTHON_VERSION": "3.12.4"}
        environment.update({key: str(value) for key, value in overrides.items()})
        return environment

    def calls(self, file):
        return file.read_text().splitlines() if file.exists() else []

    def existing_checkout(self):
        (self.repo / ".git").mkdir(parents=True)


@pytest.fixture
def machine(tmp_path):
    return Machine(tmp_path)


@pytest.fixture
def setup(run_bash, machine):
    def _setup(*args, **overrides):
        return run_bash("resolve-mcp-setup", list(args), mock_bins={"git": GIT_STAND_IN, "python3.12": PYTHON_STAND_IN},
                        env_extra=machine.environment(**overrides))
    return _setup


def run_with_only(machine, tools, **overrides):
    tool_dir = machine.tmp_path / "only_these_tools"
    tool_dir.mkdir()
    for name, body in tools.items():
        (tool_dir / name).write_text(f"#!/bin/bash\n{body}\n")
        (tool_dir / name).chmod(0o755)
    for name in ("date", "dirname"):
        (tool_dir / name).symlink_to(shutil.which(name))
    environment = {**os.environ, **machine.environment(**overrides), "PATH": str(tool_dir)}
    return subprocess.run([shutil.which("bash"), str(BIN_DIR / "resolve-mcp-setup")], capture_output=True, text=True,
                          env=environment)


def fresh_setup_output(machine):
    return [
        ("log", f"Generating bearer token at {machine.token}"),
        ("log", f"Writing {machine.launcher}"),
        ("log", f"Cloning into {machine.repo}"),
        ("log", f"Building venv with Python 3.12.4 ({machine.python})"),
        *READINESS, ("plain", "  venv:            built"), ("plain", "  token:           present"),
        *INSTRUCTIONS, ("plain", f"  3. Run: {machine.launcher}")]


class TestHelp:
    @pytest.mark.parametrize("flag", ["-h", "--help"])
    def should_print_the_usage_on_stdout_and_touch_nothing(self, setup, machine, flag):
        result = setup(flag)

        assert result.returncode == 0
        assert result.stdout.startswith("Usage: resolve-mcp-setup [--help]\n")
        assert {level for level, _ in messages(result.stdout)} == {"plain"}
        assert result.stderr == ""
        assert not machine.git_calls.exists()
        assert not machine.token.exists()


class TestSetup:
    def should_prepare_a_fresh_machine_and_report_what_is_ready(self, setup, machine):
        result = setup()

        assert result.returncode == 0, result.stderr
        assert messages(result.stdout) == fresh_setup_output(machine)
        assert result.stderr == ""

    def should_clone_the_repository_and_build_the_venv_with_the_python_it_found(self, setup, machine):
        setup()

        assert machine.calls(machine.git_calls) == [f"clone --depth 1 {REPO_URL} {machine.repo}"]
        assert machine.calls(machine.python_calls) == [
            f"{machine.repo}/install.py --clients manual --python {machine.python}"]

    def should_write_a_private_token_and_an_executable_launcher(self, setup, machine):
        setup()

        assert re.fullmatch(r"[0-9a-f]{64}\n", machine.token.read_text())
        assert machine.token.stat().st_mode & 0o777 == 0o600
        assert machine.token.parent.stat().st_mode & 0o777 == 0o700
        assert machine.launcher.stat().st_mode & 0o100
        assert machine.launcher.read_text().startswith("#!/bin/bash\n")
        assert f'readonly TOKEN_FILE="{machine.token}"' in machine.launcher.read_text()

    def should_reuse_the_token_and_update_the_checkout_on_a_rerun(self, setup, machine):
        machine.token.parent.mkdir()
        machine.token.write_text("kept\n")
        machine.existing_checkout()

        result = setup()

        assert result.returncode == 0, result.stderr
        assert messages(result.stdout) == [
            ("log", f"Reusing existing token at {machine.token}"),
            ("log", f"Writing {machine.launcher}"),
            ("log", f"Updating {machine.repo}"),
            ("log", f"Building venv with Python 3.12.4 ({machine.python})"),
            *READINESS, ("plain", "  venv:            built"), ("plain", "  token:           present"),
            *INSTRUCTIONS, ("plain", f"  3. Run: {machine.launcher}")]
        assert machine.token.read_text() == "kept\n"
        assert machine.calls(machine.git_calls) == [f"-C {machine.repo} pull --ff-only"]

    def should_warn_and_go_on_when_the_pull_fails(self, setup, machine):
        machine.existing_checkout()

        result = setup(STAND_IN_PULL_STATUS=1)

        assert result.returncode == 0, result.stderr
        assert messages(result.stdout)[2:4] == [("log", f"Updating {machine.repo}"),
                                                ("warn", "pull failed - leaving the checkout as is")]
        assert result.stderr == ""

    def should_warn_and_go_on_when_the_clone_fails(self, setup, machine):
        result = setup(STAND_IN_CLONE_STATUS=1)

        assert result.returncode == 0, result.stderr
        assert messages(result.stdout)[2:5] == [
            ("log", f"Cloning into {machine.repo}"), ("warn", "repository sync failed - re-run once resolved"),
            ("log", f"Building venv with Python 3.12.4 ({machine.python})")]
        assert result.stderr == ""

    def should_warn_and_report_a_missing_venv_when_the_build_fails(self, setup, machine):
        result = setup(STAND_IN_INSTALL_STATUS=1)

        assert result.returncode == 0, result.stderr
        assert messages(result.stdout)[3:] == [
            ("log", f"Building venv with Python 3.12.4 ({machine.python})"),
            ("warn", "venv build failed - re-run once resolved"),
            *READINESS, ("plain", "  venv:            MISSING"), ("plain", "  token:           present"),
            *INSTRUCTIONS, ("plain", f"  3. Run: {machine.launcher}")]
        assert result.stderr == ""

    def should_warn_twice_about_a_python_outside_the_range_upstream_calls_low_risk(self, setup, machine):
        result = setup(STAND_IN_PYTHON_VERSION="3.13.1")

        assert result.returncode == 0, result.stderr
        assert messages(result.stdout)[3:6] == [
            ("log", f"Building venv with Python 3.13.1 ({machine.python})"),
            ("warn", "Python 3.13.1 is outside upstream's 3.10-3.12 low-risk range."),
            ("warn", "If Resolve tools later return no connection, install python@3.12 and re-run.")]
        assert result.stderr == ""


class TestFailure:
    def should_stop_on_stderr_when_git_is_missing(self, machine):
        result = run_with_only(machine, {})

        assert result.returncode == 1
        assert messages(result.stderr) == [("error", "git not found - install Xcode Command Line Tools")]
        assert result.stdout == ""

    def should_stop_on_stderr_when_the_container_config_directory_is_missing(self, setup, machine):
        result = setup(OPENCODE_CONFIG_DIR=machine.tmp_path / "nowhere")

        assert result.returncode == 1
        assert messages(result.stderr) == [(
            "error", f"container config dir not found at {machine.tmp_path / 'nowhere'} - the token would be written "
                     "where the container cannot read it; set OPENCODE_CONFIG_DIR")]
        assert result.stdout == ""
        assert not machine.launcher.exists()

    def should_stop_on_stderr_before_writing_anything_when_no_python_is_found(self, machine):
        result = run_with_only(machine, {"git": GIT_STAND_IN})

        assert result.returncode == 1
        assert messages(result.stderr) == [("error", "no python3 found")]
        assert messages(result.stdout) == []
        assert not machine.token.exists()
        assert not machine.launcher.exists()
