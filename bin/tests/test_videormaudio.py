import pytest

FFMPEG_MOCK = 'printf "%s\\n" "$@" > "$FFMPEG_LOG"'


@pytest.fixture
def remove_audio(run_cli, tmp_path):
    log = tmp_path / "ffmpeg.log"

    def _run(*args):
        result = run_cli("videormaudio", list(args), env_extra={"FFMPEG_LOG": str(log)},
                         mock_bins={"ffmpeg": FFMPEG_MOCK}, cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        return log.read_text().splitlines()
    return _run


class TestVideormaudio:
    @pytest.mark.parametrize("video,output", [
        ("clip.mp4", "clip_no_audio.mp4"),
        ("./clip.mp4", "./clip_no_audio.mp4"),
        ("my.clip.mp4", "my.clip_no_audio.mp4"),
        ("../shots/clip.mov", "../shots/clip_no_audio.mov"),
        ("v1.2/clip.mp4", "v1.2/clip_no_audio.mp4"),
    ])
    def test_should_write_the_output_beside_the_input_and_keep_the_extension(self, remove_audio, video, output):
        call = remove_audio(video)

        assert call[:2] == ["-i", video]
        assert call[-1] == output

    def test_should_drop_the_audio_stream(self, remove_audio):
        call = remove_audio("clip.mp4")

        assert "-an" in call
