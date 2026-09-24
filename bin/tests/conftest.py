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
        sys.modules[name] = module
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


def marker_mocks(tmp_path: Path, *names: str) -> dict[str, str]:
    return {name: f'echo {name} >> "{tmp_path / "calls"}"' for name in names}


def _run_in_mocked_env(command, tmp_path, env_extra, mock_bins, stdin, isolate_path, cwd=None):
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
        command, capture_output=True, text=True, env=env, input=stdin,
        cwd=str(cwd) if cwd else None,
    )


@pytest.fixture
def run_bash(tmp_path):
    def _run(script_name, args=None, env_extra=None, mock_bins=None,
             stdin=None, isolate_path=False, cwd=None):
        command = ["bash", str(BIN_DIR / script_name)] + (args or [])
        return _run_in_mocked_env(command, tmp_path, env_extra, mock_bins,
                                  stdin, isolate_path, cwd)
    return _run


@pytest.fixture
def run_cli(tmp_path):
    """Run a bin/ script through its own shebang, so Python scripts work too."""
    def _run(script_name, args=None, env_extra=None, mock_bins=None,
             stdin=None, isolate_path=False, cwd=None):
        command = [str(BIN_DIR / script_name)] + (args or [])
        return _run_in_mocked_env(command, tmp_path, env_extra, mock_bins,
                                  stdin, isolate_path, cwd)
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


WORKTREES = Path(".claude") / "worktrees"


@pytest.fixture
def gitconfig(tmp_path):
    config = tmp_path / "gitconfig"
    config.write_text("[user]\n\tname = Test\n\temail = test@example.com\n"
                      "[init]\n\tdefaultBranch = main\n"
                      "[safe]\n\tdirectory = *\n")
    return config


@pytest.fixture
def git_env(gitconfig):
    return {"GIT_CONFIG_GLOBAL": str(gitconfig), "GIT_CONFIG_NOSYSTEM": "1"}


@pytest.fixture
def git(git_env):
    def _git(cwd, *args):
        result = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                                env={**os.environ, **git_env})
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()
    return _git


@pytest.fixture
def project(tmp_path, git):
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", str(origin))
    project = tmp_path / "project"
    git(tmp_path, "clone", str(origin), str(project))
    git(project, "commit", "--allow-empty", "-m", "Initial commit")
    git(project, "push", "origin", "main")
    git(project, "remote", "set-head", "origin", "main")
    return project


@pytest.fixture
def wt(run_cli, git_env, project):
    def _wt(*args, cwd=None):
        return run_cli("git-wt", list(args), env_extra=git_env, cwd=cwd or project)
    return _wt


@pytest.fixture
def added(wt):
    def _added(branch, *start):
        result = wt("add", branch, *start)
        assert result.returncode == 0, result.stderr
        return Path(result.stdout.strip())
    return _added


def move_to_other_mount(project, tmp_path):
    other_side = tmp_path / "other-mount"
    shutil.move(str(project), str(other_side))
    return other_side


def branches(git, repo):
    return git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split("\n")


def commit_file(git, checkout, name, content, message="Add file"):
    (checkout / name).write_text(content)
    git(checkout, "add", name)
    git(checkout, "commit", "-m", message)


def ship_by_squash_merge(git, tmp_path, checkout, branch):
    commit_file(git, checkout, f"{branch}.txt", "done")
    git(checkout, "push", "-u", "origin", branch)
    server = tmp_path / f"server-{branch}"
    git(tmp_path, "clone", str(tmp_path / "origin.git"), str(server))
    git(server, "merge", "--squash", f"origin/{branch}")
    git(server, "commit", "-m", f"Squash-merge {branch}")
    git(server, "push", "origin", "main", f":{branch}")
