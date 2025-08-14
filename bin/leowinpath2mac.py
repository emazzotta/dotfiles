#!/usr/bin/env python3
r"""
Examples:
\\192.168.5.155\PROJEKTE\2_Leonardo\43_Leonardo 24\8_Tests\Testfälle\vollständiger Invaliditätsfall.leon
K:\Daten\Bereich_Informatik\PROJEKTE\2_Leonardo\43_Leonardo 24\8_Tests\Testfälle\vollständiger Invaliditätsfall.leon
K:\Bereich_Informatik\PROJEKTE\2_Leonardo\43_Leonardo 24\8_Tests\Testfälle\vollständiger Invaliditätsfall.leon
"""
import sys
import urllib.parse
import subprocess
import os
import re
import pytest

def normalize_path(path):
    if path == 'K:':
        return 'K:\\Daten'

    path = re.sub(r'^\\\\192\.168\.5\.155\\Daten\\', r'K:\\Daten\\', path)
    path = re.sub(r'^K:\\(?!Daten)', r'K:\\Daten\\', path)

    if not path.startswith('K:\\Daten'):
        raise ValueError("Path must start with K: or \\\\192.168.5.155")

    return path

def convert_to_mac(windows_path):
    mac_path = windows_path.replace('K:\\Daten', f'{os.path.expanduser("~")}/Daten', 1)
    mac_path = mac_path.replace('\\', '/')
    return mac_path

@pytest.mark.parametrize("input_path,expected", [
    ('K:', 'K:\\Daten'),
    ('K:\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon',
     'K:\\Daten\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon'),
    ('K:\\Daten\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon',
     'K:\\Daten\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon'),
    ('\\\\192.168.5.155\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon',
     'K:\\Daten\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon'),
    ('\\\\192.168.5.155\\Daten\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon',
     'K:\\Daten\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon'),
])
def test_normalize_path_as_expected(input_path, expected):
    result = normalize_path(input_path)
    assert result == expected

def main():
    script_name = os.path.basename(sys.argv[0])

    if len(sys.argv) >= 2 and sys.argv[1] == 'check':
        pytest.main([__file__, '-v'])
        return

    if len(sys.argv) < 2:
        print(f"Usage: {script_name} K:\\path\\to\\file or {script_name} \\\\192.168.5.155\\Daten\\path\\to\\file")
        print(f"       {script_name} check  (run tests)")
        sys.exit(1)

    path = ' '.join(sys.argv[1:])

    try:
        normalized = normalize_path(path)
        mac_path = convert_to_mac(normalized)
        file_url = 'file://' + urllib.parse.quote(mac_path)

        subprocess.run(['pbcopy'], input=file_url, text=True)
        print(file_url)

        choice = input("Open file? (Y/f/n): ").strip().lower()
        if choice in ['', 'y']:
            subprocess.run(['open', mac_path])
        elif choice == 'f':
            folder_path = os.path.dirname(mac_path)
            subprocess.run(['open', folder_path])

    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
