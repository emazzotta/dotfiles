"""Image discovery shared by the image bin scripts.

Uses pathlib globbing, which descends into dotted directories and matches
dotted filenames - unlike the glob module that medialib uses for A/V.
"""
from __future__ import annotations

import sys
from pathlib import Path

from scriptlog import Logger

logger = Logger()


def find_images(directory: Path, extensions: list[str]) -> list[Path]:
    patterns = list(extensions) + [extension.upper() for extension in extensions]
    images: list[Path] = []
    for pattern in patterns:
        images.extend(directory.glob(f"**/*.{pattern}"))
    return images


def collect_images(inputs: list[Path], extensions: list[str]) -> list[Path]:
    image_files: list[Path] = []
    for input_path in inputs:
        if input_path.is_file():
            image_files.append(input_path)
        elif input_path.is_dir():
            image_files.extend(find_images(input_path, extensions))
        else:
            logger.error(f"Input '{input_path}' not found!")
            sys.exit(1)
    return list(dict.fromkeys(image_files))
