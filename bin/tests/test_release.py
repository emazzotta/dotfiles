import subprocess

import pytest


class TestExtractVersionFromPom:
    @staticmethod
    def _run_grep_version(pom_path, tmp_path):
        script = tmp_path / "test.sh"
        script.write_text(f"""#!/bin/bash
pom_file="{pom_path}"
if [ ! -f "$pom_file" ]; then exit 1; fi
version=$(grep -m 1 "<version>" "$pom_file" | sed 's/.*<version>\\(.*\\)<\\/version>.*/\\1/' | tr -d '[:space:]')
if [ -z "$version" ]; then exit 1; fi
echo "$version"
""")
        return subprocess.run(["bash", str(script)], capture_output=True, text=True)

    def test_extracts_version(self, tmp_path):
        pom = tmp_path / "pom.xml"
        pom.write_text("""<?xml version="1.0"?>
<project>
    <modelVersion>4.0.0</modelVersion>
    <version>1.2.3-SNAPSHOT</version>
</project>""")
        result = self._run_grep_version(pom, tmp_path)
        assert result.stdout.strip() == "1.2.3-SNAPSHOT"

    def test_missing_pom_fails(self, tmp_path):
        result = self._run_grep_version(tmp_path / "nonexistent.xml", tmp_path)
        assert result.returncode == 1

    def test_first_version_tag_wins(self, tmp_path):
        pom = tmp_path / "pom.xml"
        pom.write_text("""<?xml version="1.0"?>
<project>
    <parent><version>9.9.9</version></parent>
    <version>1.0.0</version>
</project>""")
        result = self._run_grep_version(pom, tmp_path)
        assert result.stdout.strip() == "9.9.9"


class TestStripSnapshotSuffix:
    @pytest.mark.parametrize("version,expected", [
        ("1.2.3-SNAPSHOT", "1.2.3"),
        ("1.2.3", "1.2.3"),
        ("2.0.0-SNAPSHOT", "2.0.0"),
        ("10.20.30-SNAPSHOT", "10.20.30"),
    ])
    def test_strips_snapshot(self, version, expected, tmp_path):
        script = tmp_path / "test.sh"
        script.write_text(f'#!/bin/bash\necho "{version}" | sed \'s/-SNAPSHOT$//\'\n')
        result = subprocess.run(["bash", str(script)], capture_output=True, text=True)
        assert result.stdout.strip() == expected


class TestValidateVersionFormat:
    @pytest.mark.parametrize("version,valid", [
        ("1.2.3", True),
        ("1.2.3.4", True),
        ("1.2", False),
        ("abc", False),
        ("1.2.3-SNAPSHOT", False),
        ("0.0.1", True),
        ("999.999.999", True),
    ])
    def test_version_validation(self, version, valid, tmp_path):
        script = tmp_path / "test.sh"
        script.write_text(f"""#!/bin/bash
version="{version}"
if [[ ! "$version" =~ ^[0-9]+\\.[0-9]+\\.[0-9]+(\\.[0-9]+)?$ ]]; then exit 1; fi
exit 0
""")
        result = subprocess.run(["bash", str(script)], capture_output=True, text=True)
        assert (result.returncode == 0) == valid


class TestReleaseScript:
    def test_no_args_shows_error(self, run_bash):
        result = run_bash("release")
        assert result.returncode != 0
        assert "error" in result.stderr.lower()
