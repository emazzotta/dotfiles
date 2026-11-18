"""A Claude Code session's title: the newest ai-title record in its transcript, on one short visible line.

Transcripts live under ~/.claude/projects, or CLAUDE_PROJECTS when set. An unknown or unreadable title is empty.
"""
from __future__ import annotations

import json
import os
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from typing import Final
from uuid import UUID

TITLE_LIMIT: Final = 60
ELLIPSIS: Final = "\u2026"
HIDDEN_CATEGORIES: Final = frozenset({"Cc", "Cf", "Co", "Cs", "Zl", "Zp"})
TITLE_TYPE: Final = "ai-title"
TITLE_MARK: Final = TITLE_TYPE.encode()
CHUNK_BYTES: Final = 1 << 16
SCAN_LIMIT_BYTES: Final = 16 << 20


def projects_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECTS", Path.home() / ".claude" / "projects"))


def clean(title: str) -> str:
    spaced = "".join(" " if char.isspace() else char for char in title)
    visible = "".join(char for char in spaced if unicodedata.category(char) not in HIDDEN_CATEGORIES)
    collapsed = " ".join(visible.split())
    if len(collapsed) <= TITLE_LIMIT:
        return collapsed
    return collapsed[:TITLE_LIMIT - len(ELLIPSIS)].rstrip() + ELLIPSIS


def lines_from_end(path: Path) -> Iterator[bytes]:
    with path.open("rb") as handle:
        position = handle.seek(0, os.SEEK_END)
        floor = max(0, position - SCAN_LIMIT_BYTES)
        partial = b""
        while position > floor:
            step = min(CHUNK_BYTES, position - floor)
            position -= step
            handle.seek(position)
            lines = (handle.read(step) + partial).split(b"\n")
            partial = lines.pop(0)
            yield from reversed(lines)
        if position == 0:
            yield partial


def title_in(line: bytes) -> str | None:
    if TITLE_MARK not in line:
        return None
    try:
        record = json.loads(line)
    except ValueError:
        return None
    title = record.get("aiTitle") if isinstance(record, dict) and record.get("type") == TITLE_TYPE else None
    return title if isinstance(title, str) else None


def find(session: UUID) -> str:
    transcript = next(projects_dir().glob(f"*/{session}.jsonl"), None)
    if transcript is None:
        return ""
    try:
        titles = (title_in(line) for line in lines_from_end(transcript))
        return clean(next((title for title in titles if title is not None), ""))
    except OSError:
        return ""
