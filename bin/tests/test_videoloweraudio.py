import pytest

FFMPEG_MOCK = 'printf "%s\\n" "$@" > "$FFMPEG_LOG"'


@pytest.fixture
def lower_audio(run_cli, tmp_path):
    log = tmp_path / "ffmpeg.log"

    def _run(*args):
        result = run_cli("videoloweraudio", list(args), env_extra={"FFMPEG_LOG": str(log)},
                         mock_bins={"ffmpeg": FFMPEG_MOCK}, cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        return log.read_text().splitlines()
    return _run


class TestVideoloweraudio:
    @pytest.mark.parametrize("video,output", [
        ("clip.mp4", "clip_lower_audio.mp4"),
        ("./clip.mp4", "./clip_lower_audio.mp4"),
        ("my.clip.mp4", "my.clip_lower_audio.mp4"),
        ("../shots/clip.mov", "../shots/clip_lower_audio.mov"),
        ("v1.2/clip.mp4", "v1.2/clip_lower_audio.mp4"),
    ])
    def test_should_write_the_output_beside_the_input_and_keep_the_extension(self, lower_audio, video, output):
        call = lower_audio(video)

        assert call[:2] == ["-i", video]
        assert call[-1] == output

    def test_should_reduce_the_audio_to_a_fifth(self, lower_audio):
        call = lower_audio("clip.mp4")

        assert call[call.index("-af") + 1] == "volume=0.2"
