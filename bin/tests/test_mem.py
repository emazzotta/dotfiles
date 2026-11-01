import re
from pathlib import Path

import pytest

VM_STAT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                                3953.
Pages active:                            262144.
Pages inactive:                          131072.
Pages speculative:                         1234.
Pages wired down:                        100000.
Pages reactivated:                       345678.
File-backed pages:                        98765.
"""

MACOS_MOCKS = {
    "uname": "echo Darwin",
    "vm_stat": f"cat <<'EOF'\n{VM_STAT}EOF",
    "sysctl": 'case "$2" in vm.pagesize) echo 16384 ;; hw.memsize) echo 17179869184 ;; esac',
}


def should_report_active_plus_inactive_pages_over_total_on_macos(run_cli):
    result = run_cli("mem", mock_bins=MACOS_MOCKS, isolate_path=True)

    assert result.returncode == 0
    assert result.stdout == "6.00G/16.00G\n"


@pytest.mark.skipif(not Path("/proc/meminfo").exists(), reason="needs /proc/meminfo")
def should_report_used_over_total_as_a_single_line_on_linux(run_cli):
    result = run_cli("mem", mock_bins={"uname": "echo Linux"}, isolate_path=True)

    assert result.returncode == 0
    assert re.fullmatch(r"\d+\.\d{2}G/\d+\.\d{2}G\n", result.stdout)


def should_fail_on_an_unsupported_os(run_cli):
    result = run_cli("mem", mock_bins={"uname": "echo SunOS"}, isolate_path=True)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "unsupported OS: SunOS" in result.stderr
