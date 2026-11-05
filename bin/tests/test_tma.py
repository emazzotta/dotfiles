import os
import pty
import subprocess

import pytest

from bin.tests.conftest import BIN_DIR


def tmux_mock(tmp_path, *sessions):
    listing = "".join(f"{name}\\n" for name in sessions)
    return f"""
case "$1" in
    list-sessions)
        [ -n "{listing}" ] || {{ echo "no server running" >&2; exit 1; }}
        printf "{listing}" ;;
    attach|switch-client) echo "$*" >> "{tmp_path / 'attached'}" ;;
esac
"""


def gum_mock(tmp_path, choice):
    return f'cat > "{tmp_path / "offered"}"; echo "{choice}"'


def attached(tmp_path):
    return (tmp_path / "attached").read_text().strip()


def run_on_tty(tmp_path, mock_bins):
    mock_dir = tmp_path / "mock_bin"
    mock_dir.mkdir()
    for name, body in mock_bins.items():
        mock = mock_dir / name
        mock.write_text(f"#!/bin/bash\n{body}\n")
        mock.chmod(0o755)
    env = {**os.environ, "PATH": f"{mock_dir}:/usr/bin:/bin"}
    leader, follower = pty.openpty()
    try:
        return subprocess.run([str(BIN_DIR / "tma")], stdin=follower,
                              capture_output=True, text=True, env=env)
    finally:
        os.close(leader)
        os.close(follower)


@pytest.fixture(autouse=True)
def outside_tmux(monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)


class TestTma:
    def should_attach_to_the_session_named_in_the_argument(self, run_cli, tmp_path):
        mocks = {"tmux": tmux_mock(tmp_path, "0", "dj")}

        result = run_cli("tma", ["dj"], mock_bins=mocks, isolate_path=True, stdin="")

        assert result.returncode == 0
        assert attached(tmp_path) == "attach -t dj"

    def should_switch_to_the_named_session_when_already_inside_tmux(self, run_cli, tmp_path):
        mocks = {"tmux": tmux_mock(tmp_path, "main", "probe")}

        result = run_cli("tma", ["probe"], env_extra={"TMUX": "/tmp/tmux-1000/default,1,0"},
                         mock_bins=mocks, isolate_path=True, stdin="")

        assert result.returncode == 0
        assert attached(tmp_path) == "switch-client -t probe"

    def should_attach_to_the_only_open_session_without_asking(self, run_cli, tmp_path):
        mocks = {"tmux": tmux_mock(tmp_path, "work"), "gum": gum_mock(tmp_path, "unused")}

        result = run_cli("tma", mock_bins=mocks, isolate_path=True, stdin="")

        assert result.returncode == 0
        assert attached(tmp_path) == "attach -t work"
        assert not (tmp_path / "offered").exists()

    def should_fail_when_no_session_is_open(self, run_cli, tmp_path):
        result = run_cli("tma", mock_bins={"tmux": tmux_mock(tmp_path)},
                         isolate_path=True, stdin="")

        assert result.returncode == 1
        assert "no tmux sessions open" in result.stderr
        assert not (tmp_path / "attached").exists()

    def should_let_the_user_pick_with_gum_when_several_sessions_are_open(self, tmp_path):
        mocks = {"tmux": tmux_mock(tmp_path, "0", "dj set"), "gum": gum_mock(tmp_path, "dj set")}

        result = run_on_tty(tmp_path, mocks)

        assert result.returncode == 0
        assert (tmp_path / "offered").read_text() == "0\ndj set\n"
        assert attached(tmp_path) == "attach -t dj set"

    def should_not_attach_when_the_gum_pick_is_cancelled(self, tmp_path):
        mocks = {"tmux": tmux_mock(tmp_path, "0", "dj"), "gum": "exit 130"}

        result = run_on_tty(tmp_path, mocks)

        assert result.returncode == 130
        assert not (tmp_path / "attached").exists()

    def should_list_the_sessions_instead_of_prompting_without_a_terminal(self, run_cli, tmp_path):
        mocks = {"tmux": tmux_mock(tmp_path, "0", "dj"), "gum": gum_mock(tmp_path, "dj")}

        result = run_cli("tma", mock_bins=mocks, isolate_path=True, stdin="")

        assert result.returncode == 1
        assert "  0\n  dj\n" in result.stderr
        assert not (tmp_path / "offered").exists()
        assert not (tmp_path / "attached").exists()

    def should_print_usage_for_help(self, run_cli, tmp_path):
        mocks = {"tmux": tmux_mock(tmp_path, "0")}

        result = run_cli("tma", ["--help"], mock_bins=mocks, isolate_path=True)

        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert not (tmp_path / "attached").exists()
