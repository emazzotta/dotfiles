import pytest

FFMPEG_OK = 'touch "${@: -1}"'


@pytest.fixture
def mod(load_script):
    return load_script("audiotox")


class TestAudioCodecs:
    def test_all_codecs_have_string_values(self, mod):
        for fmt, codec in mod.AUDIO_CODECS.items():
            assert isinstance(fmt, str)
            assert isinstance(codec, str)

    def test_common_formats_present(self, mod):
        for fmt in ("mp3", "flac", "wav", "aac", "ogg"):
            assert fmt in mod.AUDIO_CODECS


class TestCli:
    def test_should_convert_every_file_when_a_glob_expands_to_many_inputs(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        names = ["one.wav", "two.wav", "three.wav"]
        for name in names:
            (work / name).touch()

        result = run_cli("audiotox", ["-f", "mp3", "-i"] + [str(work / n) for n in names],
                         mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode == 0, result.stderr
        assert {p.name for p in work.glob("*.mp3")} == {"one.mp3", "two.mp3", "three.mp3"}

    def test_should_convert_a_directory_of_audio_files(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        for name in ("one.wav", "two.flac", "skip.txt"):
            (work / name).touch()

        result = run_cli("audiotox", ["-f", "mp3", "-i", str(work)],
                         mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode == 0, result.stderr
        assert {p.name for p in work.glob("*.mp3")} == {"one.mp3", "two.mp3"}

class TestCwdDefault:
    def test_should_convert_the_sole_audio_file_when_no_input_is_given(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        (work / "voice.wav").touch()
        (work / "notes.txt").touch()

        result = run_cli("audiotox", ["-f", "mp3"], mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode == 0, result.stderr
        assert (work / "voice.mp3").exists()

    def test_should_exit_when_several_audio_files_match_and_no_terminal_can_prompt(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        for name in ("one.wav", "two.wav"):
            (work / name).touch()

        result = run_cli("audiotox", ["-f", "mp3"], mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode != 0
        assert not list(work.glob("*.mp3"))
