"""TSV cache, display formatting and fzf plumbing for session pickers.

Shared by claude-resume and opencode-resume. Ranking lives in session_search.

fzf runs with --disabled: matching and ordering are ours, so a `change`
binding re-runs the ranked search on every keystroke and reloads the list.
That is what lets phrase matches float to the top as the query is typed.
"""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from subprocess import PIPE, run
from typing import Final, Sequence

TITLE_WIDTH: Final = 60
AGO_WIDTH: Final = 12
PREVIEW_TURN_LIMIT: Final = 60
PREVIEW_TEXT_LIMIT: Final = 600

MINUTE: Final = 60
HOUR: Final = 60 * MINUTE
DAY: Final = 24 * HOUR
DAYS_PER_MONTH: Final = 30
DAYS_PER_YEAR: Final = 365

ELLIPSIS: Final = "…"
HIGHLIGHT_ON: Final = "\033[43m\033[30m"
RESET: Final = "\033[0m"

FZF_HEADER_HINT: Final = "phrase matches first | space = AND  ^title  title$  !exclude  a|b"


@dataclass(frozen=True)
class CacheEntry:
    stamp: int
    title: str
    content: str


def load_cache(path: Path, header: str) -> dict[str, CacheEntry]:
    """Read the TSV index, or return empty when absent, unreadable or stale-format."""
    entries: dict[str, CacheEntry] = {}
    try:
        with path.open() as f:
            if f.readline().strip() != header:
                return {}
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) != 4:
                    continue
                stamp, sid, title, content = parts
                try:
                    entries[sid] = CacheEntry(int(stamp), title, content)
                except ValueError:
                    continue
    except OSError:
        return {}
    return entries


def save_cache(path: Path, header: str, entries: dict[str, CacheEntry]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w") as f:
            f.write(f"{header}\n")
            for sid, entry in entries.items():
                f.write(f"{entry.stamp}\t{sid}\t{_untab(entry.title)}\t{_untab(entry.content)}\n")
        tmp.replace(path)
    except OSError:
        tmp.unlink(missing_ok=True)


def _untab(text: str) -> str:
    return text.replace("\t", " ").replace("\n", " ")


def flatten(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def format_ago(epoch_seconds: int) -> str:
    diff = int(time.time() - epoch_seconds)
    if diff < MINUTE:
        return "just now"
    if diff < HOUR:
        return f"{diff // MINUTE}m ago"
    if diff < DAY:
        return f"{diff // HOUR}h ago"
    days = diff // DAY
    if days == 1:
        return "yesterday"
    if days < DAYS_PER_MONTH:
        return f"{days}d ago"
    if days < DAYS_PER_YEAR:
        return f"{days // DAYS_PER_MONTH}mo ago"
    return f"{days // DAYS_PER_YEAR}y ago"


def format_display(title: str, epoch_seconds: int, extra: str = "") -> str:
    shortened = title if len(title) <= TITLE_WIDTH else title[: TITLE_WIDTH - 1] + ELLIPSIS
    ago = format_ago(epoch_seconds)
    if extra:
        return f"{shortened:<{TITLE_WIDTH}}  {ago:<{AGO_WIDTH}}  {extra}"
    return f"{shortened:<{TITLE_WIDTH}}  {ago}"


def format_row(display: str, sid: str) -> str:
    """One fzf line: visible column, then the id the preview and selection use."""
    return f"{_untab(display)}\t{sid}"


def write_rows(rows: Sequence[str]) -> None:
    """Feed fzf a reloaded list - no rows must mean no lines, not one blank one."""
    sys.stdout.writelines(f"{row}\n" for row in rows)


def truncate_turn(text: str) -> str:
    return text if len(text) <= PREVIEW_TEXT_LIMIT else text[:PREVIEW_TEXT_LIMIT] + ELLIPSIS


def highlight_matches(text: str, tokens: Sequence[str]) -> str:
    if not tokens:
        return text
    pattern = re.compile("|".join(re.escape(token) for token in tokens), re.IGNORECASE)
    return pattern.sub(lambda m: f"{HIGHLIGHT_ON}{m.group(0)}{RESET}", text)


@dataclass(frozen=True)
class PickerCommands:
    preview: str
    reload: str


def build_fzf_args(query: str, header: str, commands: PickerCommands) -> list[str]:
    return [
        "fzf",
        "--delimiter", "\t",
        "--with-nth", "1",
        "--disabled",
        "--query", query,
        "--bind", f"change:reload:{commands.reload}",
        "--height", "100%",
        "--layout=reverse",
        "--border=rounded",
        "--margin=1",
        "--padding=1",
        "--prompt", "▶ ",
        "--pointer", "❯",
        "--marker", "✓",
        "--cycle",
        "--ansi",
        "--preview", commands.preview,
        "--preview-window", "right:60%:wrap",
        "--header", header,
        "--color=bg+:#2d1b3d,fg+:#ffffff,hl:#ff69b4,hl+:#ff79c6,prompt:#e75480,"
        "pointer:#e75480,marker:#bd93f9,header:#7d56f4,border:#7d56f4,info:#8b8b8b,spinner:#ff69b4",
    ]


def pick(rows: Sequence[str], query: str, header: str, commands: PickerCommands) -> str | None:
    """Run fzf and return the selected session id, or None when cancelled."""
    try:
        result = run(
            build_fzf_args(query, header, commands),
            input="\n".join(rows), text=True, stdout=PIPE,
        )
    except FileNotFoundError as e:
        raise FileNotFoundError("fzf not found on PATH") from e
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip().split("\t")[-1]


def split_args(argv: Sequence[str]) -> tuple[list[str], list[str]]:
    """Split our argv from the args forwarded to claude/opencode after `--`."""
    argv = list(argv)
    if "--" in argv:
        index = argv.index("--")
        return argv[:index], argv[index + 1 :]
    return argv, []
