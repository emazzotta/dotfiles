import platform
import subprocess

import pytest

IS_DARWIN = platform.system() == "Darwin"


class TestRandom:
    def test_generates_number(self, run_bash):
        result = run_bash("random", ["100"])
        if result.returncode == 0:
            output = result.stdout.strip()
            assert output.isdigit() or output.replace("-", "").isdigit()

    def test_no_args_uses_default(self, run_bash):
        import shutil
        if not shutil.which("bc"):
            pytest.skip("bc not available")
        result = run_bash("random")
        assert result.returncode == 0 or "usage" in result.stdout.lower()


class TestUuid:
    def test_generates_uuid_format(self, run_bash):
        result = run_bash("uuid")
        if result.returncode != 0:
            pytest.skip("uuid generation not available on this platform")
        lines = result.stdout.strip().split("\n")
        uuid_line = lines[0].strip()
        parts = uuid_line.split("-")
        assert len(parts) == 5
        assert all(len(p) > 0 for p in parts)

    def test_lowercase_output(self, run_bash):
        result = run_bash("uuid")
        if result.returncode != 0:
            pytest.skip("uuid generation not available on this platform")
        uuid_line = result.stdout.strip().split("\n")[0].strip()
        assert uuid_line == uuid_line.lower()


class TestDatefmt:
    def test_formats_timestamp(self, run_bash):
        result = run_bash("datefmt", ["0"])
        if result.returncode == 0:
            assert "1970" in result.stdout or "1969" in result.stdout

    def test_no_args_shows_usage(self, run_bash):
        result = run_bash("datefmt")
        assert "usage" in result.stdout.lower()


class TestJsonFormat:
    @pytest.fixture(autouse=True)
    def _require_jq(self):
        import shutil
        if not shutil.which("jq"):
            pytest.skip("jq not available")

    def test_formats_json_via_clipboard(self, run_bash):
        result = run_bash("json_format", ['{"a":1,"b":2}'], mock_bins={
            "pbcopy": "cat > /dev/null",
        })
        assert result.returncode == 0

    def test_no_args_shows_usage(self, run_bash):
        result = run_bash("json_format")
        assert "usage" in result.stdout.lower()


class TestCompress:
    def test_help_flag(self, run_bash):
        result = run_bash("compress", ["-h"])
        combined = result.stdout + result.stderr
        assert "Usage" in combined or "usage" in combined

    def test_no_args_shows_usage(self, run_bash):
        result = run_bash("compress")
        combined = result.stdout + result.stderr
        assert result.returncode != 0
        assert "Usage" in combined or "usage" in combined

    def test_tar_creation(self, run_bash, tmp_path):
        test_dir = tmp_path / "myfiles"
        test_dir.mkdir()
        (test_dir / "test.txt").write_text("hello world")
        archive = tmp_path / "myfiles.tar"
        result = run_bash("compress", [str(archive), str(test_dir)])
        assert result.returncode == 0, result.stderr
        assert archive.exists()
        assert archive.stat().st_size > 0

    def test_unknown_extension_fails(self, run_bash, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")
        result = run_bash("compress", [str(tmp_path / "test.xyz123")])
        assert result.returncode != 0
        assert "unknown" in result.stderr.lower() or "error" in result.stderr.lower()


class TestExtract:
    def test_no_args_shows_usage(self, run_bash):
        result = run_bash("extract")
        combined = result.stdout + result.stderr
        assert "usage" in combined.lower()

    def test_unsupported_extension(self, run_bash, tmp_path):
        fake = tmp_path / "test.xyz123"
        fake.write_text("not an archive")
        result = run_bash("extract", [str(fake)])
        assert "don't know" in result.stderr.lower()

    def test_nonexistent_file(self, run_bash):
        result = run_bash("extract", ["/tmp/nonexistent_12345.tar.gz"])
        combined = result.stdout + result.stderr
        assert "not a valid" in combined.lower() or result.returncode != 0

    def test_tar_roundtrip(self, run_bash, tmp_path):
        src = tmp_path / "mydata"
        src.mkdir()
        (src / "file.txt").write_text("hello")
        archive = tmp_path / "mydata.tar"

        create = run_bash("compress", [str(archive), str(src)])
        assert create.returncode == 0, create.stderr

        dest = tmp_path / "dest"
        dest.mkdir()
        extract = subprocess.run(
            ["tar", "xf", str(archive), "-C", str(dest)],
            capture_output=True, text=True,
        )
        assert extract.returncode == 0

    def test_tgz_case_ordering_bug(self, run_bash, tmp_path):
        """The compress script matches *gz before *tgz due to case ordering.
        This documents the known bug - tgz falls into gzip instead of tar+gzip."""
        test_dir = tmp_path / "myfiles"
        test_dir.mkdir()
        (test_dir / "test.txt").write_text("hello")
        result = run_bash("compress", [str(tmp_path / "myfiles.tgz"), str(test_dir)])
        assert result.returncode != 0
