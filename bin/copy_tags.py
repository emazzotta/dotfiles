#!/usr/bin/env python


import logging
import music_tag
import sys

logger = logging.getLogger(__name__)

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


def main(source, destination):
    source_track_metadata = music_tag.load_file(source)
    destination_track_metadata = music_tag.load_file(destination)
    copy_metadata(source_track_metadata, destination_track_metadata)
    destination_track_metadata.save()
    print(f"Copied metadata from {source} to {destination}")


def copy_metadata(source, destination):
    for tag in TAGS:
        try:
            destination[tag] = source[tag]
        except ValueError:
            pass


if __name__ == '__main__':
    logger.setLevel("DEBUG")

    if len(sys.argv) < 3:
        print(f"usage: {sys.argv[0]} <source_file> <destination_file>")
        exit(1)

    main(sys.argv[1], sys.argv[2])
