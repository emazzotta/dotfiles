"""Input collection, output naming and duration formatting shared by the media scripts."""
from __future__ import annotations

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
