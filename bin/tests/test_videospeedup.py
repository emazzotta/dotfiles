import subprocess

import pytest

from bin.tests.conftest import requires_tool

BC_STAND_IN = (
    "python3 -c 'import math, sys; "
    'expression = sys.stdin.read().strip().replace("^", "**").replace("l(", "math.log("); '
    "result = eval(expression); print(int(result) if isinstance(result, bool) else result)'"
)
SPEED = "2"


def make_video(path, with_audio):
    audio = ["-f", "lavfi", "-i", "sine=duration=1"] if with_audio else []
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=10",
         *audio, "-pix_fmt", "yuv420p", "-shortest", str(path)],
        check=True,
    )


def stream_types(path):
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return probe.stdout.split()


@pytest.fixture
def speedup(run_cli, tmp_path):
    work = tmp_path / "work"
    (work / "clips").mkdir(parents=True)

    def _run(video):
        return run_cli("videospeedup", [str(video), SPEED], mock_bins={"bc": BC_STAND_IN}, cwd=work)
    _run.work = work
    return _run


@requires_tool("ffmpeg")
class TestVideospeedup:
    def test_should_speed_up_a_video_without_an_audio_stream(self, speedup):
        make_video(speedup.work / "silent.mp4", with_audio=False)

        result = speedup("silent.mp4")

        assert result.returncode == 0, result.stderr
        assert stream_types(speedup.work / "sped_up_silent.mp4") == ["video"]

    def test_should_keep_the_audio_stream_of_a_video_that_has_one(self, speedup):
        make_video(speedup.work / "loud.mp4", with_audio=True)

        result = speedup("loud.mp4")

        assert result.returncode == 0, result.stderr
        assert sorted(stream_types(speedup.work / "sped_up_loud.mp4")) == ["audio", "video"]

    def test_should_write_the_output_beside_an_input_given_with_a_directory(self, speedup):
        make_video(speedup.work / "clips" / "a.mp4", with_audio=True)

        result = speedup(speedup.work / "clips" / "a.mp4")

        assert result.returncode == 0, result.stderr
        assert (speedup.work / "clips" / "sped_up_a.mp4").exists()
