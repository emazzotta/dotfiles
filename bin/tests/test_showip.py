import pytest


class TestShowip:
    def test_no_args_shows_help(self, run_bash):
        result = run_bash("showip")
        assert "Usage" in result.stdout or "usage" in result.stdout
        assert result.returncode == 0

    def test_help_flag(self, run_bash):
        result = run_bash("showip", ["-h"])
        assert "internal" in result.stdout.lower()
        assert "external" in result.stdout.lower()

    def test_internal_ip(self, run_bash):
        result = run_bash("showip", ["-i"])
        if result.returncode == 0:
            output = result.stdout.strip()
            assert "." in output

    def test_unknown_flag_exits(self, run_bash):
        result = run_bash("showip", ["--invalid"])
        assert result.returncode != 0
        assert "unrecognized" in result.stderr.lower()
