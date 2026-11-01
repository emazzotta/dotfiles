import re
from pathlib import Path

import pytest

MACOS_MOCKS = {
    "uname": "echo Darwin",
    "sysctl": '[ "$2" = hw.ncpu ] && echo 4',
    "ps": "printf '%%CPU\\n 50.0\\n 30.0\\n 20.0\\n'",
}


def should_report_the_process_cpu_sum_per_core_on_macos(run_cli):
    result = run_cli("cpu", mock_bins=MACOS_MOCKS, isolate_path=True)

    assert result.returncode == 0
    assert result.stdout == "25.00%\n"


@pytest.mark.skipif(not Path("/proc/stat").exists(), reason="needs /proc/stat")
def should_report_a_sampled_percentage_as_a_single_line_on_linux(run_cli):
    result = run_cli("cpu", mock_bins={"uname": "echo Linux"}, isolate_path=True)

    assert result.returncode == 0
    assert re.fullmatch(r"\d+\.\d{2}%\n", result.stdout)


def should_fail_on_an_unsupported_os(run_cli):
    result = run_cli("cpu", mock_bins={"uname": "echo SunOS"}, isolate_path=True)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "unsupported OS: SunOS" in result.stderr
