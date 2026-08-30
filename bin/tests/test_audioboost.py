import pytest


FFMPEG_OK = 'touch "${@: -1}"'


@pytest.fixture
def mod(load_script):
    return load_script("audioboost")


class TestCollectInputs:
    def test_should_gather_every_path_when_many_inputs_are_given(self, mod, tmp_path):
        first = tmp_path / "a.wav"
        second = tmp_path / "b.flac"
        first.touch()
        second.touch()

        assert mod.collect_inputs([first, second]) == [first, second]

    def test_should_keep_each_file_once_when_inputs_overlap(self, mod, tmp_path):
        track = tmp_path / "track.wav"
        track.touch()

        assert mod.collect_inputs([tmp_path, track]) == [track]

    def test_should_exit_when_an_input_is_missing(self, mod, tmp_path):
        with pytest.raises(SystemExit):
            mod.collect_inputs([tmp_path / "nonexistent.wav"])


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
