import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scriptlog import Logger, Color


def test_logger_initialization():
    logger = Logger()
    assert logger.use_timestamps is True
    assert logger.use_colors is True

    logger_no_time = Logger(use_timestamps=False)
    assert logger_no_time.use_timestamps is False


def test_colorize():
    logger = Logger(use_colors=True)
    colored = logger._colorize("test", Color.RED)
    assert colored == f"{Color.RED.value}test{Color.RESET.value}"

    logger_no_color = Logger(use_colors=False)
    plain = logger_no_color._colorize("test", Color.RED)
    assert plain == "test"


def test_log_output(capsys):
    logger = Logger(use_timestamps=False, use_colors=False)

    logger.log("Test message")
    captured = capsys.readouterr()
    assert "Test message" in captured.out


def test_success_output(capsys):
    logger = Logger(use_timestamps=False, use_colors=False)

    logger.success("Success message")
    captured = capsys.readouterr()
    assert "✓" in captured.out
    assert "Success message" in captured.out


def test_error_output(capsys):
    logger = Logger(use_timestamps=False, use_colors=False)

    logger.error("Error message")
    captured = capsys.readouterr()
    assert "ERROR:" in captured.err
    assert "Error message" in captured.err


def test_warn_output(capsys):
    logger = Logger(use_timestamps=False, use_colors=False)

    logger.warn("Warning message")
    captured = capsys.readouterr()
    assert "WARN:" in captured.out
    assert "Warning message" in captured.out


def test_info_output(capsys):
    logger = Logger(use_timestamps=False, use_colors=False)

    logger.info("Info message")
    captured = capsys.readouterr()
    assert "INFO:" in captured.out
    assert "Info message" in captured.out


def test_timestamp_format():
    logger = Logger(use_timestamps=True)
    timestamp = logger._timestamp()
    assert timestamp.startswith("[")
    assert timestamp.endswith("]")
    assert len(timestamp) > 10
