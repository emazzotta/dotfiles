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
