import re
from pathlib import Path

import pytest

EXTRACT = Path(__file__).parent.parent / "extract"
UNZIP_MOCK = 'echo "$*" > "$UNZIP_LOG"'
PICKER_PICKS_FIRST = "sed -n 1p"


class TestCompress:
    def test_no_args_exits_nonzero(self, run_bash):
        result = run_bash("compress")
        assert result.returncode != 0


@pytest.fixture
def extract(run_bash, tmp_path):
    work = tmp_path / "work"
    work.mkdir()

    def _run(args=None):
        return run_bash(
            "extract",
            args or [],
            env_extra={"UNZIP_LOG": str(tmp_path / "unzip.log")},
            mock_bins={"unzip": UNZIP_MOCK, "picker": PICKER_PICKS_FIRST},
            isolate_path=True,
            cwd=work,
        )
    _run.work = work
    _run.unzip_log = tmp_path / "unzip.log"
    return _run


class TestExtract:
    def test_should_extract_the_only_archive_when_given_no_argument(self, extract):
        (extract.work / "release.zip").touch()

        result = extract()

        assert result.returncode == 0
        assert extract.unzip_log.read_text().strip() == "release.zip"

    def test_should_pick_among_several_archives_when_given_no_argument(self, extract):
        (extract.work / "alpha.zip").touch()
        (extract.work / "bravo.tar.gz").touch()

        result = extract()

        assert result.returncode == 0
        assert extract.unzip_log.read_text().strip() == "alpha.zip"

    def test_should_fail_when_the_current_directory_holds_no_archive(self, extract):
        (extract.work / "notes.txt").touch()

        result = extract()

        assert result.returncode == 1
        assert not extract.unzip_log.exists()

    def test_should_still_accept_a_named_archive(self, extract):
        (extract.work / "alpha.zip").touch()
        (extract.work / "bravo.zip").touch()

        result = extract(["bravo.zip"])

        assert result.returncode == 0
        assert extract.unzip_log.read_text().strip() == "bravo.zip"

    def test_should_report_an_unsupported_extension(self, extract):
        (extract.work / "test.xyz123").touch()

        result = extract(["test.xyz123"])

        assert "don't know" in result.stderr.lower()

    def test_should_report_a_nonexistent_file(self, extract):
        result = extract(["/tmp/nonexistent_archive_12345.tar.gz"])

        assert result.returncode != 0
        assert "not a valid file" in result.stderr

    @pytest.mark.parametrize("flag", ["-h", "--help"])
    def test_should_show_usage_for_the_help_flag(self, extract, flag):
        result = extract([flag])

        assert result.returncode == 0
        assert "usage:" in result.stdout.lower()

    def test_should_offer_every_dispatched_extension_for_discovery(self):
        source = EXTRACT.read_text()
        declared = set(
            re.search(r"ARCHIVE_EXTENSIONS=\(([^)]*)\)", source).group(1).split()
        )
        dispatched = set(re.findall(r"^\s+\*\.([^)]+)\)", source, re.MULTILINE))

        assert declared == dispatched
