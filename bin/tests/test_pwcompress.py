import pytest

SEVEN_ZIP_MOCK = 'printf "%s\\n" "$@" > "$SEVEN_ZIP_LOG"'
ARCHIVE_ARGUMENT = 4


@pytest.fixture
def pwcompress(run_cli, tmp_path):
    work = tmp_path / "work"
    for name in ("BigFolder", "x", "sub", "src/a", "src/b", "deep/a"):
        (work / name).mkdir(parents=True)
    for name in ("report.pdf", "file1.txt", "file2.txt", "sub/report.pdf", "src/a/f", "src/b/f"):
        (work / name).write_text("data")
    log = tmp_path / "7z.log"

    def _run(*args, cwd=work):
        result = run_cli(
            "pwcompress", ["-p", "secret", *args],
            env_extra={"SEVEN_ZIP_LOG": str(log)},
            mock_bins={"7z": SEVEN_ZIP_MOCK},
            cwd=cwd,
        )
        assert result.returncode == 0, result.stderr
        return log.read_text().splitlines()
    _run.work = work
    return _run


class TestArchiveName:
    @pytest.mark.parametrize("inputs,archive", [
        (["report.pdf"], "report.7z"),
        (["BigFolder/"], "BigFolder.7z"),
        (["BigFolder"], "BigFolder.7z"),
        (["./x"], "x.7z"),
        (["sub/report.pdf"], "sub/report.7z"),
    ])
    def test_should_name_a_single_input_after_itself(self, pwcompress, inputs, archive):
        call = pwcompress(*inputs)

        assert call[ARCHIVE_ARGUMENT] == archive
        assert call[ARCHIVE_ARGUMENT + 1:] == inputs

    def test_should_keep_the_archive_beside_an_input_in_a_parent_directory(self, pwcompress):
        call = pwcompress("../src/a", cwd=pwcompress.work / "deep")

        assert call[ARCHIVE_ARGUMENT] == "../src/a.7z"

    def test_should_name_the_archive_after_the_directory_when_the_input_is_dot(self, pwcompress):
        call = pwcompress(".")

        assert call[ARCHIVE_ARGUMENT] == f"{pwcompress.work.resolve()}.7z"

    def test_should_name_a_multi_file_archive_after_the_working_directory(self, pwcompress):
        call = pwcompress("file1.txt", "file2.txt")

        assert call[ARCHIVE_ARGUMENT] == "work.7z"

    def test_should_name_a_multi_file_archive_after_the_parent_directory(self, pwcompress):
        call = pwcompress("src/a", "src/b")

        assert call[ARCHIVE_ARGUMENT] == "src.7z"
