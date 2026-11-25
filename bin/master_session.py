"""Which Claude Code session is the master session, the one that steers the others through `fleet`.

`fleet master on` marks it; claude-notify then sends no ping for its finished turns, since the
master reports through the flags it sets on the other sessions' windows (web-terminal UC-054).
A mark is an empty file named after the session in MARK_DIR, on the machine the session runs on.
"""
from __future__ import annotations

from pathlib import Path
from typing import Final
from uuid import UUID

MARK_DIR: Final = Path.home() / ".cache" / "claude-notify" / "master"


def mark(session: UUID, on: bool) -> None:
    path = MARK_DIR / str(session)
    if on:
        MARK_DIR.mkdir(parents=True, exist_ok=True)
        path.touch()
    else:
        path.unlink(missing_ok=True)


def is_master(session: UUID) -> bool:
    return (MARK_DIR / str(session)).is_file()
