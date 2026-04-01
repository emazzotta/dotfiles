import xml.etree.ElementTree as ET

import pytest


@pytest.fixture
def mod(load_script):
    return load_script("rekordbox_fix")


class TestProcessXml:
    def _create_xml(self, tmp_path, tracks, playlist_keys=None):
        root = ET.Element("DJ_PLAYLISTS")
        collection = ET.SubElement(root, "COLLECTION")
        for track in tracks:
            ET.SubElement(collection, "TRACK", **track)
        if playlist_keys:
            playlists = ET.SubElement(root, "PLAYLISTS")
            node = ET.SubElement(playlists, "NODE")
            for key in playlist_keys:
                ET.SubElement(node, "TRACK", Key=key)
        tree = ET.ElementTree(root)
        input_path = tmp_path / "input.xml"
        tree.write(str(input_path))
        return input_path

    def test_removes_sandisk_tracks(self, mod, tmp_path):
        input_path = self._create_xml(tmp_path, [
            {"TrackID": "1", "Name": "Song", "Artist": "Art", "Location": "file:///Volumes/SanDisk_1TB/song.mp3"},
            {"TrackID": "2", "Name": "Song", "Artist": "Art", "Location": "file:///Users/emanuelemazzotta/song.mp3"},
        ])
        output_path = tmp_path / "output.xml"
        mod.process_xml(str(input_path), str(output_path))
        tree = ET.parse(str(output_path))
        tracks = tree.findall(".//COLLECTION/TRACK")
        locations = [t.get("Location") for t in tracks]
        assert not any("/Volumes/SanDisk_1TB" in loc for loc in locations)
        assert any("/Users/emanuelemazzotta" in loc for loc in locations)

    def test_updates_playlist_references(self, mod, tmp_path):
        input_path = self._create_xml(
            tmp_path,
            [
                {"TrackID": "1", "Name": "Song", "Artist": "Art", "Location": "file:///Volumes/SanDisk_1TB/song.mp3"},
                {"TrackID": "2", "Name": "Song", "Artist": "Art", "Location": "file:///Users/emanuelemazzotta/song.mp3"},
            ],
            playlist_keys=["1"],
        )
        output_path = tmp_path / "output.xml"
        mod.process_xml(str(input_path), str(output_path))
        tree = ET.parse(str(output_path))
        playlist_tracks = tree.findall(".//NODE/TRACK")
        keys = [t.get("Key") for t in playlist_tracks]
        assert "2" in keys
        assert "1" not in keys

    def test_keeps_tracks_without_sandisk(self, mod, tmp_path):
        input_path = self._create_xml(tmp_path, [
            {"TrackID": "1", "Name": "Local", "Artist": "Art", "Location": "file:///Users/emanuelemazzotta/local.mp3"},
        ])
        output_path = tmp_path / "output.xml"
        mod.process_xml(str(input_path), str(output_path))
        tree = ET.parse(str(output_path))
        tracks = tree.findall(".//COLLECTION/TRACK")
        assert len(tracks) == 1

    def test_no_replacement_keeps_sandisk_in_playlist(self, mod, tmp_path):
        input_path = self._create_xml(
            tmp_path,
            [
                {"TrackID": "1", "Name": "Unique", "Artist": "Art", "Location": "file:///Volumes/SanDisk_1TB/unique.mp3"},
            ],
            playlist_keys=["1"],
        )
        output_path = tmp_path / "output.xml"
        mod.process_xml(str(input_path), str(output_path))
        tree = ET.parse(str(output_path))
        playlist_tracks = tree.findall(".//NODE/TRACK")
        keys = [t.get("Key") for t in playlist_tracks]
        assert "1" in keys
