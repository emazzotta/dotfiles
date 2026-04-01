import pytest


@pytest.fixture
def mod(load_script):
    return load_script("audiotox")


class TestFormatTime:
    @pytest.mark.parametrize("seconds,expected", [
        (0.0, "0.0s"),
        (30.5, "30.5s"),
        (59.9, "59.9s"),
        (60.0, "1m 0s"),
        (90.0, "1m 30s"),
        (3661.0, "61m 1s"),
    ])
    def test_formats_correctly(self, mod, seconds, expected):
        assert mod.format_time(seconds) == expected


class TestGetOutputPath:
    def test_basic_output_same_dir(self, mod, tmp_path):
        input_file = tmp_path / "song.wav"
        input_file.touch()
        result = mod.get_output_path(input_file, "mp3", None)
        assert result == tmp_path / "song.mp3"

    def test_output_to_specified_dir(self, mod, tmp_path):
        input_file = tmp_path / "song.wav"
        input_file.touch()
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        result = mod.get_output_path(input_file, "flac", out_dir)
        assert result == out_dir / "song.flac"

    def test_no_conflict_returns_directly(self, mod, tmp_path):
        input_file = tmp_path / "song.wav"
        input_file.touch()
        result = mod.get_output_path(input_file, "mp3", None)
        assert result.name == "song.mp3"


class TestListInputs:
    def test_single_file(self, mod, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        assert mod.list_inputs(f) == [f]

    def test_directory_finds_audio_files(self, mod, tmp_path):
        for name in ("a.mp3", "b.flac", "c.wav", "d.txt"):
            (tmp_path / name).touch()
        results = mod.list_inputs(tmp_path)
        names = {r.name for r in results}
        assert "a.mp3" in names
        assert "b.flac" in names
        assert "c.wav" in names
        assert "d.txt" not in names

    def test_nonexistent_path_exits(self, mod, tmp_path):
        with pytest.raises(SystemExit):
            mod.list_inputs(tmp_path / "nonexistent")

    def test_recursive_search(self, mod, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.mp3").touch()
        results = mod.list_inputs(tmp_path)
        assert any(r.name == "nested.mp3" for r in results)


class TestAudioCodecs:
    def test_all_codecs_have_string_values(self, mod):
        for fmt, codec in mod.AUDIO_CODECS.items():
            assert isinstance(fmt, str)
            assert isinstance(codec, str)

    def test_common_formats_present(self, mod):
        for fmt in ("mp3", "flac", "wav", "aac", "ogg"):
            assert fmt in mod.AUDIO_CODECS
