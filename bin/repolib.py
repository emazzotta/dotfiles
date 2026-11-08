"""Python twin of bin/repolib.sh: reads ~/.config/repos/ignore the way rh_ignored does."""
from __future__ import annotations

from collections.abc import Sequence
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Final

IGNORE_FILE: Final = Path(".config", "repos", "ignore")
PRUNE_SECTION: Final = "prune"


def ignore_entries(section: str) -> tuple[str, ...]:
    try:
        lines = (Path.home() / IGNORE_FILE).read_text().splitlines()
    except OSError:
        return ()
    entries: list[str] = []
    current = ""
    for entry in (line.strip() for line in lines):
        if entry.startswith("[") and entry.endswith("]"):
            current = entry
        elif entry and not entry.startswith("#") and current == f"[{section}]":
            entries.append(entry)
    return tuple(entries)


def is_ignored(path: Path, entries: Sequence[str]) -> bool:
    toplevel = str(path.resolve())
    return any(fnmatchcase(toplevel, entry) or fnmatchcase(toplevel, f"*/{entry}") for entry in entries)
