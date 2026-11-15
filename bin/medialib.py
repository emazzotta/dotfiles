"""Input collection, output naming, duration formatting and the ffmpeg batch flow shared by the media and image scripts."""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from glob import escape, glob
from pathlib import Path

import scriptlog as logger


AUDIO_EXTS = ["mp3", "m4a", "aac", "flac", "wav", "aif", "aiff", "alac", "ogg", "opus", "wma", "ape", "wv"]
VIDEO_EXTS = ["mp4", "m4v", "mov", "mkv", "avi", "webm", "mpg", "mpeg", "wmv", "flv", "3gp", "mts", "m2ts"]


@dataclass(frozen=True)
class OutputNaming:
    extension: str
    name_suffix: str = ""
    conflict_suffix: str = "_converted"


@dataclass(frozen=True)
class MediaKind:
    label: str
    extensions: list[str]


AUDIO = MediaKind("audio", AUDIO_EXTS)
VIDEO = MediaKind("video", VIDEO_EXTS)


@dataclass(frozen=True)
class FfmpegJob:
    cmd: list[str]
    output_file: Path


@dataclass(frozen=True)
class BatchSpec:
    media: MediaKind
    task: str
    doing: str
    done: str
    plan: Callable[[Path, Path | None], FfmpegJob | None]


def format_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m {secs}s"


LOSSY_AUDIO_QUALITY_ARGS = {
    "mp3": ["-b:a", "320k"],
    "m4a": ["-b:a", "256k"],
    "aac": ["-b:a", "256k"],
    "opus": ["-b:a", "128k"],
    "ogg": ["-q:a", "6"],
}


def list_inputs(path: Path, extensions: list[str]) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        files = []
        root = escape(str(path))
        for ext in extensions:
            files.extend(Path(p) for p in glob(f"{root}/**/*.{ext}", recursive=True))
            files.extend(Path(p) for p in glob(f"{root}/**/*.{ext.upper()}", recursive=True))
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
        stdout=subprocess.PIPE, text=True,
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


def prepare_output_dir(output_path: str | None) -> Path | None:
    if not output_path:
        return None
    output_dir = Path(output_path).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def gather_inputs(media: MediaKind, input_args: list[str] | None) -> list[Path]:
    if input_args:
        sources = [Path(arg).expanduser().resolve() for arg in input_args]
        inputs = collect_inputs(sources, media.extensions)
    else:
        inputs = resolve_inputs_or_pick(media.extensions, media.label)
    if not inputs:
        logger.error(f"No {media.label} files found")
        sys.exit(1)
    return inputs


def process_file(spec: BatchSpec, input_file: Path, output_dir: Path | None,
                 delete_original: bool, progress: str) -> bool:
    job = spec.plan(input_file, output_dir)
    if job is None:
        return False
    names = f"{input_file.name} -> {job.output_file.name}"
    logger.info(f"\n{progress} {spec.doing}: {names}")
    print()

    start_time = time.time()
    try:
        subprocess.run(job.cmd, check=True)
        elapsed = time.time() - start_time
        print()
        logger.success(f"{spec.done} in {format_time(elapsed)}: {names}")
        if delete_original:
            input_file.unlink(missing_ok=True)
        return True
    except subprocess.CalledProcessError:
        print()
        logger.error(f"Failed: {input_file.name}")
        return False


def run_batch(spec: BatchSpec, input_args: list[str] | None, output_path: str | None,
              delete_original: bool) -> None:
    output_dir = prepare_output_dir(output_path)
    inputs = gather_inputs(spec.media, input_args)
    total = len(inputs)
    logger.info(f"Found {total} {spec.media.label} file(s) to {spec.task}")

    succeeded = 0
    batch_start_time = time.time()
    for number, input_file in enumerate(inputs, 1):
        if process_file(spec, input_file, output_dir, delete_original, f"[{number}/{total}]"):
            succeeded += 1

    batch_elapsed = time.time() - batch_start_time
    print()
    logger.info(f"Summary: {succeeded} succeeded, {total - succeeded} failed, "
                f"{total} total in {format_time(batch_elapsed)}")
