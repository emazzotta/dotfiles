#!/usr/bin/env python3

import pytest

from bin.leowinpath2mac import normalize_path


@pytest.mark.parametrize("input_path,expected", [
    ('K:', 'K:\\Daten'),
    ('K:\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon',
     'K:\\Daten\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon'),
    ('K:\\Daten\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon',
     'K:\\Daten\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon'),
    ('\\\\192.168.5.155\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon',
     'K:\\Daten\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon'),
    ('\\192.168.5.155\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon',
     'K:\\Daten\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon'),
    ('\\\\192.168.5.155\\Daten\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon',
     'K:\\Daten\\Bereich_Informatik\\PROJEKTE\\2_Leonardo\\43_Leonardo 24\\8_Tests\\Testfälle\\vollständiger Invaliditätsfall.leon'),
])
def should_normalize_path_as_expected(input_path, expected):
    result = normalize_path(input_path)
    assert result == expected


def main():
    pytest.main([__file__, '-v'])


if __name__ == '__main__':
    main()
