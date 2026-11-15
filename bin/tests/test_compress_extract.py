import bz2
import gzip
import re
import tarfile
from pathlib import Path

import pytest

EXTRACT = Path(__file__).parent.parent / "extract"
UNZIP_MOCK = 'echo "$*" > "$UNZIP_LOG"'
PICKER_PICKS_FIRST = "sed -n 1p"
RAR_MOCK = 'echo "$*" > "$RAR_LOG"'
NOTES = "remember the milk\n"


@pytest.fixture
def compress(run_cli, tmp_path):
    work = tmp_path / "work"
    (work / "project").mkdir(parents=True)
    (work / "project" / "notes.txt").write_text(NOTES)
    (work / "notes.txt").write_text(NOTES)

    def _run(*args):
        return run_cli(
            "compress", list(args),
            env_extra={"RAR_LOG": str(tmp_path / "rar.log")},
            mock_bins={"rar": RAR_MOCK},
            cwd=work,
        )
    _run.work = work
    _run.rar_log = tmp_path / "rar.log"
    return _run


class TestCompress:
    def test_no_args_exits_nonzero(self, run_bash):
        result = run_bash("compress")
        assert result.returncode != 0

    @pytest.mark.parametrize("flag", ["-h", "--help"])
    def test_should_show_usage_for_the_help_flag(self, compress, flag):
        result = compress(flag)

        assert result.returncode == 0
        assert "Usage:" in result.stdout

    @pytest.mark.parametrize("archive", ["project.tar.gz", "project.tgz", "project.tar.bz2", "project.tbz2", "project.tar"])
    def test_should_pack_the_folder_named_like_the_archive_into_a_tarball(self, compress, archive):
        result = compress(archive)

        assert result.returncode == 0, result.stderr
        with tarfile.open(compress.work / archive) as tarball:
            assert "project/notes.txt" in tarball.getnames()

    @pytest.mark.parametrize("archive,opener", [("notes.txt.gz", gzip.open), ("notes.txt.bz2", bz2.open)])
    def test_should_compress_a_named_file_and_keep_the_original(self, compress, archive, opener):
        result = compress(archive, "notes.txt")

        assert result.returncode == 0, result.stderr
        with opener(compress.work / archive, "rt") as compressed:
            assert compressed.read() == NOTES
        assert (compress.work / "notes.txt").read_text() == NOTES

    def test_should_add_the_named_files_to_a_rar_archive(self, compress):
        result = compress("backup.rar", "notes.txt", "project")

        assert result.returncode == 0, result.stderr
        assert compress.rar_log.read_text().strip() == "a backup.rar notes.txt project"

    def test_should_fail_when_the_archiver_fails(self, compress):
        result = compress("missing.tar.gz")

        assert result.returncode != 0
        assert "Archive creation failed" in result.stderr

    def test_should_report_an_unknown_extension(self, compress):
        result = compress("project.xyz")

        assert result.returncode == 1
        assert "Unknown extension" in result.stderr


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

    def test_should_unpack_a_deb_with_ar(self, run_bash, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        (work / "tool.deb").touch()
        calls = tmp_path / "calls.log"
        record = 'echo "$(basename "$0") $*" >> "$CALLS_LOG"'

        result = run_bash("extract", ["tool.deb"], env_extra={"CALLS_LOG": str(calls)},
                          mock_bins={"ar": record, "w": record}, isolate_path=True, cwd=work)

        assert result.returncode == 0, result.stderr
        assert calls.read_text().splitlines() == ["ar x tool.deb"]

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
