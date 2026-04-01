import os
import subprocess
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).parent.parent


class TestRmBuildFiles:
    def _run_in_dir(self, work_dir):
        env = os.environ.copy()
        env["PATH"] = str(BIN_DIR) + ":" + env.get("PATH", "")
        return subprocess.run(
            ["bash", str(BIN_DIR / "rm_build_files")],
            capture_output=True, text=True, cwd=str(work_dir), env=env,
        )

    def test_removes_pycache(self, tmp_path):
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "module.pyc").touch()
        result = self._run_in_dir(tmp_path)
        assert result.returncode == 0
        assert not cache.exists()

    def test_removes_ds_store(self, tmp_path):
        ds = tmp_path / ".DS_Store"
        ds.touch()
        self._run_in_dir(tmp_path)
        assert not ds.exists()

    def test_removes_target_dir(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        (target / "classes").mkdir()
        self._run_in_dir(tmp_path)
        assert not target.exists()

    def test_removes_pyc_files(self, tmp_path):
        (tmp_path / "module.pyc").touch()
        self._run_in_dir(tmp_path)
        assert not (tmp_path / "module.pyc").exists()


class TestReplaceActionPluginVersion:
    def test_replaces_version_logic(self, tmp_path):
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        wf = workflows / "ci.yml"
        wf.write_text("uses: actions/checkout@v3\nuses: actions/setup-java@v3\n")

        script = tmp_path / "test_replace.sh"
        script.write_text(f"""#!/bin/bash
set -euo pipefail
PLUGIN_NAME="actions/checkout"
TARGET_VERSION="v4"
ESCAPED_PLUGIN_NAME=$(echo "$PLUGIN_NAME" | sed 's/\\//\\\\\\//g')
file="{wf}"
sed "s/${{ESCAPED_PLUGIN_NAME}}@[a-zA-Z0-9_.-]*/${{ESCAPED_PLUGIN_NAME}}@${{TARGET_VERSION}}/g" "$file" > "$file.tmp" && mv "$file.tmp" "$file"
""")
        result = subprocess.run(["bash", str(script)], capture_output=True, text=True)
        assert result.returncode == 0
        content = wf.read_text()
        assert "actions/checkout@v4" in content
        assert "actions/setup-java@v3" in content

    def test_no_args_shows_usage(self, run_bash):
        result = run_bash("replace_action_plugin_version")
        assert result.returncode != 0
        assert "Usage" in result.stdout + result.stderr


class TestKillgrep:
    def test_no_args_shows_usage(self, run_bash):
        result = run_bash("killgrep")
        assert "Usage" in result.stdout or "usage" in result.stdout

    def test_cancel_does_not_kill(self, run_bash):
        result = run_bash("killgrep", ["bash"], stdin="n\n")
        assert "cancelled" in result.stdout.lower() or "canceled" in result.stdout.lower()
