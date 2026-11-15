import pytest

RECORD_ARGS = 'printf "%s\\n" "$@" > "$FFMPEG_ARGS"'


@pytest.fixture
def imgtovideo(run_bash, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    args_log = tmp_path / "ffmpeg.args"

    def _run():
        return run_bash("imgtovideo", env_extra={"FFMPEG_ARGS": str(args_log)},
                        mock_bins={"ffmpeg": RECORD_ARGS}, cwd=work)
    _run.work = work
    _run.args = lambda: args_log.read_text().splitlines()
    return _run


class TestImgtovideo:
    def should_hand_ffmpeg_the_jpg_glob_unexpanded_so_no_photo_becomes_an_output(self, imgtovideo):
        (imgtovideo.work / "a.jpg").touch()
        (imgtovideo.work / "b.jpg").touch()

        result = imgtovideo()

        assert result.returncode == 0, result.stderr
        args = imgtovideo.args()
        assert args[args.index("-i") + 1] == "*.jpg"
        assert args[-1] == "timelapsevid.mp4"
