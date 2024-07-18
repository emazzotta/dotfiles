#!/usr/bin/env python3

import xml.etree.ElementTree as ET

def process_xml(input_path, output_path):
    tree = ET.parse(input_path)
    root = tree.getroot()

    # Create dictionaries for deletion candidates and valid tracks
    to_delete = {}
    valid_tracks = {}

    # Identify tracks for deletion and valid tracks
    for track in root.findall(".//TRACK"):
        location = track.get('Location')
        if location and "/Volumes/SanDisk_1TB" in location:
            to_delete[track.get('TrackID')] = (track.get('Name'), track.get('Artist'))
        elif location and "/Users/emanuelemazzotta" in location:
            valid_tracks[(track.get('Name'), track.get('Artist'))] = track.get('TrackID')

    # Map deletions to valid replacements
    replacements = {}
    for track_id, (name, artist) in to_delete.items():
        if (name, artist) in valid_tracks:
            replacements[track_id] = valid_tracks[(name, artist)]

    # Update playlist references
    for node in root.findall(".//NODE"):
        for track in node.findall(".//TRACK"):
            key = track.get('Key')
            if key and key in replacements:
                track.set('Key', replacements[key])

    # Remove the tracks slated for deletion
    for track_id in list(to_delete.keys()):
        for track in root.findall(".//TRACK[@TrackID='" + track_id + "']"):
            parent = root.find('.//COLLECTION')  # Assuming TRACKs are direct children of COLLECTION
            if track in parent:
                parent.remove(track)

    # Save the modified XML
    tree.write(output_path)

# Replace with the actual file paths
process_xml('input.xml', 'output.xml')
