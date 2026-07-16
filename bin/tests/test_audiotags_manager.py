from unittest.mock import MagicMock, patch

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


class TestRemoveWhereFrom:
    def test_should_pass_filename_as_literal_argv_without_invoking_a_shell(self, atm):
        hostile = "/tracks/x$(id -un > /tmp/pwned)`whoami`.mp3"

        with patch.object(atm.subprocess, "run") as run:
            atm.remove_where_from(hostile)

        args, kwargs = run.call_args
        assert args[0] == [
            "xattr", "-d", "com.apple.metadata:kMDItemWhereFroms", hostile
        ]
        assert kwargs.get("shell") is not True

    @pytest.mark.parametrize("filename", [
        "/tracks/Ke$ha - Tik Tok.mp3",
        "/tracks/Artist - $HOME.mp3",
        '/tracks/a"b.mp3',
        "/tracks/Bjork - Joga `whoami`.mp3",
        "/tracks/50% Off (Remix).wav",
    ])
    def test_should_preserve_shell_metacharacters_in_the_filename(self, atm, filename):
        with patch.object(atm.subprocess, "run") as run:
            atm.remove_where_from(filename)

        assert run.call_args[0][0][3] == filename

    def test_should_accept_a_path_and_stringify_it(self, atm, tmp_path):
        track = tmp_path / "track.mp3"

        with patch.object(atm.subprocess, "run") as run:
            atm.remove_where_from(track)

        assert run.call_args[0][0][3] == str(track)

    def test_should_not_raise_when_attribute_is_absent(self, atm, tmp_path):
        track = tmp_path / "no-such-attribute.mp3"
        track.write_bytes(b"")

        atm.remove_where_from(track)
