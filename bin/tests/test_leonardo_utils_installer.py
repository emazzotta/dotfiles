import os
import re

import pytest

CURL_WRITES_URL = """\
while [ $# -gt 0 ]; do
    case "$1" in
        -o) out=$2; shift 2 ;;
        -*) shift ;;
        *) url=$1; shift ;;
    esac
done
echo "$url" > "$out"
"""


@pytest.fixture
def install(run_bash, tmp_path):
    target = tmp_path / "install"

    def _run(*args):
        return run_bash(
            "leonardo_utils_installer", [str(target), *args],
            mock_bins={"curl": CURL_WRITES_URL}, isolate_path=True,
        )
    _run.target = target
    return _run


def _listed_in_usage(run_bash) -> set[str]:
    usage = run_bash("leonardo_utils_installer", ["--help"]).stdout
    section = usage.split("Scripts installed:")[1].split("Examples:")[0]
    return set(re.findall(r"^\s+- (\S+)$", section, re.MULTILINE))


class TestInstalledScripts:
    def test_should_ship_envify_with_the_python_helper_it_calls(self, install):
        result = install()

        assert result.returncode == 0, result.stderr
        for name in ("envify", "envify.py"):
            script = install.target / name
            assert script.read_text().strip().endswith(f"/bin/{name}")
            assert os.access(script, os.X_OK)

    def test_should_list_in_the_usage_exactly_the_scripts_it_installs(self, install, run_bash):
        install()

        installed = {path.name for path in install.target.iterdir()}

        assert installed == _listed_in_usage(run_bash)
