import pytest

FFMPEG_OK = 'touch "${@: -1}"'


@pytest.fixture
def mod(load_script):
    return load_script("audioboost")


class TestDefaults:
    def test_should_boost_by_two_with_a_boosted_suffix(self, mod):
        assert mod.DEFAULT_VOLUME == 2.0
        assert mod.DEFAULT_SUFFIX == "_boosted"


class TestCli:
    def test_should_boost_every_file_when_a_glob_expands_to_many_inputs(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        names = ["one.wav", "two.wav", "three.wav"]
        for name in names:
            (work / name).touch()

        result = run_cli("audioboost", ["-i"] + [str(work / n) for n in names],
                         mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode == 0, result.stderr
        assert {p.name for p in work.glob("*_boosted.wav")} == {
            "one_boosted.wav", "two_boosted.wav", "three_boosted.wav"}

    def test_should_apply_a_custom_suffix(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        (work / "one.wav").touch()

        result = run_cli("audioboost", ["-i", str(work / "one.wav"), "-s", "_loud"],
                         mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode == 0, result.stderr
        assert (work / "one_loud.wav").exists()

class TestQuality:
    @staticmethod
    def _recording_ffmpeg(tmp_path):
        return f'printf "%s\\n" "$@" > "{tmp_path}/ffmpeg_args.txt"\n' + FFMPEG_OK

    @pytest.mark.parametrize("extension,expected", [
        ("mp3", ["-b:a", "320k"]),
        ("m4a", ["-b:a", "256k"]),
        ("aac", ["-b:a", "256k"]),
        ("opus", ["-b:a", "128k"]),
        ("ogg", ["-q:a", "6"]),
    ])
    def test_should_set_the_quality_of_a_lossy_input_explicitly(self, run_cli, tmp_path, extension, expected):
        work = tmp_path / "work"
        work.mkdir()
        (work / f"voice.{extension}").touch()

        result = run_cli("audioboost", ["-i", str(work / f"voice.{extension}")],
                         mock_bins={"ffmpeg": self._recording_ffmpeg(tmp_path)}, cwd=work)

        args = (tmp_path / "ffmpeg_args.txt").read_text().split("\n")
        assert result.returncode == 0, result.stderr
        assert args[args.index(expected[0]):][:2] == expected

    @pytest.mark.parametrize("extension", ["wav", "flac"])
    def test_should_add_no_quality_option_for_a_lossless_input(self, run_cli, tmp_path, extension):
        work = tmp_path / "work"
        work.mkdir()
        (work / f"voice.{extension}").touch()

        result = run_cli("audioboost", ["-i", str(work / f"voice.{extension}")],
                         mock_bins={"ffmpeg": self._recording_ffmpeg(tmp_path)}, cwd=work)

        args = (tmp_path / "ffmpeg_args.txt").read_text().split("\n")
        assert result.returncode == 0, result.stderr
        assert not {"-b:a", "-q:a"} & set(args)


class TestOriginalSurvival:
    def test_should_keep_the_original_when_ffmpeg_fails_even_with_delete(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        (work / "voice.mp3").write_bytes(b"original")

        result = run_cli("audioboost", ["-i", str(work / "voice.mp3"), "-d"],
                         mock_bins={"ffmpeg": "exit 1"}, cwd=work)

        assert (work / "voice.mp3").read_bytes() == b"original"
        assert "Failed: voice.mp3" in result.stderr


class TestCwdDefault:
    def test_should_boost_the_sole_audio_file_when_no_input_is_given(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        (work / "voice.wav").touch()
        (work / "notes.txt").touch()

        result = run_cli("audioboost", [], mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode == 0, result.stderr
        assert (work / "voice_boosted.wav").exists()

    def test_should_exit_when_several_audio_files_match_and_no_terminal_can_prompt(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        for name in ("one.wav", "two.wav"):
            (work / name).touch()

        result = run_cli("audioboost", [], mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode != 0
        assert not list(work.glob("*_boosted.wav"))


class TestFfmpegCommand:
    @staticmethod
    def _recording_ffmpeg(tmp_path):
        return f'printf "%s\\n" "$@" > "{tmp_path}/ffmpeg_args.txt"\n' + FFMPEG_OK

    def test_should_pass_the_default_volume_filter_to_ffmpeg(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        source = work / "voice.wav"
        source.touch()

        result = run_cli("audioboost", ["-i", str(source)],
                         mock_bins={"ffmpeg": self._recording_ffmpeg(tmp_path)}, cwd=work)

        args = (tmp_path / "ffmpeg_args.txt").read_text().splitlines()
        assert result.returncode == 0, result.stderr
        assert args == ["-i", str(source.resolve()), "-af", "volume=2.0", "-y",
                        str(work.resolve() / "voice_boosted.wav")]

    def test_should_pass_the_given_volume_and_name_it_in_the_report(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        source = work / "voice.wav"
        source.touch()

        result = run_cli("audioboost", ["-v", "1.5", "-s", "_loud", "-i", str(source)],
                         mock_bins={"ffmpeg": self._recording_ffmpeg(tmp_path)}, cwd=work)

        args = (tmp_path / "ffmpeg_args.txt").read_text().splitlines()
        assert result.returncode == 0, result.stderr
        assert args == ["-i", str(source.resolve()), "-af", "volume=1.5", "-y",
                        str(work.resolve() / "voice_loud.wav")]
        assert "Found 1 audio file(s) to boost at 1.5x volume" in result.stdout
        assert "Boosting: voice.wav -> voice_loud.wav" in result.stdout

    def test_should_keep_an_uppercase_extension_and_match_its_quality_case_insensitively(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        source = work / "voice.MP3"
        source.touch()

        result = run_cli("audioboost", ["-i", str(source)],
                         mock_bins={"ffmpeg": self._recording_ffmpeg(tmp_path)}, cwd=work)

        args = (tmp_path / "ffmpeg_args.txt").read_text().splitlines()
        assert result.returncode == 0, result.stderr
        assert args == ["-i", str(source.resolve()), "-af", "volume=2.0", "-b:a", "320k", "-y",
                        str(work.resolve() / "voice_boosted.MP3")]
