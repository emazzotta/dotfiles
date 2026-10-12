import subprocess

import pytest

from bin.tests.conftest import BIN_DIR

PRETTYPRINT = BIN_DIR / "prettyprint"
COLORS = ["BOLD", "DIM", "RED", "GREEN", "YELLOW", "BLUE", "MAGENTA", "CYAN", "WHITE", "TURQUOISE", "RESET"]
STATUS_LINES = ["info", "success", "error", "substep_info", "substep_success", "substep_error"]
MESSAGES = ["Converting 3 files", "", "Zürich · ● 100% done", "back\\slash $HOME", "trailing newline\n"]


@pytest.fixture
def scriptlog(load_script):
    return load_script("scriptlog.py")


def run_prettyprint(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", f'source "$1"; shift; {script}', "bash", str(PRETTYPRINT), *args],
        capture_output=True, encoding="utf-8",
    )


@pytest.mark.parametrize("name", COLORS)
def should_define_the_same_colors_as_bash_prettyprint(scriptlog, name):
    assert getattr(scriptlog, name) == run_prettyprint('printf %s "${!1}"', name).stdout


@pytest.mark.parametrize("message", MESSAGES)
@pytest.mark.parametrize("function", STATUS_LINES)
def should_print_the_same_bytes_on_the_same_stream_as_bash_prettyprint(scriptlog, capsys, function, message):
    expected = run_prettyprint('"$@"', function, message)

    getattr(scriptlog, function)(message)

    assert capsys.readouterr() == (expected.stdout, expected.stderr)


def should_build_the_same_hyperlink_as_bash_prettyprint(scriptlog):
    url, text = "https://example.com/a?b=1", "example"

    assert scriptlog.hyperlink(url, text) == run_prettyprint('hyperlink "$@"', url, text).stdout


def should_print_a_warning_as_a_yellow_bullet_on_stdout(scriptlog, capsys):
    scriptlog.warn("Skipping x")

    assert capsys.readouterr() == ("\033[1m\033[33m●\033[0m Skipping x\n", "")
