import pytest


@pytest.fixture
def mod(load_script):
    return load_script("trackduplication_info")


class TestGenerateReport:
    def test_empty_details(self, mod):
        args = type("A", (), {"search_path": ["/music"], "output_path": "."})()
        report = mod.generate_report({}, args, 0)
        assert "No MP3 files found" in report

    def test_single_group_no_duplicates(self, mod):
        args = type("A", (), {"search_path": ["/music"], "output_path": "."})()
        details = {"song": [(1000, "/music/song.mp3")]}
        report = mod.generate_report(details, args, 0)
        assert "0 duplicate groups" in report
        assert "song" not in report.split("found.")[1] if "found." in report else True

    def test_duplicate_group_in_report(self, mod):
        args = type("A", (), {"search_path": ["/music"], "output_path": "."})()
        details = {
            "track": [
                (5000, "/music/a/track.mp3"),
                (3000, "/music/b/track.mp3"),
            ]
        }
        report = mod.generate_report(details, args, 1)
        assert "1 duplicate groups" in report
        assert "track" in report
        assert "/music/a" in report
        assert "/music/b" in report
        assert "track.mp3" in report

    def test_largest_file_marked(self, mod):
        args = type("A", (), {"search_path": ["/music"], "output_path": "."})()
        details = {
            "track": [
                (3000, "/music/small.mp3"),
                (5000, "/music/large.mp3"),
            ]
        }
        report = mod.generate_report(details, args, 1)
        lines = report.split("\n")
        first_data_line = [l for l in lines if "| X |" in l]
        assert len(first_data_line) == 1
        assert "large.mp3" in first_data_line[0]

    def test_report_contains_header(self, mod):
        args = type("A", (), {"search_path": ["/a", "/b"], "output_path": "."})()
        report = mod.generate_report({}, args, 0)
        assert "MP3 File Analysis" in report
        assert "/a" in report
        assert "/b" in report


def _album(tmp_path, files):
    for relative, content in files.items():
        target = tmp_path / "music" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return tmp_path / "music"


class TestGrouping:
    def test_should_not_group_tracks_whose_names_only_share_a_prefix_of_letters_from_mp3(self, run_cli, tmp_path):
        music = _album(tmp_path, {"a/Camp.mp3": b"1234", "b/Cam.mp3": b"12"})

        result = run_cli("trackduplication_info", [str(music), "-o", str(tmp_path / "out")])

        assert result.returncode == 0, result.stderr
        assert "0 duplicate groups found." in (tmp_path / "out" / "report.md").read_text()

    def test_should_group_the_same_track_name_found_in_two_folders(self, run_cli, tmp_path):
        music = _album(tmp_path, {"a/Camp.mp3": b"1234", "b/Camp.mp3": b"12"})

        result = run_cli("trackduplication_info", [str(music), "-o", str(tmp_path / "out")])

        report = (tmp_path / "out" / "report.md").read_text()
        assert result.returncode == 0, result.stderr
        assert "1 duplicate groups found." in report
        assert "## Potential Versions of: Camp\n" in report


class TestHandleDuplicates:
    @pytest.fixture
    def confirm(self, mod):
        mod.input = lambda prompt: "yes"

    def test_should_refuse_to_overwrite_a_file_already_in_the_destination(self, mod, confirm, tmp_path):
        music = _album(tmp_path, {"a/track.mp3": b"large version", "b/track.mp3": b"small"})
        destination = tmp_path / "dest"
        destination.mkdir()
        (destination / "track.mp3").write_bytes(b"existing")
        group = {"track": [(13, str(music / "a/track.mp3")), (5, str(music / "b/track.mp3"))]}

        mod.handle_duplicates(group, str(destination))

        assert (destination / "track.mp3").read_bytes() == b"existing"
        assert (music / "a/track.mp3").read_bytes() == b"large version"
        assert (music / "b/track.mp3").read_bytes() == b"small"

    def test_should_move_the_largest_and_delete_the_rest_when_the_destination_is_free(self, mod, confirm, tmp_path):
        music = _album(tmp_path, {"a/track.mp3": b"large version", "b/track.mp3": b"small"})
        destination = tmp_path / "dest"
        destination.mkdir()
        group = {"track": [(13, str(music / "a/track.mp3")), (5, str(music / "b/track.mp3"))]}

        mod.handle_duplicates(group, str(destination))

        assert (destination / "track.mp3").read_bytes() == b"large version"
        assert not (music / "a/track.mp3").exists()
        assert not (music / "b/track.mp3").exists()

    def test_should_delete_the_smaller_copies_when_the_largest_already_sits_in_the_destination(self, mod, confirm, tmp_path):
        music = _album(tmp_path, {"dest/track.mp3": b"large version", "b/track.mp3": b"small"})
        group = {"track": [(13, str(music / "dest/track.mp3")), (5, str(music / "b/track.mp3"))]}

        mod.handle_duplicates(group, str(music / "dest"))

        assert (music / "dest/track.mp3").read_bytes() == b"large version"
        assert not (music / "b/track.mp3").exists()
