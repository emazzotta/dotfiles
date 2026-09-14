"""Every script that defaults its input argument through `pickfile`."""
import pytest

RECORD = 'echo "$*" >> "$TOOL_LOG"'
PDFINFO = 'echo "Pages:          1"'

# script, fixture file, tool whose invocation proves the resolution, extra mocks
CONSUMERS = [
    ("pdfsplit", "doc.pdf", "gs", {"pdfinfo": PDFINFO}),
    ("pdftoimg", "doc.pdf", "convert", {}),
    ("pdfcompress", "doc.pdf", "gs", {}),
    ("pdfify", "notes.md", "pandoc", {}),
    ("videotoaudio", "clip.mp4", "ffmpeg", {}),
    ("videoloweraudio", "clip.mp4", "ffmpeg", {}),
    ("videormaudio", "clip.mp4", "ffmpeg", {}),
    ("audiospec", "song.flac", "sox", {}),
    ("imgmirror", "pic.png", "convert", {}),
    ("exifrm", "pic.png", "exiftool", {}),
    ("imgtopdf", "pic.png", "magick", {}),
    ("isotoimg", "disk.iso", "hdiutil", {"mv": "true"}),
    ("putty2pem", "key.ppk", "docker", {}),
    ("asciicast2gif", "demo.cast", "docker", {}),
    ("cert_viewer_file", "ca.pem", "openssl", {}),
]
IDS = [consumer[0] for consumer in CONSUMERS]


@pytest.fixture
def consumer(run_bash, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    log = tmp_path / "tool.log"

    def _run(script, tool, extra_mocks, args=None):
        return run_bash(
            script,
            args or [],
            env_extra={"TOOL_LOG": str(log)},
            mock_bins={tool: RECORD, **extra_mocks},
            isolate_path=True,
            cwd=work,
        )
    _run.work = work
    _run.log = log
    return _run


@pytest.mark.parametrize("script,fixture,tool,extra", CONSUMERS, ids=IDS)
def test_should_resolve_the_only_candidate_when_called_without_arguments(
    consumer, script, fixture, tool, extra
):
    (consumer.work / fixture).touch()
    (consumer.work / "unrelated.txt").touch()

    result = consumer(script, tool, extra)

    assert result.returncode == 0, result.stderr
    assert fixture in consumer.log.read_text()


@pytest.mark.parametrize("script,fixture,tool,extra", CONSUMERS, ids=IDS)
def test_should_fail_without_touching_its_tool_when_nothing_matches(
    consumer, script, fixture, tool, extra
):
    (consumer.work / "unrelated.txt").touch()

    result = consumer(script, tool, extra)

    assert result.returncode != 0
    assert not consumer.log.exists()


@pytest.mark.parametrize("script,fixture,tool,extra", CONSUMERS, ids=IDS)
def test_should_still_accept_an_explicit_argument(consumer, script, fixture, tool, extra):
    (consumer.work / fixture).touch()
    (consumer.work / f"decoy_{fixture}").touch()

    result = consumer(script, tool, extra, args=[fixture])

    assert result.returncode == 0, result.stderr
    assert fixture in consumer.log.read_text()


@pytest.mark.parametrize("script,fixture,tool,extra", CONSUMERS, ids=IDS)
def test_should_show_usage_for_the_help_flag(consumer, script, fixture, tool, extra):
    result = consumer(script, tool, extra, args=["--help"])

    assert result.returncode == 0
    assert "usage" in (result.stdout + result.stderr).lower()
    assert not consumer.log.exists()
