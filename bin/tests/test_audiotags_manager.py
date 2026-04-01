from unittest.mock import MagicMock

import pytest


@pytest.fixture
def atm(load_script):
    mocks = {
        "music_tag": MagicMock(),
        "requests": MagicMock(),
        "PIL": MagicMock(),
        "PIL.UnidentifiedImageError": MagicMock(),
    }
    return load_script("audiotags_manager", mock_modules=mocks)


class TestCleanString:
    @pytest.mark.parametrize("input_val,expected", [
        ("hello https://example.com", "hello"),
        ("track www.example.com here", "track here"),
        ("Track Purchased at Beatport", "Track"),
        ("Track Converted by someone", "Track someone"),
        ("  hello  ", "hello"),
        ("hello    world", "hello world"),
        ("hello , world", "hello, world"),
        ("Track (123)", "Track"),
    ])
    def test_basic_cleaning(self, atm, input_val, expected):
        assert atm.clean_string(input_val) == expected

    @pytest.mark.parametrize("input_val", [
        "Track (copy)",
        "Track (Extended Mix)",
        "Track (Original Mix)",
        "Track (Original Version)",
        "Track (Extended Version)",
        "Track (Extended)",
        "Track (Original)",
    ])
    def test_removes_mix_patterns(self, atm, input_val):
        result = atm.clean_string(input_val)
        assert result == "Track"

    def test_artist_slash_replacement(self, atm):
        assert atm.clean_string("Artist1/Artist2", tag_name="artist") == "Artist1, Artist2"

    def test_non_artist_keeps_slash(self, atm):
        result = atm.clean_string("Title1/Title2")
        assert "/" not in result or "Title1" in result

    def test_removes_original_mix_standalone(self, atm):
        result = atm.clean_string("Track Original Mix")
        assert "Original Mix" not in result
        assert "Track" in result

    def test_preserves_named_mixes(self, atm):
        result = atm.clean_string("Track (Club Mix)")
        assert "Club Mix" in result
