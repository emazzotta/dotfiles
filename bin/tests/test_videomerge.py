import subprocess

import pytest

from bin.tests.conftest import requires_tool


def make_video(path):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=10",
         "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )


def frame_count(path):
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return int(probe.stdout.strip())


@pytest.fixture
def merge(run_cli, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    make_video(work / "one.mp4")
    make_video(work / "it's two.mp4")
    clip_frames = frame_count(work / "one.mp4")

    def _run(*videos):
        return run_cli("videomerge", [str(video) for video in videos], cwd=work)
    _run.work = work
    _run.clip_frames = clip_frames
    return _run


@requires_tool("ffmpeg")
class TestVideomerge:
    def test_should_merge_videos_given_as_relative_paths(self, merge):
        result = merge("one.mp4", "one.mp4")

        assert result.returncode == 0, result.stderr
        assert frame_count(merge.work / "merged.mp4") == 2 * merge.clip_frames

    def test_should_merge_videos_given_as_absolute_paths(self, merge):
        result = merge(merge.work / "one.mp4", merge.work / "one.mp4")

        assert result.returncode == 0, result.stderr
        assert frame_count(merge.work / "merged.mp4") == 2 * merge.clip_frames

    def test_should_merge_a_video_whose_name_holds_a_single_quote(self, merge):
        result = merge("one.mp4", "it's two.mp4")

        assert result.returncode == 0, result.stderr
        assert frame_count(merge.work / "merged.mp4") == 2 * merge.clip_frames

    def test_should_fail_when_a_video_is_missing(self, merge):
        result = merge("one.mp4", "missing.mp4")

        assert result.returncode == 1
        assert "not found" in result.stderr
