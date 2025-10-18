#!/usr/bin/env python3
import pytest
import sys
import os

from ..leopath import normalize_path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_CASES = [
    pytest.param(
        'K:',
        'K:\\Daten',
        id='k_drive_alone'
    ),
    pytest.param(
        'K:\\Bereich_Informatik\\PROJEKTE\\file.leon',
        'K:\\Daten\\Bereich_Informatik\\PROJEKTE\\file.leon',
        id='k_drive_without_daten'
    ),
    pytest.param(
        'K:\\Daten\\Bereich_Informatik\\PROJEKTE\\file.leon',
        'K:\\Daten\\Bereich_Informatik\\PROJEKTE\\file.leon',
        id='k_drive_with_daten'
    ),
    pytest.param(
        '\\\\192.168.5.155\\Bereich_Informatik\\PROJEKTE\\file.leon',
        'K:\\Daten\\Bereich_Informatik\\PROJEKTE\\file.leon',
        id='unc_path_without_daten'
    ),
    pytest.param(
        '\\192.168.5.155\\Bereich_Informatik\\PROJEKTE\\file.leon',
        'K:\\Daten\\Bereich_Informatik\\PROJEKTE\\file.leon',
        id='unc_path_single_slash'
    ),
    pytest.param(
        '\\\\192.168.5.155\\Daten\\Bereich_Informatik\\PROJEKTE\\file.leon',
        'K:\\Daten\\Bereich_Informatik\\PROJEKTE\\file.leon',
        id='unc_path_with_daten'
    ),
    pytest.param(
        'C:\\emanuelemazzotta\\windows_mount\\Daten\\Bereich_Informatik\\file.leon',
        'K:\\Daten\\Bereich_Informatik\\file.leon',
        id='c_drive_with_daten'
    ),
    pytest.param(
        'D:\\backup\\old\\Daten\\projects\\subfolder\\file.txt',
        'K:\\Daten\\projects\\subfolder\\file.txt',
        id='d_drive_with_daten'
    ),
    pytest.param(
        '/Users/someone/mount/Daten/subfolder/file.leon',
        'K:\\Daten\\subfolder\\file.leon',
        id='unix_path_with_daten'
    ),
    pytest.param(
        'C:/roland/meineSachen/Daten/important/document.pdf',
        'K:\\Daten\\important\\document.pdf',
        id='mixed_slashes_with_daten'
    ),
    pytest.param(
        '\\\\server\\share\\nested\\folders\\Daten\\work\\project.leon',
        'K:\\Daten\\work\\project.leon',
        id='deep_unc_path_with_daten'
    ),
    pytest.param(
        'K:\\Daten\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon',
        'K:\\Daten\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon',
        id='complex_path_with_special_chars'
    ),
]


@pytest.mark.parametrize("input_path,expected", TEST_CASES)
def test_normalize_path(input_path, expected):
    result = normalize_path(input_path)
    assert result == expected


INVALID_CASES = [
    pytest.param(
        'C:\\random\\path\\without\\target',
        id='no_daten_no_k_no_ip'
    ),
    pytest.param(
        '/usr/local/bin/something',
        id='unix_path_without_daten'
    ),
    pytest.param(
        '\\\\other.server\\share\\file.txt',
        id='different_server_without_daten'
    ),
]


@pytest.mark.parametrize("invalid_path", INVALID_CASES)
def test_normalize_path_raises_error(invalid_path):
    with pytest.raises(ValueError, match="Path must contain 'Daten' or start with K: or 192.168.5.155"):
        normalize_path(invalid_path)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
