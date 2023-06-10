#!/usr/bin/env python


import argparse
import base64
import logging
import os
import re
import unicodedata
from itertools import chain
from pathlib import Path

import music_tag
import requests

'''
New track procedure:

1. Add missing artwork to new mp3 files
2. Put mp3 files in "Original" folder in correct subdirectory based on genre
3. Run Platinum Notes with new files
4. Run this tag fixer
'''

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)

ORIGINAL_TRACKS_PATH = os.environ.get('DJ_TRACKS', f'${os.environ.get("HOME")}/Google_Drive/Music/DJing/Tracks')
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
    parser.add_argument('--autofix', action='store_true', help='Autofix needs no additional parameters')
    parser.add_argument(
        '--copy-tag',
        nargs=2,
        metavar=('SRC', 'DEST'),
        help='Copy tag needs a source and destination file'
    )
    parser.add_argument(
        '--rename-by-tag',
        help='Rename by tag just needs a source file',
        nargs=1,
        metavar='SRC'
    )
    parser.add_argument(
        '--full-tag-optimizer',
        help='Full tag optimizer option needs a source file',
        nargs=1,
        metavar='SRC'
    )

    args = parser.parse_args()

    if args.autofix:
        autofix()
    elif args.copy_tag:
        src, dest = args.copy_tag
        copy_tag(src, dest)
    elif args.rename_by_tag:
        src, = args.rename_by_tag
        rename_by_tag(src)
    elif args.full_tag_optimizer:
        src, = args.full_tag_optimizer
        full_tag_optimizer(src)
    else:
        print("Please provide valid parameters.")


def autofix():
    for src in ORIGINAL_TRACKS:
        logger.info(f"[AUTOFIX] Processing {src}")
        original_track_metadata = music_tag.load_file(src)
        clean_all_tags(original_track_metadata)
        original_track_metadata.save()
        new_track_name = compose_filename(original_track_metadata)
        src.rename(Path(src.parent, f'{new_track_name}{src.suffix}'))


def copy_tag(src, dest):
    if not os.path.exists(src):
        print(f"Source file {src} does not exist.")
        return
    if not os.path.exists(dest):
        print(f"Destination file {dest} does not exist.")
        return

    logger.info(f"[COPY_TAG] Processing {src} / {dest}")
    source_track_metadata = music_tag.load_file(src)
    destination_track_metadata = music_tag.load_file(dest)
    copy_metadata(source_track_metadata, destination_track_metadata)
    destination_track_metadata.save()
    print(f"Copied metadata from {src} to {dest}")


def rename_by_tag(src):
    if not os.path.exists(src):
        print(f"Source file {src} does not exist.")
        return

    logger.info(f"[RENAME_BY_TAG] Processing {src}")
    source_track_metadata = music_tag.load_file(src)
    filename = compose_filename(source_track_metadata)
    source_path = Path(src)
    source_path.rename(
        Path(source_path.parent, f'{filename}{source_path.suffix}')
    )
    print(f"Renamed via metadata from [{src}] to [{filename}]")


def full_tag_optimizer(src):
    if not os.path.exists(src):
        print(f"Source file {src} does not exist.")
        return

    logger.info(f"[FULL_TAG_OPTIMIZER] Processing {src}")
    original_track_metadata = music_tag.load_file(src)
    clean_all_tags(original_track_metadata)
    original_track_metadata.save()

    set_missing_metadata_from_filename(src, original_track_metadata)

    if not original_track_metadata['artwork'].first:
        download_and_set_cover_photo(original_track_metadata)
    original_track_metadata.save()

    rename_by_tag(src)


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


def clean_all_tags(track_metadata):
    for tag in TAGS:
        try:
            if isinstance(track_metadata[tag].first, str):
                track_metadata[tag] = clean_string(track_metadata[tag].first)
        except ValueError:
            pass


def clean_string(dirty_string):
    cleaned_metadata = re.sub(r'\[www\.slider\.kz]', '', dirty_string)
    trimmed_metadata = re.sub(r'\s+', ' ', cleaned_metadata)
    return trimmed_metadata


def set_missing_metadata_from_filename(src, track_metadata):
    src = Path(src)
    new_track_name = src.stem.replace("_", " ")
    new_track_name = re.sub(r'^\d+\s+', '', new_track_name)
    new_track_name = clean_string(new_track_name)
    src.rename(Path(src.parent, f'{new_track_name}{src.suffix}'))

    if not track_metadata['artist'].first or not track_metadata['tracktitle'].first:
        if ' - ' in new_track_name:
            artist, title = map(str.strip, new_track_name.split(' - ', 1))
            if not track_metadata['artist'].first:
                track_metadata['artist'] = artist
            if not track_metadata['tracktitle'].first:
                track_metadata['tracktitle'] = title


def download_and_set_cover_photo(track_metadata):
    query = f"{track_metadata['artist'].first} {track_metadata['tracktitle'].first} cover art"
    url = f"https://www.google.com/search?q={query}&tbm=isch"

    HEADERS = {"content-type": "image/png"}
    html = requests.get(url, headers=HEADERS).text
    soup = BeautifulSoup(html, "html.parser")

    image_url = soup.find_all('img')[1]['src']
    response = requests.get(image_url)

    track_metadata['artwork'].set_data(response.content, fmt='image/jpeg')

def get_album_art(album_id, token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"https://api.spotify.com/v1/albums/{album_id}", headers=headers)

    if response.status_code != 200:
        raise Exception(response.content)

    album = response.json()
    # The images field is a list of images in descending size order.
    # So the first image is the largest.
    return album["images"][0]["url"]





def get_spotify_token(client_id, client_secret):
    encoded = base64.b64encode(f"{client_id}:{client_secret}".encode())
    headers = {"Authorization": f"Basic {encoded.decode()}"}
    data = {"grant_type": "client_credentials"}

    response = requests.post("https://accounts.spotify.com/api/token", headers=headers, data=data)

    if response.status_code != 200:
        raise Exception(response.content)

    return response.json()["access_token"]


if __name__ == '__main__':
    logger.setLevel("DEBUG")
    main()
