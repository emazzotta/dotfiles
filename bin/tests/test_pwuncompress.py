import unicodedata

import pytest

SEVEN_Z_MOCK = r'''
name=$(basename "$0")
case "$name" in
    7zz) accept="${ACCEPT_7ZZ-}" ;;
    keka) shift 2; accept="${ACCEPT_KEKA-}" ;;
    *) accept="${ACCEPT_7Z-*}" ;;
esac
password=""
for arg in "$@"; do
    case "$arg" in -p*) password="${arg#-p}" ;; esac
done
if [ "$1" = l ] && [ -n "${HEADERS_PLAIN:-}" ]; then
    exit 0
fi
if [ "$accept" != "*" ] && [ "$password" != "$accept" ]; then
    exit 2
fi
if [ "$1" = x ]; then
    printf '%s\t%s\t%s\n' "$name" "$2" "$password" >> "$SEVEN_Z_LOG"
fi
'''
STORED_PASSWORD = "test-password"
PICKER_PICKS_FIRST = 'cat > "$PICKER_LOG"\nsed -n 1p "$PICKER_LOG"'
PICKER_CANCELLED = 'cat > "$PICKER_LOG"\nexit 130'
UMLAUT_PASSWORD = "p\u00c4ss"
UMLAUT_PASSWORD_NFD = unicodedata.normalize("NFD", UMLAUT_PASSWORD)


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

    def _run(args=None, picker=PICKER_PICKS_FIRST, password=STORED_PASSWORD,
             accept_7z="*", accept_7zz=None, accept_keka=None, headers_plain=False):
        env = {
            "DESKDIR": str(desk),
            "SEVEN_Z_LOG": str(tmp_path / "7z.log"),
            "PICKER_LOG": str(tmp_path / "picker.log"),
            "ACCEPT_7Z": accept_7z,
            "KEKA_CLI": str(tmp_path / "mock_bin" / "keka"),
        }
        if accept_7zz is not None:
            env["ACCEPT_7ZZ"] = accept_7zz
        if accept_keka is not None:
            env["ACCEPT_KEKA"] = accept_keka
        if headers_plain:
            env["HEADERS_PLAIN"] = "1"
        return run_bash(
            "pwuncompress",
            (args or []) + ["-o", str(desk)],
            env_extra=env,
            mock_bins={
                "7z": SEVEN_Z_MOCK,
                "7zz": SEVEN_Z_MOCK,
                "keka": SEVEN_Z_MOCK,
                "envify": f"export PASSWORD_ZIPS='{password}'",
                "picker": picker,
            },
            isolate_path=True,
            cwd=work,
        )
    return _run


def extractions(tmp_path):
    log = tmp_path / "7z.log"
    if not log.exists():
        return []
    return [tuple(line.split("\t")) for line in log.read_text().splitlines()]


def extracted_archive(tmp_path):
    ((_, archive, _),) = extractions(tmp_path)
    return archive


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


class TestPasswordFallback:
    @pytest.fixture(autouse=True)
    def archive(self, workspace):
        work, _ = workspace
        (work / "a.7z").touch()

    def test_should_extract_with_the_stored_password_when_it_opens_the_archive(self, uncompress, tmp_path):
        result = uncompress(accept_7z=STORED_PASSWORD)

        assert result.returncode == 0
        assert extractions(tmp_path) == [("7z", "a.7z", STORED_PASSWORD)]

    def test_should_fall_back_to_the_nfd_spelling_when_the_stored_one_fails(self, uncompress, tmp_path):
        result = uncompress(password=UMLAUT_PASSWORD, accept_7z=UMLAUT_PASSWORD_NFD)

        assert result.returncode == 0
        assert extractions(tmp_path) == [("7z", "a.7z", UMLAUT_PASSWORD_NFD)]
        assert "NFD" in result.stdout

    def test_should_prefer_7zz_over_the_7z_wrapper(self, uncompress, tmp_path):
        result = uncompress(accept_7zz=STORED_PASSWORD)

        assert result.returncode == 0
        assert extractions(tmp_path) == [("7zz", "a.7z", STORED_PASSWORD)]

    def test_should_try_keka_after_7zz_rejects_every_spelling(self, uncompress, tmp_path):
        result = uncompress(accept_keka=STORED_PASSWORD, accept_7z="")

        assert result.returncode == 0
        assert extractions(tmp_path) == [("keka", "a.7z", STORED_PASSWORD)]

    def test_should_use_the_7z_wrapper_when_7zz_rejects_every_spelling(self, uncompress, tmp_path):
        result = uncompress(password=UMLAUT_PASSWORD, accept_7zz="", accept_7z=UMLAUT_PASSWORD_NFD)

        assert result.returncode == 0
        assert extractions(tmp_path) == [("7z", "a.7z", UMLAUT_PASSWORD_NFD)]

    def test_should_check_passwords_by_testing_when_headers_are_not_encrypted(self, uncompress, tmp_path):
        result = uncompress(password=UMLAUT_PASSWORD, accept_7z=UMLAUT_PASSWORD_NFD, headers_plain=True)

        assert result.returncode == 0
        assert extractions(tmp_path) == [("7z", "a.7z", UMLAUT_PASSWORD_NFD)]

    def test_should_fail_without_extracting_when_no_spelling_opens_the_archive(self, uncompress, tmp_path):
        result = uncompress(accept_7z="something-else")

        assert result.returncode == 1
        assert extractions(tmp_path) == []
        assert "No spelling of PASSWORD_ZIPS opens" in result.stderr
