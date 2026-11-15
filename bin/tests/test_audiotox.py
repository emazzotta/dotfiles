import sys

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


class TestFfmpegCommand:
    @staticmethod
    def _recording_ffmpeg(tmp_path):
        return f'printf "%s\\n" "$@" > "{tmp_path}/ffmpeg_args.txt"\n' + FFMPEG_OK

    @pytest.mark.parametrize("fmt,source_ext,codec_args", [
        ("mp3", "wav", ["-c:a", "libmp3lame", "-b:a", "320k"]),
        ("m4a", "wav", ["-c:a", "aac", "-b:a", "256k"]),
        ("aac", "wav", ["-c:a", "aac", "-b:a", "256k"]),
        ("opus", "wav", ["-c:a", "libopus", "-b:a", "128k"]),
        ("ogg", "wav", ["-c:a", "libvorbis", "-q:a", "6"]),
        ("flac", "wav", ["-c:a", "flac"]),
        ("wav", "flac", ["-c:a", "pcm_s16le"]),
    ])
    def test_should_pass_the_codec_and_quality_of_the_format_to_ffmpeg(
        self, run_cli, tmp_path, fmt, source_ext, codec_args
    ):
        work = tmp_path / "work"
        work.mkdir()
        source = work / f"voice.{source_ext}"
        source.touch()

        result = run_cli("audiotox", ["-f", fmt, "-i", str(source)],
                         mock_bins={"ffmpeg": self._recording_ffmpeg(tmp_path)}, cwd=work)

        args = (tmp_path / "ffmpeg_args.txt").read_text().splitlines()
        assert result.returncode == 0, result.stderr
        assert args == ["-i", str(source.resolve()), *codec_args, "-y", str(work.resolve() / f"voice.{fmt}")]

    def test_should_default_to_mp3_and_name_the_conversion_in_the_report(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        (work / "voice.wav").touch()

        result = run_cli("audiotox", ["-i", str(work / "voice.wav")],
                         mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode == 0, result.stderr
        assert (work / "voice.mp3").exists()
        assert "Converting: voice.wav -> voice.mp3" in result.stdout

    def test_should_reject_a_format_outside_the_table(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        (work / "voice.wav").touch()

        result = run_cli("audiotox", ["-f", "xyz", "-i", str(work / "voice.wav")],
                         mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode == 2
        assert "invalid choice: 'xyz'" in result.stderr


class TestUnsupportedFormat:
    def test_should_report_the_format_and_count_the_file_as_failed_when_it_has_no_codec(
        self, mod, tmp_path, monkeypatch, capsys
    ):
        source = tmp_path / "voice.wav"
        source.touch()
        mod.AUDIO_CODECS["mp3"] = ""
        monkeypatch.setattr(sys, "argv", ["audiotox", "-f", "mp3", "-i", str(source)])

        mod.main()

        captured = capsys.readouterr()
        assert "Unsupported format: mp3" in captured.err
        assert "Summary: 0 succeeded, 1 failed, 1 total" in captured.out
        assert "Failed:" not in captured.err
        assert sorted(path.name for path in tmp_path.iterdir()) == ["voice.wav"]
