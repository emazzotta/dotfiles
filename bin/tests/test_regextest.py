import pytest


class TestRegextest:
    def test_matching_pattern(self, run_bash):
        result = run_bash("regextest", ["^[0-9]+\\.[0-9]+\\.[0-9]+$"])
        assert result.returncode == 0
        assert "FOUND" in result.stdout
        assert "NOT FOUND" in result.stdout

    def test_ip_like_pattern(self, run_bash):
        result = run_bash("regextest", ["^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$"])
        lines = result.stdout.strip().split("\n")
        found_lines = [l for l in lines if l.startswith("FOUND")]
        assert any("1.1.1.1" in l for l in found_lines)

    def test_no_args_shows_usage(self, run_bash):
        result = run_bash("regextest")
        assert "usage" in result.stdout.lower()

    def test_branch_pattern(self, run_bash):
        result = run_bash("regextest", ["^(feature|bugfix)/"])
        lines = result.stdout.strip().split("\n")
        found_lines = [l for l in lines if l.startswith("FOUND")]
        assert any("feature/bla" in l for l in found_lines)
        assert any("bugfix/bla" in l for l in found_lines)
