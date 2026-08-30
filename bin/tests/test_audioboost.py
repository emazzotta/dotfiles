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
