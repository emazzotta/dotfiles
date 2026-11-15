import sys

import pytest

FFMPEG_OK = 'touch "${@: -1}"'


@pytest.fixture
def mod(load_script):
    return load_script("videotox")


class TestFormatCodecs:
    def test_all_codecs_are_tuples(self, mod):
        for fmt, codecs in mod.FORMAT_CODECS.items():
            assert isinstance(codecs, tuple)
            assert len(codecs) == 2

    def test_common_formats_present(self, mod):
        for fmt in ("mp4", "mkv", "webm", "avi"):
            assert fmt in mod.FORMAT_CODECS


class TestCli:
    def test_should_convert_every_file_when_a_glob_expands_to_many_inputs(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        names = ["one.mov", "two.mov", "three.mov"]
        for name in names:
            (work / name).touch()

        result = run_cli("videotox", ["-f", "mp4", "-i"] + [str(work / n) for n in names],
                         mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode == 0, result.stderr
        assert {p.name for p in work.glob("*.mp4")} == {"one.mp4", "two.mp4", "three.mp4"}

    def test_should_convert_a_directory_of_video_files(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        for name in ("one.mov", "two.mkv", "skip.txt"):
            (work / name).touch()

        result = run_cli("videotox", ["-f", "mp4", "-i", str(work)],
                         mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode == 0, result.stderr
        assert {p.name for p in work.glob("*.mp4")} == {"one.mp4", "two.mp4"}

class TestCwdDefault:
    def test_should_convert_the_sole_video_file_when_no_input_is_given(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        (work / "clip.mkv").touch()
        (work / "notes.txt").touch()

        result = run_cli("videotox", ["-f", "mp4"], mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode == 0, result.stderr
        assert (work / "clip.mp4").exists()

    def test_should_exit_when_several_video_files_match_and_no_terminal_can_prompt(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        for name in ("one.mkv", "two.mkv"):
            (work / name).touch()

        result = run_cli("videotox", ["-f", "mp4"], mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode != 0
        assert not list(work.glob("*.mp4"))


class TestFfmpegCommand:
    @staticmethod
    def _recording_ffmpeg(tmp_path):
        return f'printf "%s\\n" "$@" > "{tmp_path}/ffmpeg_args.txt"\n' + FFMPEG_OK

    @pytest.mark.parametrize("fmt,codec_args", [
        ("mp4", ["-c:v", "libx264", "-c:a", "aac", "-crf", "23", "-movflags", "+faststart"]),
        ("m4v", ["-c:v", "libx264", "-c:a", "aac", "-crf", "23", "-movflags", "+faststart"]),
        ("mov", ["-c:v", "libx264", "-c:a", "aac", "-crf", "23", "-movflags", "+faststart"]),
        ("mkv", ["-c:v", "libx264", "-c:a", "aac", "-crf", "23"]),
        ("avi", ["-c:v", "libx264", "-c:a", "mp3", "-crf", "23"]),
        ("webm", ["-c:v", "libvpx-vp9", "-c:a", "libopus", "-crf", "23", "-b:v", "0"]),
        ("mpg", ["-c:v", "mpeg2video", "-c:a", "mp2", "-crf", "23"]),
        ("mpeg", ["-c:v", "mpeg2video", "-c:a", "mp2", "-crf", "23"]),
    ])
    def test_should_pass_the_codecs_and_extra_options_of_the_format_to_ffmpeg(
        self, run_cli, tmp_path, fmt, codec_args
    ):
        work = tmp_path / "work"
        work.mkdir()
        source = work / "clip.wmv"
        source.touch()

        result = run_cli("videotox", ["-f", fmt, "-i", str(source)],
                         mock_bins={"ffmpeg": self._recording_ffmpeg(tmp_path)}, cwd=work)

        args = (tmp_path / "ffmpeg_args.txt").read_text().splitlines()
        assert result.returncode == 0, result.stderr
        assert args == ["-i", str(source.resolve()), *codec_args, "-y", str(work.resolve() / f"clip.{fmt}")]

    def test_should_pass_the_given_quality_as_crf(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        source = work / "clip.wmv"
        source.touch()

        result = run_cli("videotox", ["-f", "mkv", "-q", "30", "-i", str(source)],
                         mock_bins={"ffmpeg": self._recording_ffmpeg(tmp_path)}, cwd=work)

        args = (tmp_path / "ffmpeg_args.txt").read_text().splitlines()
        assert result.returncode == 0, result.stderr
        assert args[args.index("-crf"):][:2] == ["-crf", "30"]

    def test_should_default_to_mp4_and_name_the_conversion_in_the_report(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        (work / "clip.mov").touch()

        result = run_cli("videotox", ["-i", str(work / "clip.mov")],
                         mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode == 0, result.stderr
        assert (work / "clip.mp4").exists()
        assert "Converting: clip.mov -> clip.mp4" in result.stdout

    def test_should_reject_a_format_outside_the_table(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        (work / "clip.mov").touch()

        result = run_cli("videotox", ["-f", "xyz", "-i", str(work / "clip.mov")],
                         mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode == 2
        assert "invalid choice: 'xyz'" in result.stderr


class TestUnsupportedFormat:
    def test_should_report_the_format_and_count_the_file_as_failed_when_it_has_no_codec(
        self, mod, tmp_path, monkeypatch, capsys
    ):
        source = tmp_path / "clip.mov"
        source.touch()
        mod.FORMAT_CODECS["mp4"] = (None, None)
        monkeypatch.setattr(sys, "argv", ["videotox", "-f", "mp4", "-i", str(source)])

        mod.main()

        captured = capsys.readouterr()
        assert "Unsupported format: mp4" in captured.err
        assert "Summary: 0 succeeded, 1 failed, 1 total" in captured.out
        assert "Failed:" not in captured.err
        assert sorted(path.name for path in tmp_path.iterdir()) == ["clip.mov"]
