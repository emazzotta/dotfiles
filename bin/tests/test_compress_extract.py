import pytest


class TestCompress:
    def test_no_args_exits_nonzero(self, run_bash):
        result = run_bash("compress")
        assert result.returncode != 0


class TestExtract:
    def test_no_args_exits_nonzero(self, run_bash):
        result = run_bash("extract")
        combined = result.stdout + result.stderr
        assert result.returncode != 0 or "usage" in combined.lower()

    def test_unsupported_extension(self, run_bash, tmp_path):
        fake_file = tmp_path / "test.xyz123"
        fake_file.write_text("not an archive")
        result = run_bash("extract", [str(fake_file)])
        assert "don't know" in result.stderr.lower()

    def test_nonexistent_file(self, run_bash):
        result = run_bash("extract", ["/tmp/nonexistent_archive_12345.tar.gz"])
        combined = result.stdout + result.stderr
        assert result.returncode != 0 or "error" in combined.lower() or "not found" in combined.lower()
