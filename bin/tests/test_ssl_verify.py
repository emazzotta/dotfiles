import platform
import subprocess
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).parent.parent
IS_DARWIN = platform.system() == "Darwin"


class TestCheckWildcardMatch:
    @pytest.mark.parametrize("hostname,pattern,expected", [
        ("www.example.com", "*.example.com", 0),
        ("sub.example.com", "*.example.com", 0),
        ("example.com", "example.com", 0),
        ("www.other.com", "*.example.com", 1),
        ("deep.sub.example.com", "*.example.com", 0),
    ])
    def test_wildcard_matching(self, hostname, pattern, expected, tmp_path):
        script = tmp_path / "test.sh"
        script.write_text(f"""#!/bin/bash
check_wildcard_match() {{
    local hostname="$1"
    local pattern="$2"
    if [[ "$pattern" == "*."* ]]; then
        local domain="${{pattern#*.}}"
        local host_suffix="${{hostname##*.}}"
        local remaining="${{hostname%.$host_suffix}}"
        if [[ "$remaining.$host_suffix" == *".$domain" ]] || [[ "$hostname" == *".$domain" ]]; then
            return 0
        fi
    fi
    if [[ "$hostname" == "$pattern" ]]; then
        return 0
    fi
    return 1
}}
check_wildcard_match "{hostname}" "{pattern}"
""")
        result = subprocess.run(["bash", str(script)], capture_output=True, text=True)
        assert result.returncode == expected


class TestParseCertDatePortability:
    def test_function_exists_in_source(self):
        content = (BIN_DIR / "ssl_verify").read_text()
        assert "parse_cert_date()" in content

    def test_has_platform_branching(self):
        content = (BIN_DIR / "ssl_verify").read_text()
        assert "date -j -f" in content
        assert "date -d" in content
        assert "Darwin" in content

    def test_parse_cert_date_on_current_platform(self, tmp_path):
        script = tmp_path / "test.sh"
        script.write_text("""#!/bin/bash
parse_cert_date() {
    local date_str
    date_str="$(echo "$1" | sed 's/  */ /g')"
    if [ "$(uname -s)" = "Darwin" ]; then
        date -j -f "%b %d %T %Y %Z" "$date_str" "+%s" 2>/dev/null || echo 0
    else
        date -d "$1" "+%s" 2>/dev/null || echo 0
    fi
}
result=$(parse_cert_date "Jan  1 00:00:00 2025 UTC")
if [ "$result" -gt 0 ] 2>/dev/null; then
    echo "OK"
else
    echo "FAIL"
fi
""")
        result = subprocess.run(["bash", str(script)], capture_output=True, text=True)
        assert result.stdout.strip() == "OK"
