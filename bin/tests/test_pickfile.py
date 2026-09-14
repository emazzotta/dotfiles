import re
from pathlib import Path

import pytest

BIN = Path(__file__).parent.parent

PICKER_PICKS_FIRST = 'echo "$*" > "$PICKER_LOG"\nsed -n 1p'
PICKER_CANCELLED = 'echo "$*" > "$PICKER_LOG"\ncat > /dev/null\nexit 130'


@pytest.fixture
def pickfile(run_bash, tmp_path):
    work = tmp_path / "work"
    work.mkdir()

    def _run(args, picker=PICKER_PICKS_FIRST):
        return run_bash(
            "pickfile",
            args,
            env_extra={"PICKER_LOG": str(tmp_path / "picker.log")},
            mock_bins={"picker": picker},
            isolate_path=True,
            cwd=work,
        )
    _run.work = work
    _run.picker_log = tmp_path / "picker.log"
    return _run


class TestSingleMatch:
    def test_should_print_the_only_match_without_prompting(self, pickfile):
        (pickfile.work / "report.pdf").touch()

        result = pickfile(["pdf"])

        assert result.returncode == 0
        assert result.stdout == "report.pdf\n"
        assert not pickfile.picker_log.exists()

    def test_should_accept_an_extension_with_a_leading_dot(self, pickfile):
        (pickfile.work / "report.pdf").touch()

        result = pickfile([".pdf"])

        assert result.stdout == "report.pdf\n"

    def test_should_match_an_extension_case_insensitively(self, pickfile):
        (pickfile.work / "SCAN.PDF").touch()

        result = pickfile(["pdf"])

        assert result.stdout == "SCAN.PDF\n"

    def test_should_count_a_compound_extension_only_once(self, pickfile):
        (pickfile.work / "site.tar.gz").touch()

        result = pickfile(["tar.gz", "gz"])

        assert result.stdout == "site.tar.gz\n"
        assert not pickfile.picker_log.exists()

    def test_should_ignore_a_directory_that_looks_like_a_match(self, pickfile):
        (pickfile.work / "bundle.pdf").mkdir()
        (pickfile.work / "report.pdf").touch()

        result = pickfile(["pdf"])

        assert result.stdout == "report.pdf\n"


class TestNoMatch:
    def test_should_fail_when_nothing_matches(self, pickfile):
        (pickfile.work / "notes.txt").touch()

        result = pickfile(["pdf"])

        assert result.returncode == 1
        assert result.stdout == ""
        assert "no pdf file in" in result.stderr


class TestSeveralMatches:
    def test_should_hand_every_match_to_the_picker(self, pickfile):
        for name in ["alpha.pdf", "bravo.pdf", "notes.txt"]:
            (pickfile.work / name).touch()

        result = pickfile(["pdf"])

        assert result.returncode == 0
        assert result.stdout == "alpha.pdf\n"

    def test_should_pass_the_header_through_to_the_picker(self, pickfile):
        (pickfile.work / "alpha.pdf").touch()
        (pickfile.work / "bravo.pdf").touch()

        pickfile(["--header", "Select archive:", "pdf"])

        assert pickfile.picker_log.read_text().strip() == "--header Select archive:"

    def test_should_fail_when_the_picker_selects_nothing(self, pickfile):
        (pickfile.work / "alpha.pdf").touch()
        (pickfile.work / "bravo.pdf").touch()

        result = pickfile(["pdf"], picker=PICKER_CANCELLED)

        assert result.returncode == 1
        assert result.stdout == ""
        assert "nothing selected" in result.stderr


class TestUsage:
    def test_should_reject_a_call_without_an_extension(self, pickfile):
        result = pickfile([])

        assert result.returncode == 2
        assert "at least one extension" in result.stderr

    def test_should_reject_an_unknown_option(self, pickfile):
        result = pickfile(["--nope", "pdf"])

        assert result.returncode == 2
        assert "unknown option" in result.stderr

    def test_should_reject_a_header_without_a_value(self, pickfile):
        result = pickfile(["--header"])

        assert result.returncode == 2
        assert "requires a value" in result.stderr

    @pytest.mark.parametrize("flag", ["-h", "--help"])
    def test_should_render_its_own_header_comment_as_help(self, pickfile, flag):
        result = pickfile([flag])

        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "pickfile [--header TEXT] [--class NAME] [EXT...]" in result.stdout
        assert "#" not in result.stdout


class TestExtensionClasses:
    def test_should_resolve_a_named_class(self, pickfile):
        (pickfile.work / "clip.mov").touch()
        (pickfile.work / "notes.txt").touch()

        result = pickfile(["--class", "video"])

        assert result.stdout == "clip.mov\n"

    def test_should_combine_a_class_with_a_bare_extension(self, pickfile):
        (pickfile.work / "song.flac").touch()

        result = pickfile(["--class", "video", "flac"])

        assert result.stdout == "song.flac\n"

    def test_should_name_the_class_rather_than_its_extensions_when_nothing_matches(self, pickfile):
        result = pickfile(["--class", "image"])

        assert result.returncode == 1
        assert "no image file in" in result.stderr

    def test_should_reject_an_unknown_class(self, pickfile):
        result = pickfile(["--class", "spreadsheet"])

        assert result.returncode == 2
        assert "unknown class: spreadsheet" in result.stderr

    @pytest.mark.parametrize(
        "class_name,constant",
        [("VIDEO", "VIDEO_EXTS"), ("AUDIO", "AUDIO_EXTS")],
    )
    def test_should_keep_its_media_classes_in_step_with_medialib(self, class_name, constant):
        declared = re.search(
            rf'{class_name}_EXTENSIONS="([^"]*)"', (BIN / "pickfile").read_text()
        ).group(1).split()
        canonical = re.findall(
            r'"([^"]+)"',
            re.search(rf"{constant} = \[([^\]]*)\]", (BIN / "medialib.py").read_text()).group(1),
        )

        assert declared == canonical
