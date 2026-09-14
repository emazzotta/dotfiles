import pytest

SEVEN_Z_MOCK = 'printf "%s\\n" "$2" > "$SEVEN_Z_LOG"'
ENVIFY_MOCK = 'export PASSWORD_ZIPS=test-password'
PICKER_PICKS_FIRST = 'cat > "$PICKER_LOG"\nsed -n 1p "$PICKER_LOG"'
PICKER_CANCELLED = 'cat > "$PICKER_LOG"\nexit 130'


@pytest.fixture
def workspace(tmp_path):
    work = tmp_path / "work"
    desk = tmp_path / "desk"
    work.mkdir()
    desk.mkdir()
    return work, desk


@pytest.fixture
def uncompress(run_bash, tmp_path, workspace):
    work, desk = workspace

    def _run(args=None, picker=PICKER_PICKS_FIRST):
        return run_bash(
            "pwuncompress",
            (args or []) + ["-o", str(desk)],
            env_extra={
                "DESKDIR": str(desk),
                "SEVEN_Z_LOG": str(tmp_path / "7z.log"),
                "PICKER_LOG": str(tmp_path / "picker.log"),
            },
            mock_bins={"7z": SEVEN_Z_MOCK, "envify": ENVIFY_MOCK, "picker": picker},
            isolate_path=True,
            cwd=work,
        )
    return _run


def extracted_archive(tmp_path):
    return (tmp_path / "7z.log").read_text().strip()


class TestArchiveDiscovery:
    def test_should_extract_the_only_archive_in_the_current_directory(self, uncompress, tmp_path, workspace):
        work, _ = workspace
        (work / "one archive.7z").touch()

        result = uncompress()

        assert result.returncode == 0
        assert extracted_archive(tmp_path) == "one archive.7z"
        assert not (tmp_path / "picker.log").exists()

    def test_should_error_when_the_current_directory_holds_no_archive(self, uncompress, tmp_path):
        result = uncompress()

        assert result.returncode == 1
        assert "no 7z file in" in result.stderr
        assert not (tmp_path / "7z.log").exists()

    def test_should_offer_every_archive_to_the_picker_when_several_exist(self, uncompress, tmp_path, workspace):
        work, _ = workspace
        (work / "alpha.7z").touch()
        (work / "bravo.7z").touch()
        (work / "notes.txt").touch()

        result = uncompress()

        assert result.returncode == 0
        assert (tmp_path / "picker.log").read_text().splitlines() == ["alpha.7z", "bravo.7z"]
        assert extracted_archive(tmp_path) == "alpha.7z"

    def test_should_abort_when_the_picker_selects_nothing(self, uncompress, tmp_path, workspace):
        work, _ = workspace
        (work / "alpha.7z").touch()
        (work / "bravo.7z").touch()

        result = uncompress(picker=PICKER_CANCELLED)

        assert result.returncode == 1
        assert "nothing selected" in result.stderr
        assert not (tmp_path / "7z.log").exists()

    def test_should_ignore_discovery_when_an_archive_is_named(self, uncompress, tmp_path, workspace):
        work, _ = workspace
        (work / "alpha.7z").touch()
        (work / "bravo.7z").touch()

        result = uncompress(["bravo.7z"])

        assert result.returncode == 0
        assert extracted_archive(tmp_path) == "bravo.7z"
        assert not (tmp_path / "picker.log").exists()
