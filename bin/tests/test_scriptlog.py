import pytest


@pytest.fixture
def scriptlog(load_script):
    mod = load_script("scriptlog.py")
    mod.reset_logger()
    yield mod
    mod.reset_logger()


class TestLoggerInit:
    def test_defaults(self, scriptlog):
        logger = scriptlog.Logger()
        assert logger.use_timestamps is True
        assert logger.use_colors is True

    def test_custom_flags(self, scriptlog):
        logger = scriptlog.Logger(use_timestamps=False, use_colors=False)
        assert logger.use_timestamps is False
        assert logger.use_colors is False


class TestColorize:
    def test_with_colors(self, scriptlog):
        logger = scriptlog.Logger(use_colors=True)
        colored = logger._colorize("test", scriptlog.Color.RED)
        assert colored == f"{scriptlog.Color.RED.value}test{scriptlog.Color.RESET.value}"

    def test_without_colors(self, scriptlog):
        logger = scriptlog.Logger(use_colors=False)
        assert logger._colorize("test", scriptlog.Color.RED) == "test"


class TestTimestamp:
    def test_format(self, scriptlog):
        logger = scriptlog.Logger(use_timestamps=True)
        ts = logger._timestamp()
        assert ts.startswith("[")
        assert ts.endswith("]")
        assert len(ts) > 10

    def test_disabled(self, scriptlog):
        logger = scriptlog.Logger(use_timestamps=False)
        assert logger._timestamp() == ""


class TestLoggerOutput:
    @pytest.fixture
    def logger(self, scriptlog):
        return scriptlog.Logger(use_timestamps=False, use_colors=False)

    def test_log(self, logger, capsys):
        logger.log("Test message")
        assert "Test message" in capsys.readouterr().out

    def test_log_with_prefix(self, logger, capsys):
        logger.log("test", prefix="CUSTOM")
        captured = capsys.readouterr().out
        assert "CUSTOM:" in captured
        assert "test" in captured

    def test_success(self, logger, capsys):
        logger.success("ok")
        captured = capsys.readouterr().out
        assert "✓" in captured
        assert "ok" in captured

    def test_error(self, logger, capsys):
        logger.error("fail")
        captured = capsys.readouterr().err
        assert "ERROR:" in captured
        assert "fail" in captured

    def test_warn(self, logger, capsys):
        logger.warn("warning")
        captured = capsys.readouterr().out
        assert "WARN:" in captured
        assert "warning" in captured

    def test_info(self, logger, capsys):
        logger.info("information")
        captured = capsys.readouterr().out
        assert "INFO:" in captured
        assert "information" in captured

    def test_debug(self, logger, capsys):
        logger.debug("debug msg")
        captured = capsys.readouterr().out
        assert "DEBUG:" in captured
        assert "debug msg" in captured


class TestSingleton:
    def test_returns_same_instance(self, scriptlog):
        l1 = scriptlog.get_logger(use_timestamps=False)
        l2 = scriptlog.get_logger(use_timestamps=True)
        assert l1 is l2

    def test_reset_allows_reconfiguration(self, scriptlog):
        l1 = scriptlog.get_logger(use_timestamps=False)
        scriptlog.reset_logger()
        l2 = scriptlog.get_logger(use_timestamps=True)
        assert l2 is not l1
        assert l2.use_timestamps is True


class TestModuleFunctions:
    def test_log(self, scriptlog, capsys):
        scriptlog.log("module log")
        assert "module log" in capsys.readouterr().out

    def test_success(self, scriptlog, capsys):
        scriptlog.success("ok")
        assert "✓" in capsys.readouterr().out

    def test_error(self, scriptlog, capsys):
        scriptlog.error("fail")
        assert "ERROR:" in capsys.readouterr().err
