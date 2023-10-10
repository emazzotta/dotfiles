#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys


def convert_audio(input_file, output_format, output_path, delete_original):
    filename, _ = os.path.splitext(os.path.basename(input_file))
    if output_path:
        output_file = f"{output_path}/{filename}.{output_format}"
    else:
        output_file = f"{os.path.dirname(input_file)}/{filename}.{output_format}"

    codec = {
        'flac': 'flac',
        'alac': 'alac',
        'wav': 'pcm_s16le',
        'ogg': 'libvorbis',
        'mp3': 'libmp3lame -q:a 0'
    }.get(output_format)

    if not codec:
        print(f"Error: Unsupported output format '{output_format}'")
        sys.exit(1)

    command = f"ffmpeg -i {input_file} -c:a {codec} {output_file}"
    subprocess.run(command, shell=True, check=True)

    if delete_original:
        os.remove(input_file)
        print(f"Original file '{input_file}' deleted.")

    print(f"Conversion complete: {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Convert audio files.')
    parser.add_argument('output_format', help='The format of the output audio file.')
    parser.add_argument('input_file', help='The audio file to convert.')
    parser.add_argument('-d', '--delete', action='store_true', help='Delete the original file after conversion.')
    parser.add_argument('-o', '--output-path', help='Path where to save the converted file.')

    args = parser.parse_args()

    if not os.path.isfile(args.input_file):
        print(f"Error: Input file '{args.input_file}' not found!")
        sys.exit(1)

    convert_audio(args.input_file, args.output_format, args.output_path, args.delete)


if __name__ == "__main__":
    main()
