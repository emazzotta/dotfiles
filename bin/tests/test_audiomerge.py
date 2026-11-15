import subprocess
import wave

import pytest

from bin.tests.conftest import requires_tool

SAMPLE_RATE = 44100


def make_tone(path, seconds):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-ar", str(SAMPLE_RATE), "-ac", "2", str(path)], check=True)


def frames(path):
    with wave.open(str(path)) as merged:
        return merged.getnframes()


@pytest.fixture
def audiomerge(run_bash, tmp_path):
    work = tmp_path / "work"
    work.mkdir()

    def _run(*files):
        return run_bash("audiomerge", ["-o", "merged", *files], cwd=work,
                        env_extra={"TMPDIR": str(tmp_path)})
    _run.work = work
    return _run


@requires_tool("ffmpeg")
class TestAudiomerge:
    def should_merge_a_file_whose_name_contains_an_apostrophe(self, audiomerge):
        make_tone(audiomerge.work / "Don't Stop.wav", 0.3)
        make_tone(audiomerge.work / "other.wav", 0.2)

        result = audiomerge("Don't Stop.wav", "other.wav")

        assert result.returncode == 0, result.stderr
        assert frames(audiomerge.work / "merged.wav") == pytest.approx(0.5 * SAMPLE_RATE, abs=SAMPLE_RATE * 0.05)

    def should_keep_both_files_when_two_inputs_share_a_basename(self, audiomerge):
        make_tone(audiomerge.work / "a" / "01.wav", 0.2)
        make_tone(audiomerge.work / "b" / "01.wav", 0.5)

        result = audiomerge("a/01.wav", "b/01.wav")

        assert result.returncode == 0, result.stderr
        assert frames(audiomerge.work / "merged.wav") == pytest.approx(0.7 * SAMPLE_RATE, abs=SAMPLE_RATE * 0.05)
