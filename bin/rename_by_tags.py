#!/usr/bin/env python


import logging
import music_tag
import sys
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)


def main(source):
    source_track_metadata = music_tag.load_file(source)
    filename = compose_filename(source_track_metadata)
    source_path = Path(source)
    source_path.rename(
        Path(source_path.parent, f'{filename}{source_path.suffix}')
    )
    print(f"Renamed via metadata from [{source}] to [{filename}]")


def compose_filename(metadata):
    return normalize_special_characters(f"{metadata['artist']} - {metadata['tracktitle']}")


def normalize_special_characters(new_track_name):
    normalized = unicodedata.normalize('NFD', new_track_name).encode('ASCII', 'ignore').decode()
    normalized = normalized.replace("/", "_")
    normalized = normalized.replace("?", "...")
    if new_track_name != normalized:
        logger.warning(f'Normalized track name: {new_track_name} => {normalized}')
    return normalized


if __name__ == '__main__':
    logger.setLevel("DEBUG")

    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <source_file>")
        exit(1)

    main(sys.argv[1])
