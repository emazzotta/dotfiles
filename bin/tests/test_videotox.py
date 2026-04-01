import pytest


@pytest.fixture
def mod(load_script):
    return load_script("videotox")


class TestFormatTime:
    @pytest.mark.parametrize("seconds,expected", [
        (0.0, "0.0s"),
        (30.5, "30.5s"),
        (60.0, "1m 0s"),
        (3661.0, "61m 1s"),
    ])
    def test_formats_correctly(self, mod, seconds, expected):
        assert mod.format_time(seconds) == expected


class TestGetOutputPath:
    def test_basic_output_same_dir(self, mod, tmp_path):
        input_file = tmp_path / "video.mov"
        input_file.touch()
        result = mod.get_output_path(input_file, "mp4", None)
        assert result == tmp_path / "video.mp4"

    def test_output_to_specified_dir(self, mod, tmp_path):
        input_file = tmp_path / "video.mov"
        input_file.touch()
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        result = mod.get_output_path(input_file, "mkv", out_dir)
        assert result == out_dir / "video.mkv"


class TestListInputs:
    def test_single_file(self, mod, tmp_path):
        f = tmp_path / "video.mp4"
        f.touch()
        assert mod.list_inputs(f) == [f]

    def test_directory_finds_video_files(self, mod, tmp_path):
        for name in ("a.mp4", "b.mkv", "c.mov", "d.txt"):
            (tmp_path / name).touch()
        results = mod.list_inputs(tmp_path)
        names = {r.name for r in results}
        assert "a.mp4" in names
        assert "b.mkv" in names
        assert "c.mov" in names
        assert "d.txt" not in names

    def test_nonexistent_path_exits(self, mod, tmp_path):
        with pytest.raises(SystemExit):
            mod.list_inputs(tmp_path / "nonexistent")


class TestFormatCodecs:
    def test_all_codecs_are_tuples(self, mod):
        for fmt, codecs in mod.FORMAT_CODECS.items():
            assert isinstance(codecs, tuple)
            assert len(codecs) == 2

    def test_common_formats_present(self, mod):
        for fmt in ("mp4", "mkv", "webm", "avi"):
            assert fmt in mod.FORMAT_CODECS
