import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

BIN_DIR = Path(__file__).parent.parent
IS_DARWIN = platform.system() == "Darwin"


@pytest.fixture
def load_script():
    def _load(name: str, mock_modules: dict | None = None) -> ModuleType:
        if mock_modules:
            for mod_name, mock in mock_modules.items():
                sys.modules[mod_name] = mock

        script_path = BIN_DIR / name
        sys.path.insert(0, str(BIN_DIR))
        module = ModuleType(name)
        module.__file__ = str(script_path)
        with open(script_path) as f:
            exec(f.read(), module.__dict__)
        return module
    return _load


def _essential_bin_dirs() -> list[str]:
    dirs = ["/usr/bin", "/bin"]
    if IS_DARWIN:
        dirs.extend(["/usr/local/bin", "/opt/homebrew/bin"])
    dirs.append("/usr/sbin")
    return [d for d in dirs if Path(d).is_dir()]


@pytest.fixture
def run_bash(tmp_path):
    def _run(script_name, args=None, env_extra=None, mock_bins=None,
             stdin=None, isolate_path=False):
        script = BIN_DIR / script_name
        mock_dir = tmp_path / "mock_bin"
        mock_dir.mkdir(exist_ok=True)

        if mock_bins:
            for name, body in mock_bins.items():
                mock = mock_dir / name
                mock.write_text(f"#!/bin/bash\n{body}\n")
                mock.chmod(mock.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        if isolate_path:
            essential = ":".join(_essential_bin_dirs())
            env["PATH"] = f"{mock_dir}:{BIN_DIR}:{essential}"
        else:
            env["PATH"] = f"{mock_dir}:{BIN_DIR}:{env.get('PATH', '')}"

        if env_extra:
            env.update(env_extra)

        return subprocess.run(
            ["bash", str(script)] + (args or []),
            capture_output=True, text=True, env=env, input=stdin,
        )
    return _run


@pytest.fixture
def create_mock_bin(tmp_path):
    def _create(name, body):
        mock = tmp_path / "bin" / name
        mock.parent.mkdir(exist_ok=True)
        mock.write_text(f"#!/bin/bash\n{body}\n")
        mock.chmod(mock.stat().st_mode | stat.S_IEXEC)
        return mock
    return _create


@pytest.fixture
def run_script(tmp_path):
    def _run(script_path, args=None, env_extra=None):
        env = os.environ.copy()
        env["PATH"] = f"{tmp_path / 'bin'}:{BIN_DIR}:{env['PATH']}"
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            ["bash", str(script_path)] + (args or []),
            capture_output=True, text=True, env=env,
        )
    return _run


def requires_tool(tool_name):
    return pytest.mark.skipif(
        shutil.which(tool_name) is None,
        reason=f"{tool_name} not available",
    )


skip_on_darwin = pytest.mark.skipif(IS_DARWIN, reason="Linux-only test")
skip_on_linux = pytest.mark.skipif(not IS_DARWIN, reason="macOS-only test")
