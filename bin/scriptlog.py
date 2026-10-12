"""Python twin of bin/prettyprint: the same colors, bullets and streams for status lines."""
from __future__ import annotations

import sys
from typing import Final

BOLD: Final = "\033[1m"
DIM: Final = "\033[2m"
RED: Final = "\033[31m"
GREEN: Final = "\033[32m"
YELLOW: Final = "\033[33m"
BLUE: Final = "\033[34m"
MAGENTA: Final = "\033[35m"
CYAN: Final = "\033[36m"
WHITE: Final = "\033[37m"
TURQUOISE: Final = "\033[38;5;80m"
RESET: Final = "\033[0m"


def hyperlink(url: str, text: str) -> str:
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


def info(message: str) -> None:
    print(f"{BOLD}{BLUE}●{RESET} {message}")


def success(message: str) -> None:
    print(f"{BOLD}{GREEN}●{RESET} {message}")


def warn(message: str) -> None:
    print(f"{BOLD}{YELLOW}●{RESET} {message}")


def error(message: str) -> None:
    print(f"{BOLD}{RED}●{RESET} {message}", file=sys.stderr)


def substep_info(message: str) -> None:
    print(f"  {BOLD}{MAGENTA}·{RESET} {message}")


def substep_success(message: str) -> None:
    print(f"  {BOLD}{CYAN}·{RESET} {message}")


def substep_error(message: str) -> None:
    print(f"  {BOLD}{RED}·{RESET} {message}", file=sys.stderr)
