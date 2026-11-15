import json
import subprocess

import pytest

from bin.tests.conftest import requires_tool

BC_STAND_IN = (
    "python3 -c 'import math, sys; "
    'expression = sys.stdin.read().strip().replace("^", "**").replace("l(", "math.log("); '
    "result = eval(expression); print(int(result) if isinstance(result, bool) else result)'"
)
SPEED = "2"
RECORD_ARGV = r"""python3 -I -c 'import json, os, sys; open(os.environ["ARGV_LOG"], "a").write(json.dumps(sys.argv[1:]) + "\n")'"""
FFMPEG_STAND_IN = RECORD_ARGV + """ ffmpeg "$@"
if [ "$#" -eq 2 ] && [ "$1" = "-i" ]; then
    [ "${HAS_AUDIO:-0}" = 1 ] && echo "  Stream #0:1: Audio: aac" >&2
    exit 1
fi
exit ${FFMPEG_STATUS:-0}"""
FFPROBE_STAND_IN = RECORD_ARGV + ' ffprobe "$@"'


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

    def _run(video, speed=SPEED, extra_bins=None, env=None):
        return run_cli(
            "videospeedup", [str(video), speed], env_extra=env,
            mock_bins={"bc": BC_STAND_IN, **(extra_bins or {})}, cwd=work,
        )
    _run.work = work
    return _run


@pytest.fixture
def recorded(speedup, tmp_path):
    argv_log = tmp_path / "argv.jsonl"
    argv_log.touch()

    def _run(video, speed=SPEED, **env):
        return speedup(
            video, speed, env={"ARGV_LOG": str(argv_log), **env},
            extra_bins={"ffmpeg": FFMPEG_STAND_IN, "ffprobe": FFPROBE_STAND_IN},
        )
    _run.work = speedup.work
    _run.calls = lambda: [json.loads(line) for line in argv_log.read_text().splitlines()]
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


HOSTILE_NAMES = [
    "two words.mp4",
    'say "hi".mp4',
    "it's.mp4",
    "$(touch pwned).mp4",
    "`touch pwned`.mp4",
    "$HOME.mp4",
]


def silent_argv(video, speed, output):
    return ["ffmpeg", "-i", video, "-filter:v", f"setpts=PTS/{speed}", "-an", output]


def audio_argv(video, speed, atempo, output):
    return ["ffmpeg", "-i", video, "-filter_complex", f"[0:v]setpts=PTS/{speed}[v];[0:a]{atempo}[a]",
            "-map", "[v]", "-map", "[a]", output]


class TestVideospeedupFfmpegArguments:
    @pytest.mark.parametrize("has_audio, speed, expected_call", [
        ("0", "2", silent_argv("in.mp4", "2", "sped_up_in.mp4")),
        ("1", "2", audio_argv("in.mp4", "2", "atempo=2.0", "sped_up_in.mp4")),
        ("1", "3", audio_argv("in.mp4", "3", "atempo=2.0,atempo=1.5", "sped_up_in.mp4")),
        ("1", "5", audio_argv("in.mp4", "5", "atempo=2.0,atempo=2.0,atempo=1.25", "sped_up_in.mp4")),
        ("1", "1.5", audio_argv("in.mp4", "1.5", "atempo=2.0,atempo=0.75", "sped_up_in.mp4")),
    ])
    def test_should_pass_ffmpeg_the_same_arguments_as_before(self, recorded, has_audio, speed, expected_call):
        result = recorded("in.mp4", speed, HAS_AUDIO=has_audio)

        assert result.returncode == 0, result.stderr
        assert recorded.calls() == [["ffmpeg", "-i", "in.mp4"], expected_call]
        assert f"Video successfully sped up by factor of {speed}." in result.stdout
        assert "Output video: sped_up_in.mp4" in result.stdout

    def test_should_pass_ffmpeg_an_output_beside_an_input_given_with_a_directory(self, recorded):
        result = recorded("clips/a.mp4", HAS_AUDIO="0")

        assert result.returncode == 0, result.stderr
        assert recorded.calls()[-1] == silent_argv("clips/a.mp4", "2", "clips/sped_up_a.mp4")

    def test_should_fail_with_a_message_when_ffmpeg_fails(self, recorded):
        result = recorded("in.mp4", FFMPEG_STATUS="1")

        assert result.returncode == 1
        assert "ffmpeg command failed" in result.stderr
        assert "successfully" not in result.stdout

    @pytest.mark.parametrize("has_audio", ["0", "1"])
    @pytest.mark.parametrize("name", HOSTILE_NAMES)
    def test_should_hand_ffmpeg_a_hostile_file_name_as_one_argument_and_run_nothing(self, recorded, name, has_audio):
        result = recorded(name, HAS_AUDIO=has_audio)

        assert result.returncode == 0, result.stderr
        ffmpeg_call = recorded.calls()[-1]
        assert ffmpeg_call.count(name) == 1
        assert ffmpeg_call.count(f"sped_up_{name}") == 1
        assert not (recorded.work / "pwned").exists()
