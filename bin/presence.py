"""Who sits at a web terminal right now, read from ~/.claude/presence.

Each file in the folder is one web-terminal instance (a name starting with a dot is a temporary
write and is skipped). Each line is `<epoch-seconds> <kind>` with kind
`computer` or `phone`, and stays fresh for 120 seconds. A malformed line is ignored. A missing or
unreadable folder is `unknown`, which callers treat as away.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable
from datetime import timedelta
from enum import Enum
from pathlib import Path
from typing import Final

PRESENCE_DIR: Final = Path.home() / ".claude" / "presence"
FRESH_FOR: Final = timedelta(seconds=120)
LINE: Final = re.compile(r"([0-9]{1,12})\s+(computer|phone)")


class Presence(Enum):
    COMPUTER = "computer"
    PHONE = "phone"
    AWAY = "away"
    UNKNOWN = "unknown"

    @property
    def attended(self) -> bool:
        return self in (Presence.COMPUTER, Presence.PHONE)


def fresh_kinds(lines: Iterable[str], now: float) -> set[Presence]:
    kinds = set()
    for line in lines:
        match = LINE.fullmatch(line.strip())
        if match and now - int(match.group(1)) < FRESH_FOR.total_seconds():
            kinds.add(Presence(match.group(2)))
    return kinds


def classify(lines: Iterable[str] | None, now: float) -> Presence:
    if lines is None:
        return Presence.UNKNOWN
    kinds = fresh_kinds(lines, now)
    if Presence.COMPUTER in kinds:
        return Presence.COMPUTER
    return Presence.PHONE if Presence.PHONE in kinds else Presence.AWAY


def file_lines(path: Path) -> list[str]:
    try:
        return path.read_text(errors="replace").splitlines()
    except OSError:
        return []


def folder_lines(folder: Path) -> list[str] | None:
    try:
        files = [entry for entry in folder.iterdir() if not entry.name.startswith(".") and entry.is_file()]
    except OSError:
        return None
    return [line for entry in files for line in file_lines(entry)]


def current(clock: Callable[[], float] = time.time) -> Presence:
    return classify(folder_lines(PRESENCE_DIR), clock())
