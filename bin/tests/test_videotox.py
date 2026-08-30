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
