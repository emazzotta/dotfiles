import sys
import time
from enum import Enum
from typing import Optional


class Color(Enum):
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    MAGENTA = "\033[0;35m"
    CYAN = "\033[0;36m"
    RESET = "\033[0m"


class Logger:
    def __init__(self, use_timestamps: bool = True, use_colors: bool = True):
        self.use_timestamps = use_timestamps
        self.use_colors = use_colors

    def _timestamp(self) -> str:
        if not self.use_timestamps:
            return ""
        return f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]"

    def _colorize(self, message: str, color: Color) -> str:
        if not self.use_colors:
            return message
        return f"{color.value}{message}{Color.RESET.value}"

    def log(self, message: str, prefix: Optional[str] = None) -> None:
        timestamp = self._colorize(self._timestamp(), Color.GREEN) if self._timestamp() else ""
        prefix_str = f" {prefix}:" if prefix else ""
        output = f"{timestamp}{prefix_str} {message}" if timestamp else f"{prefix_str} {message}".lstrip()
        print(output)

    def success(self, message: str) -> None:
        timestamp = self._colorize(self._timestamp(), Color.GREEN) if self._timestamp() else ""
        msg = self._colorize("✓", Color.GREEN)
        output = f"{timestamp} {msg} {message}" if timestamp else f"{msg} {message}"
        print(output)

    def error(self, message: str) -> None:
        timestamp = self._colorize(self._timestamp(), Color.RED) if self._timestamp() else ""
        prefix = self._colorize("ERROR:", Color.RED)
        output = f"{timestamp} {prefix} {message}" if timestamp else f"{prefix} {message}"
        print(output, file=sys.stderr)

    def warn(self, message: str) -> None:
        timestamp = self._colorize(self._timestamp(), Color.YELLOW) if self._timestamp() else ""
        prefix = self._colorize("WARN:", Color.YELLOW)
        output = f"{timestamp} {prefix} {message}" if timestamp else f"{prefix} {message}"
        print(output)

    def info(self, message: str) -> None:
        timestamp = self._colorize(self._timestamp(), Color.GREEN) if self._timestamp() else ""
        prefix = self._colorize("INFO:", Color.CYAN)
        output = f"{timestamp} {prefix} {message}" if timestamp else f"{prefix} {message}"
        print(output)

    def debug(self, message: str) -> None:
        timestamp = self._colorize(self._timestamp(), Color.MAGENTA) if self._timestamp() else ""
        prefix = self._colorize("DEBUG:", Color.MAGENTA)
        output = f"{timestamp} {prefix} {message}" if timestamp else f"{prefix} {message}"
        print(output)


_default_logger: Optional[Logger] = None


def get_logger(use_timestamps: bool = True, use_colors: bool = True) -> Logger:
    global _default_logger
    if _default_logger is None:
        _default_logger = Logger(use_timestamps=use_timestamps, use_colors=use_colors)
    return _default_logger


def log(message: str, prefix: Optional[str] = None) -> None:
    get_logger().log(message, prefix)


def success(message: str) -> None:
    get_logger().success(message)


def error(message: str) -> None:
    get_logger().error(message)


def warn(message: str) -> None:
    get_logger().warn(message)


def info(message: str) -> None:
    get_logger().info(message)


def debug(message: str) -> None:
    get_logger().debug(message)
