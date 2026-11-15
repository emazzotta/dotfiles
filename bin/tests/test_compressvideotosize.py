import pytest

FFPROBE_STAND_IN = """
case "$*" in
    *bit_rate*) echo 128000 ;;
    *) echo 10 ;;
esac
"""
FFMPEG_STAND_IN = """
echo CALL >> "$FFMPEG_LOG"
printf '%s\\n' "$@" >> "$FFMPEG_LOG"
case "$*" in *"-pass 1"*) exit "${FIRST_PASS_STATUS:-0}" ;; esac
"""
TARGET_MB = "5"


@pytest.fixture
def compressvideotosize(run_bash, tmp_path):
    log = tmp_path / "ffmpeg.log"

    def _run(video, first_pass_status=0):
        return run_bash("compressvideotosize", [video, TARGET_MB], cwd=tmp_path,
                        env_extra={"FFMPEG_LOG": str(log), "FIRST_PASS_STATUS": str(first_pass_status)},
                        mock_bins={"ffprobe": FFPROBE_STAND_IN, "ffmpeg": FFMPEG_STAND_IN})
    _run.calls = lambda: [call.splitlines() for call in log.read_text().split("CALL\n") if call] if log.exists() else []
    return _run


class TestCompressvideotosize:
    def should_hand_ffmpeg_an_output_name_with_spaces_as_one_argument(self, compressvideotosize):
        result = compressvideotosize("My Clip.mp4")

        assert result.returncode == 0, result.stderr
        second_pass = compressvideotosize.calls()[1]
        assert second_pass[-1] == f"My Clip-{TARGET_MB}MB.mp4"

    def should_fail_without_running_the_second_pass_when_the_first_pass_fails(self, compressvideotosize):
        result = compressvideotosize("clip.mp4", first_pass_status=1)

        assert result.returncode != 0
        assert len(compressvideotosize.calls()) == 1

    def should_show_usage_without_a_size(self, run_bash):
        result = run_bash("compressvideotosize", ["clip.mp4"])

        assert result.returncode == 1
        assert "usage:" in result.stdout
