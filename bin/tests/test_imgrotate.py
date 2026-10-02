import pytest

RECORD_ARGS = 'printf "%s\\n" "$@" >> "$TOOL_LOG"'


@pytest.fixture
def imgrotate(run_bash, tmp_path):
    log = tmp_path / "magick.log"

    def _run(*args, magick=RECORD_ARGS):
        return run_bash("imgrotate", list(args), env_extra={"TOOL_LOG": str(log)},
                        mock_bins={"magick": magick}, isolate_path=True, cwd=tmp_path)
    _run.calls = lambda: log.read_text().splitlines() if log.exists() else []
    return _run


@pytest.mark.parametrize("rotation", ["90", "-90", "12.5"])
def should_rotate_a_copy_of_the_image_as_it_displays(imgrotate, tmp_path, rotation):
    (tmp_path / "my pic.png").touch()

    result = imgrotate("my pic.png", rotation)

    assert result.returncode == 0, result.stderr
    assert imgrotate.calls() == ["my pic.png", "-auto-orient", "-background", "none",
                                 "-rotate", rotation, "my pic_rotated.png"]


@pytest.mark.parametrize("args", [[], ["pic.png"], ["missing.png", "90"], ["pic.png", "ninety"]],
                         ids=["no arguments", "no rotation", "missing file", "rotation not a number"])
def should_reject_bad_input_without_running_magick(imgrotate, tmp_path, args):
    (tmp_path / "pic.png").touch()

    result = imgrotate(*args)

    assert result.returncode == 1
    assert imgrotate.calls() == []


def should_fail_without_claiming_success_when_magick_fails(imgrotate, tmp_path):
    (tmp_path / "pic.png").touch()

    result = imgrotate("pic.png", "90", magick="exit 1")

    assert result.returncode == 1
    assert "saved" not in result.stdout


def should_show_usage_for_the_help_flag(imgrotate):
    result = imgrotate("--help")

    assert result.returncode == 0
    assert "usage" in result.stdout.lower()
    assert imgrotate.calls() == []
