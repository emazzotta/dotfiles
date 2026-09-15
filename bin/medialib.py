"""Input collection, output naming and duration formatting shared by the media and image scripts."""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from glob import glob
from pathlib import Path

from scriptlog import Logger

logger = Logger()

AUDIO_EXTS = ["mp3", "m4a", "aac", "flac", "wav", "aif", "aiff", "alac", "ogg", "opus", "wma", "ape", "wv"]
VIDEO_EXTS = ["mp4", "m4v", "mov", "mkv", "avi", "webm", "mpg", "mpeg", "wmv", "flv", "3gp", "mts", "m2ts"]


@dataclass(frozen=True)
class OutputNaming:
    extension: str
    name_suffix: str = ""
    conflict_suffix: str = "_converted"


def format_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m {secs}s"


def list_inputs(path: Path, extensions: list[str]) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        files = []
        for ext in extensions:
            files.extend(Path(p) for p in glob(str(path / f"**/*.{ext}"), recursive=True))
            files.extend(Path(p) for p in glob(str(path / f"**/*.{ext.upper()}"), recursive=True))
        return sorted(set(files))
    logger.error(f"Input not found: {path}")
    sys.exit(1)


def find_in_cwd(extensions: list[str]) -> list[Path]:
    cwd = Path.cwd()
    matches: set[Path] = set()
    for ext in extensions:
        for pattern in (f"*.{ext}", f"*.{ext.upper()}"):
            matches.update(path for path in cwd.glob(pattern) if path.is_file())
    return sorted(matches)


def can_prompt() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty() and shutil.which("gum") is not None


def pick_from(candidates: list[Path], label: str) -> list[Path]:
    if not can_prompt():
        logger.error(f"Several {label} files here; pass -i to choose")
        sys.exit(1)
    convert_all = f"Convert all ({len(candidates)})"
    result = subprocess.run(
        ["gum", "choose", "--header", f"Select {label} input:",
         convert_all, *(path.name for path in candidates)],
        capture_output=True, text=True,
    )
    chosen = result.stdout.strip()
    if not chosen:
        logger.error("Nothing selected")
        sys.exit(1)
    if chosen == convert_all:
        return candidates
    return [Path.cwd() / chosen]


def resolve_inputs_or_pick(extensions: list[str], label: str) -> list[Path]:
    candidates = find_in_cwd(extensions)
    if not candidates:
        logger.error(f"No {label} files in {Path.cwd()}")
        sys.exit(1)
    if len(candidates) == 1:
        return candidates
    return pick_from(candidates, label)


def collect_inputs(paths: list[Path], extensions: list[str]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        files.extend(list_inputs(path, extensions))
    return list(dict.fromkeys(files))


def resolve_output_path(input_file: Path, output_dir: Path | None, naming: OutputNaming) -> Path:
    base_dir = output_dir or input_file.parent
    output_path = base_dir / f"{input_file.stem}{naming.name_suffix}{naming.extension}"

    if not output_path.exists():
        return output_path

    response = input(f"File exists: {output_path}\nOverwrite? [y/N/a] "
                     f"(N=add {naming.conflict_suffix}, a=abort): ").lower()
    if response == "a":
        logger.error("Aborted")
        sys.exit(1)
    if response == "y":
        return output_path

    counter = ""
    while True:
        candidate = base_dir / f"{input_file.stem}{naming.conflict_suffix}{counter}{naming.extension}"
        if not candidate.exists():
            return candidate
        counter = "_2" if not counter else f"_{int(counter[1:]) + 1}"
