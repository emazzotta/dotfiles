#!/usr/bin/env python3

import os
import re
import subprocess
import sys
import urllib.parse

FILE_PROTOCOL_PREFIX = 'file://'

HOME_DATEN = os.path.join(os.path.expanduser("~"), "Daten")


def is_file_url(path):
    return path.startswith(FILE_PROTOCOL_PREFIX)


def parse_file_url(file_url):
    path = file_url

    if is_file_url(path):
        path = path[7:]

    return urllib.parse.unquote(path)


def normalize_slashes(path):
    return path.replace('/', '\\')


def remove_leading_slashes(path):
    return re.sub(r'^\\+', '', path)


def has_daten(path):
    return bool(re.search(r'Daten', path, re.IGNORECASE))


def extract_from_daten(path):
    match = re.search(r'Daten(?:\\.*)?$', path, re.IGNORECASE)
    daten_part = match.group(0)
    daten_part = re.sub(r'^Daten', 'Daten', daten_part, count=1, flags=re.IGNORECASE)
    return f'K:\\{daten_part}'


def normalize_path(path):
    if is_file_url(path):
        path = parse_file_url(path)

    path = normalize_slashes(path)
    path = remove_leading_slashes(path)

    if path == 'K:':
        return 'K:\\Daten'

    if has_daten(path):
        return extract_from_daten(path)

    if path.startswith('K:\\'):
        return path.replace('K:\\', 'K:\\Daten\\', 1)

    if path.startswith('192.168.5.155\\'):
        return path.replace('192.168.5.155\\', 'K:\\Daten\\', 1)

    raise ValueError("Path must contain 'Daten' or start with K: or 192.168.5.155")


def to_mac_path(windows_path):
    mac_path = windows_path.replace('K:\\Daten', HOME_DATEN, 1)
    return mac_path.replace('\\', '/')


def is_folder(path):
    if path.endswith(('/', '\\')) or path.endswith(('/.', '\\.')):
        return True

    last_component = os.path.basename(path)
    return '.' not in last_component


def create_file_url(mac_path):
    return FILE_PROTOCOL_PREFIX + urllib.parse.quote(mac_path)


def copy_to_clipboard(text):
    subprocess.run(['pbcopy'], input=text, text=True)


def open_path(path):
    subprocess.run(['open', path])


def get_parent_folder(path):
    return os.path.dirname(path)


def run_tests():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    test_file = os.path.join(script_dir, 'tests', 'leopath_tests.py')
    result = subprocess.run([sys.executable, '-m', 'pytest', test_file, '-v'], capture_output=False, text=True)
    sys.exit(result.returncode)


def read_from_stdin():
    print("Paste the path and press Enter:")
    return input().strip()


def print_usage(script_name):
    print(f"Usage: {script_name} <path>")
    print(f"       {script_name} -           (read path from stdin/paste)")
    print(f"       {script_name} check       (run tests)")
    print()
    print("Examples:")
    print(f"  {script_name} 'K:\\Daten\\path\\to\\file.leon'")
    print(f"  {script_name} 'file:///Users/name/Daten/file.pdf'")
    print(f"  {script_name} -")
    print()
    print("Note: Supports file:// URLs with automatic URL decoding")


def prompt_user_action(mac_path, windows_path):
    path_type = "folder" if is_folder(mac_path) else "file"
    choice = input(f"\nOpen {path_type}? (Y/w/f/n): ").strip().lower()

    if choice in ['', 'y']:
        open_path(mac_path)
    elif choice == 'w':
        print(f"\nWindows path: {windows_path}")
        copy_to_clipboard(windows_path)
        print("Windows path copied to clipboard!")
    elif choice == 'f':
        folder = get_parent_folder(mac_path) if not is_folder(mac_path) else mac_path
        open_path(folder)


def process_path(input_path):
    normalized = normalize_path(input_path)
    mac_path = to_mac_path(normalized)
    file_url = create_file_url(mac_path)

    copy_to_clipboard(file_url)

    path_type = "Folder" if is_folder(mac_path) else "File"
    print(f"Type:       {path_type}")
    print(f"Normalized: {normalized}")
    print(f"Mac path:   {mac_path}")
    print(f"File URL:   {file_url}")
    print("\nFile URL copied to clipboard!")

    prompt_user_action(mac_path, normalized)


def main():
    script_name = os.path.basename(sys.argv[0])

    if len(sys.argv) >= 2 and sys.argv[1] == 'check':
        run_tests()

    if len(sys.argv) < 2:
        print_usage(script_name)
        sys.exit(1)

    if sys.argv[1] == '-':
        if not sys.stdin.isatty():
            input_path = sys.stdin.read().strip()
        else:
            input_path = read_from_stdin()
    else:
        input_path = ' '.join(sys.argv[1:])

    if not input_path:
        print("Error: No path provided")
        sys.exit(1)

    try:
        process_path(input_path)
    except ValueError as e:
        print(f"Error: {e}")
        print(f"\nTip: On Mac/Linux, quote Windows paths or use '{script_name} -' to paste interactively")
        sys.exit(1)


if __name__ == '__main__':
    main()
