#!/usr/bin/env python


import argparse
import logging
import os
import re
import unicodedata
from itertools import chain
from pathlib import Path

import music_tag

'''
New track procedure:

1. Add missing artwork to new mp3 files
2. Put mp3 files in "Original" folder in correct subdirectory based on genre
3. Run Platinum Notes with new files
4. Run this tag fixer
'''

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)

'''
Assumption:
Path for original files contains "Original" and platinum notes path contains "Platinum_Notes"
'''
ORIGINAL_TRACKS_PATH = os.environ.get('DJ_TRACKS')
PLATINUM_NOTES_TRACKS_PATH = os.environ.get('DJ_PLATINUM_NOTES_TRACKS')
ORIGINAL_TRACKS = chain(Path(ORIGINAL_TRACKS_PATH).glob('**/*.mp3'), Path(ORIGINAL_TRACKS_PATH).glob('**/*.wav'))

'''
Hint regarding Mixed In Key:
1. Import in Mixed in Key
2. Import Playlist in RekordBox
3. Export rekordbox.xml
4. Export Mixed In Key Cue Points
5. Reload rekordbox.xml Playlists and import new "Mixed in Key" items
6. Reload tags of tracks if necessary
'''

TAGS = [
    'album',
    'albumartist',
    'artist',
    'comment',
    'compilation',
    'composer',
    'discnumber',
    'genre',
    'lyrics',
    'totaldiscs',
    'totaltracks',
    'tracknumber',
    'tracktitle',
    'year',
    'isrc',
    'artwork'
]


def main():
    parser = argparse.ArgumentParser(description='Perform audio tags operations')

    # Parameter: autofix
    parser.add_argument('--autofix', action='store_true', help='Autofix needs no additional parameters')

    # Parameter: copy_tag
    parser.add_argument('--copy_tag', nargs=2, metavar=('SRC', 'DEST'),
                        help='Copy tag needs a source and destination file')

    # Parameter: rename_by_tag
    parser.add_argument('--rename_by_tag', help='Rename by tag just needs a source file')

    args = parser.parse_args()

    if args.autofix:
        autofix()
    elif args.copy_tag:
        src, dest = args.copy_tag
        copy_tag(src, dest)
    elif args.rename_by_tag:
        rename_by_tag(args.rename_by_tag)
    else:
        print("Please provide valid parameters.")


def autofix():
    for original_track_path in ORIGINAL_TRACKS:
        logger.info(f"Processing {original_track_path}")
        original_track_metadata = music_tag.load_file(original_track_path)
        trim_tags(original_track_metadata)
        original_track_metadata.save()

        new_track_name = compose_filename(original_track_metadata)
        platinum_notes_track_path = Path(
            f"{original_track_path.parent}".replace(ORIGINAL_TRACKS_PATH, PLATINUM_NOTES_TRACKS_PATH),
            f'{original_track_path.stem}_PN.wav')
        original_track_path.rename(Path(original_track_path.parent, f'{new_track_name}{original_track_path.suffix}'))

        if platinum_notes_track_path.exists():
            platinum_notes_track_metadata = music_tag.load_file(platinum_notes_track_path)
            copy_metadata(platinum_notes_track_metadata, original_track_metadata)
            platinum_notes_track_metadata.save()
            platinum_notes_track_path.rename(
                Path(platinum_notes_track_path.parent, f'{new_track_name}_PN{platinum_notes_track_path.suffix}'))


def copy_tag(src, dest):
    if not os.path.exists(src):
        print(f"Source file {src} does not exist.")
        return
    if not os.path.exists(dest):
        print(f"Destination file {dest} does not exist.")
        return

    source_track_metadata = music_tag.load_file(src)
    destination_track_metadata = music_tag.load_file(dest)
    copy_metadata(source_track_metadata, destination_track_metadata)
    destination_track_metadata.save()
    print(f"Copied metadata from {src} to {dest}")


def rename_by_tag(src):
    if not os.path.exists(src):
        print(f"Source file {src} does not exist.")
        return

    source_track_metadata = music_tag.load_file(src)
    filename = compose_filename(source_track_metadata)
    source_path = Path(src)
    source_path.rename(
        Path(source_path.parent, f'{filename}{source_path.suffix}')
    )
    print(f"Renamed via metadata from [{src}] to [{filename}]")


def compose_filename(metadata):
    return normalize_special_characters(f"{metadata['artist']} - {metadata['tracktitle']}")


def normalize_special_characters(new_track_name):
    normalized = unicodedata.normalize('NFD', new_track_name).encode('ASCII', 'ignore').decode()
    normalized = normalized.replace("/", "_")
    normalized = normalized.replace("?", "...")
    if new_track_name != normalized:
        logger.warning(f'Normalized track name: {new_track_name} => {normalized}')
    return normalized


def copy_metadata(destination, source):
    for tag in TAGS:
        try:
            destination[tag] = source[tag]
        except ValueError:
            pass


def trim_tags(track_metadata):
    for tag in TAGS:
        try:
            track_metadata[tag] = trim(track_metadata[tag])
        except ValueError:
            pass


def trim(metadata):
    return re.sub(r'^\s+|\s+$', '', metadata.first) if isinstance(metadata.first, str) else metadata


if __name__ == '__main__':
    logger.setLevel("DEBUG")
    main()
