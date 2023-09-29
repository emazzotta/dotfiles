#!/usr/bin/env python


from PIL import UnidentifiedImageError
from itertools import chain
from pathlib import Path
import argparse
import base64
import logging
import music_tag
import os
import re
import requests
import unicodedata

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)

SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')
TRACKS_PATH = os.environ.get('DJ_TRACKS')

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
    'artwork',
    'comment',
    'compilation',
    'composer',
    'discnumber',
    'genre',
    'isrc',
    'lyrics',
    'totaldiscs',
    'totaltracks',
    'tracknumber',
    'tracktitle',
    'year',
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
    for src in chain(
            Path(TRACKS_PATH).glob('**/*.mp3'),
            Path(TRACKS_PATH).glob('**/*.flac'),
            Path(TRACKS_PATH).glob('**/*.wav')):
        if src.name.startswith("._"):
            continue
        logger.info(f"[AUTOFIX] Processing {src}")
        track_metadata = music_tag.load_file(src)
        clean_all_tags(track_metadata)
        track_metadata.save()
        rename_by_tag(src)


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
    source_path = to_path(src)
    source_path.rename(
        Path(source_path.parent, f'{filename}{source_path.suffix}')
    )
    print(f"Renamed via metadata from [{src}] to [{filename}]")


def full_tag_optimizer(src):
    if not os.path.exists(src):
        print(f"Source file {src} does not exist.")
        return

    logger.info(f"[FULL_TAG_OPTIMIZER] Processing {src}")
    track_metadata = music_tag.load_file(src)
    set_missing_metadata_from_filename(src, track_metadata)
    clean_all_tags(track_metadata)
    if not track_metadata['artwork'].first:
        download_and_set_cover_photo(track_metadata)
    track_metadata.save()
    remove_where_from(src)
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
        except (ValueError, UnidentifiedImageError) as e:
            logger.warning(f"Error processing tag {tag}: {str(e)}")


def clean_string(line):
    line = re.sub(r'\[www\.slider\.kz]', '', line)
    line = re.sub(r'\s+', ' ', line)
    line = line.replace('(Original Mix)', '')
    line = line.replace('(Original Version)', '')
    line = line.replace('(Extended Mix)', '')
    line = line.replace('(Extended Version)', '')
    line = line.replace('(copy)', '')
    line = re.sub(r'\(\d+\)', '', line)
    line = re.sub(r'^\s+|\s+$', '', line)
    return line


def set_missing_metadata_from_filename(src, track_metadata):
    src_path = to_path(src)
    if not track_metadata['artist'].first or not track_metadata['tracktitle'].first:
        if ' - ' in src_path.stem:
            artist, title = map(str.strip, src_path.stem.split(' - ', 1))
            if not track_metadata['artist'].first:
                track_metadata['artist'] = artist
            if not track_metadata['tracktitle'].first:
                track_metadata['tracktitle'] = title


def get_spotify_token(client_id, client_secret):
    encoded = base64.b64encode(f"{client_id}:{client_secret}".encode())
    headers = {"Authorization": f"Basic {encoded.decode()}"}
    data = {"grant_type": "client_credentials"}
    response = requests.post("https://accounts.spotify.com/api/token", headers=headers, data=data)
    if response.status_code != 200:
        raise Exception(response.content)
    return response.json()["access_token"]


def search_track(artist, title, token):
    headers = {"Authorization": f"Bearer {token}"}
    params = {"q": f"{artist} {title}", "type": "track"}
    response = requests.get("https://api.spotify.com/v1/search", headers=headers, params=params)
    if response.status_code != 200:
        raise Exception(response.content)
    tracks = response.json()["tracks"]["items"]
    if tracks:
        return tracks[0]["album"]["id"]
    return None


def get_album_art(album_id, token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"https://api.spotify.com/v1/albums/{album_id}", headers=headers)
    if response.status_code != 200:
        raise Exception(response.content)
    album = response.json()
    return album["images"][0]["url"]


def download_and_set_cover_photo(track_metadata):
    token = get_spotify_token(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
    album_id = search_track(track_metadata['artist'].first, track_metadata['tracktitle'].first, token)
    if album_id:
        album_art_url = get_album_art(album_id, token)
        response = requests.get(album_art_url)
        track_metadata['artwork'] = response.content


def to_path(src):
    if isinstance(src, str):
        return Path(src)
    elif isinstance(src, Path):
        return src
    else:
        raise TypeError(f"Expected str or Path, got {type(src).__name__}")


def remove_where_from(file_path):
    os.system(f'xattr -d com.apple.metadata:kMDItemWhereFroms "{file_path}"')


if __name__ == '__main__':
    logger.setLevel("DEBUG")
    main()
