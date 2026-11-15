import os
import shlex
import shutil
import stat
import subprocess

import pytest

from bin.tests.conftest import BIN_DIR, requires_tool

ALIAS_DIR = BIN_DIR.parent / "bash" / ".bashrc.d"
SHELLS = {"bash": ["bash", "-c"], "zsh": ["zsh", "-f", "-c"]}
SYSTEM_PATH = "/usr/bin:/bin"


@pytest.fixture(params=["bash", pytest.param("zsh", marks=requires_tool("zsh"))])
def shell(request):
    return request.param


@pytest.fixture
def mock_bin(tmp_path):
    directory = tmp_path / "mock_bin"
    directory.mkdir()
    return directory


def add_mock(directory, name, body):
    mock = directory / name
    mock.write_text(f"#!/bin/bash\n{body}\n")
    mock.chmod(mock.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def run_alias(shell, tmp_path):
    def _run(alias_file, commands, cwd=None, env_extra=None, path=None):
        prelude = "shopt -s expand_aliases\n" if shell == "bash" else ""
        script = f'{prelude}source "{ALIAS_DIR / alias_file}"\neval {shlex.quote(commands)}\n'
        env = {**os.environ, **(env_extra or {})}
        if path is not None:
            env["PATH"] = path
        return subprocess.run([shutil.which(SHELLS[shell][0]), *SHELLS[shell][1:], script],
                              capture_output=True, text=True, cwd=cwd or tmp_path, env=env)
    return _run


def relative_files(root):
    return sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())


class TestAliasNames:
    def should_not_shadow_a_script_of_bin(self, tmp_path):
        names = set()
        for alias_file in sorted(ALIAS_DIR.glob("*aliases*.sh")):
            result = subprocess.run(["bash", "-c", f'source "{alias_file}"; alias'],
                                    capture_output=True, text=True, cwd=tmp_path)
            names.update(line.split("=")[0].removeprefix("alias ") for line in
                         result.stdout.splitlines() if line.startswith("alias "))

        shadowed = sorted(name for name in names if (BIN_DIR / name).exists())

        assert shadowed == []


class TestRmpy:
    @pytest.fixture
    def tree(self, tmp_path):
        root = tmp_path / "tree"
        for name in ("keep.py", "pkg/module.pyc", "pkg/__pycache__/module.cpython-312.pyc",
                     "pkg/__pycache__/notes.txt", ".cache/blob", "target/classes/App.class",
                     ".coverage", "pkg/keep.txt"):
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text("x")
        return root

    def should_remove_the_python_and_build_leftovers_whatever_they_hold(self, run_alias, tree):
        result = run_alias("16-aliases-cleanup.sh", "rmpy", cwd=tree)

        assert result.returncode == 0, result.stderr
        assert relative_files(tree) == ["keep.py", "pkg/keep.txt"]


class TestRmwin:
    @pytest.fixture
    def tree(self, tmp_path):
        root = tmp_path / "tree"
        for name in ("Thumbs.db", "docs/desktop.ini", "docs/report.txt", "$RECYCLE.BIN/entry",
                     "Desktop.txt"):
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text("x")
        return root

    def should_remove_the_windows_leftovers_including_the_recycle_bin(self, run_alias, tree):
        result = run_alias("16-aliases-cleanup.sh", "rmwin", cwd=tree)

        assert result.returncode == 0, result.stderr
        assert relative_files(tree) == ["Desktop.txt", "docs/report.txt"]

    def should_leave_other_files_with_the_bin_suffix_alone(self, run_alias, tree):
        (tree / "archive.BIN").write_text("x")

        run_alias("16-aliases-cleanup.sh", "rmwin", cwd=tree)

        assert (tree / "archive.BIN").exists()


class TestAutoc:
    @pytest.fixture
    def project(self, tmp_path, mock_bin):
        add_mock(mock_bin, "clang-format", f'printf "%s\\n" "$@" > "{tmp_path / "clang-format.log"}"')
        root = tmp_path / "project"
        (root / "src").mkdir(parents=True)
        for name in ("src/main.c", "src/util.CPP", "src/api.h", "src/notes.txt"):
            (root / name).write_text("x")
        return root

    @pytest.fixture
    def autoc(self, run_alias, mock_bin, tmp_path):
        def _autoc(project):
            result = run_alias("18-aliases-misc.sh", "autoc", cwd=project,
                               env_extra={"PATH": f"{mock_bin}:{os.environ['PATH']}"})
            assert result.returncode == 0, result.stderr
            lines = (tmp_path / "clang-format.log").read_text().splitlines()
            return sorted(line for line in lines if line.startswith("./"))
        return _autoc

    def should_format_every_c_family_source_below_a_directory_without_such_files(
            self, autoc, project):
        formatted = autoc(project)

        assert formatted == ["./src/api.h", "./src/main.c", "./src/util.CPP"]

    def should_not_let_the_shell_expand_the_patterns_against_the_current_directory(
            self, autoc, project):
        (project / "top.h").write_text("x")

        formatted = autoc(project)

        assert formatted == ["./src/api.h", "./src/main.c", "./src/util.CPP", "./top.h"]


class TestAip:
    def should_enter_the_workspace_directory_of_the_opencode_checkout(self, run_alias, tmp_path):
        checkout = tmp_path / "opencode"
        workspace = checkout / "opencode" / "workspace"
        workspace.mkdir(parents=True)

        result = run_alias("10-aliases-nav.sh", "aip\npwd", env_extra={"OPENCODE_PATH": str(checkout)})

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(workspace.resolve())


class TestPing:
    def should_use_prettyping_when_it_is_installed(self, run_alias, mock_bin, tmp_path):
        add_mock(mock_bin, "prettyping", 'echo "pretty $*"')

        result = run_alias("17-aliases-ssh-net.sh", "ping example.test",
                           path=f"{mock_bin}:{SYSTEM_PATH}")

        assert result.stdout.strip() == "pretty --nolegend example.test"

    def should_leave_ping_alone_without_prettyping(self, run_alias, mock_bin):
        add_mock(mock_bin, "ping", 'echo "plain $*"')

        result = run_alias("17-aliases-ssh-net.sh", "ping example.test",
                           path=f"{mock_bin}:{SYSTEM_PATH}")

        assert result.stdout.strip() == "plain example.test"
