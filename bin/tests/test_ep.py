import os
import stat
import subprocess

import pytest

from bin.tests.conftest import BIN_DIR, requires_tool

FUNCTIONS = BIN_DIR.parent / "bash" / ".bashrc.d" / "20-functions.sh"
SHELLS = {"bash": ["bash", "-c"], "zsh": ["zsh", "-f", "-c"]}
SAMPLE = """#!/bin/bash
alias ll='ls -l'
export BAR=1
baz() {
    :
}
function g {
    :
}
function h() {
    :
}
"""


@pytest.fixture(params=["bash", pytest.param("zsh", marks=requires_tool("zsh"))])
def shell(request):
    return request.param


@pytest.fixture
def ep(shell, tmp_path):
    home = tmp_path / "home"
    rc_dir = home / ".bashrc.d"
    rc_dir.mkdir(parents=True)
    (home / ".bashrc").write_text("")
    (rc_dir / "20-sample.sh").write_text(SAMPLE)
    edits = tmp_path / "edits.log"
    editor = tmp_path / "editor"
    editor.write_text(f'#!/bin/bash\necho "$*" >> "{edits}"\n')
    editor.chmod(editor.stat().st_mode | stat.S_IEXEC)

    def _ep(*args):
        script = f'source "{FUNCTIONS}"; ep {" ".join(args)}'
        env = {**os.environ, "HOME": str(home), "EDITOR": str(editor)}
        result = subprocess.run([*SHELLS[shell], script], capture_output=True, text=True, env=env)
        _ep.edits = edits.read_text().splitlines() if edits.exists() else []
        _ep.sample = rc_dir / "20-sample.sh"
        return result
    return _ep


def line_of(definition):
    return SAMPLE.splitlines().index(definition) + 1


class TestEpJump:
    @pytest.mark.parametrize("name, definition", [
        ("ll", "alias ll='ls -l'"),
        ("BAR", "export BAR=1"),
        ("baz", "baz() {"),
        ("g", "function g {"),
        ("h", "function h() {"),
    ])
    def should_open_the_editor_at_the_definition(self, ep, name, definition):
        result = ep(name)

        assert result.returncode == 0, result.stderr
        assert ep.edits == [f"+{line_of(definition)} {ep.sample}"]

    def should_not_match_a_name_that_only_starts_like_another_function(self, ep):
        result = ep("gg")

        assert result.returncode == 1
        assert ep.edits == []
        assert "no definition for: gg" in result.stderr


class TestEpList:
    @requires_tool("less")
    def should_list_every_kind_of_definition(self, ep):
        result = ep("-l")

        listed = result.stdout.splitlines()
        assert [line for line in listed if line and not line.startswith("\x1b") and "===" not in line] == [
            "alias ll='ls -l'", "export BAR=1", "baz() {", "function g {", "function h() {"]
