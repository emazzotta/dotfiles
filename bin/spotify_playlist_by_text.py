#!/usr/bin/env python3

###
# https://developer.spotify.com/dashboard
###
print("Remember to run `envify && av`")

import spotipy
from spotipy.oauth2 import SpotifyOAuth
import time
import sys
import os

PLAYLIST_NAME = "Shazam"

scope = 'playlist-modify-private playlist-read-private'
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope))

def find_or_create_playlist(name):
    user_id = sp.current_user()['id']
    playlists = sp.current_user_playlists()

    for playlist in playlists['items']:
        if playlist['name'] == name:
            return playlist['id']

    return sp.user_playlist_create(user_id, name, public=False, description='A playlist from Shazam')['id']

def add_tracks_to_playlist(playlist_id, track_file):
    existing_tracks = set([item['track']['id'] for item in sp.playlist_tracks(playlist_id)['items']])
    track_ids = []
    not_found = []
    rate_limited = False

    with open(track_file, 'r') as file:
        for line in file:
            track = line.strip()
            result = None
            while result is None:
                try:
                    result = sp.search(q=track, limit=1)
                    if result['tracks']['items']:
                        track_id = result['tracks']['items'][0]['id']
                        if track_id not in existing_tracks:
                            track_ids.append(track_id)
                            existing_tracks.add(track_id)
                    else:
                        not_found.append(track)
                except spotipy.exceptions.SpotifyException as e:
                    if e.http_status == 429:
                        rate_limited = True
                        delay = int(e.headers['Retry-After'])
                        print(f"Rate limiting occurred. Retrying in {delay} seconds...")
                        time.sleep(delay + 1)
                        result = None
                    else:
                        raise

    if track_ids:
        sp.playlist_add_items(playlist_id, track_ids)

    return not_found, rate_limited

if __name__ == '__main__':
    if len(sys.argv) < 2:
        script_name = os.path.basename(__file__)
        print(f"Usage: {script_name} <path_to_track_file>")
        sys.exit(1)

    track_file = sys.argv[1]
    playlist_id = find_or_create_playlist(PLAYLIST_NAME)

    tracks_not_found, rate_limited_occurred = add_tracks_to_playlist(playlist_id, track_file)

    if tracks_not_found:
        print("The following tracks were not found on Spotify:", tracks_not_found)
    if rate_limited_occurred:
        print("Rate limiting was encountered during the operation.")
    else:
        print("All track operations completed")
