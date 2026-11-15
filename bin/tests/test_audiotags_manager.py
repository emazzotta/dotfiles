import os
from datetime import datetime, timedelta
from types import SimpleNamespace
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


@pytest.fixture
def make_candidate(atm):
    def _make(source, artist, title, image_url="https://example.test/art.jpg"):
        return atm.CoverCandidate(
            source=source, artist=artist, title=title, image_url=image_url
        )
    return _make


@pytest.fixture
def fake_metadata():
    def _make(artist, title):
        tags = {"artist": artist, "tracktitle": title}
        written: dict = {}

        class Metadata:
            def __getitem__(self, key):
                return SimpleNamespace(first=tags.get(key))

            def __setitem__(self, key, value):
                written[key] = value

        return Metadata(), written
    return _make


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

    def test_preserves_named_mixes(self, atm):
        result = atm.clean_string("Track (Club Mix)")
        assert "Club Mix" in result


class TestCleanStringRegressions:
    @pytest.mark.parametrize("input_val,expected", [
        ("Track (mix)", "Track (Mix)"),
        ("Track (edit)", "Track (Edit)"),
        ("Track (version)", "Track (Version)"),
        ("Track (radio edit)", "Track (Radio Edit)"),
    ])
    def test_should_capitalise_a_lowercase_mix_marker_with_or_without_a_leading_word(
        self, atm, input_val, expected
    ):
        assert atm.clean_string(input_val) == expected

    @pytest.mark.parametrize("tag_name", ["lyrics", "comment"])
    def test_should_keep_the_line_breaks_of_lyrics_and_comments(self, atm, tag_name):
        text = "First line  \nsecond   line\n\nthird line"

        assert atm.clean_string(text, tag_name=tag_name) == "First line\nsecond line\n\nthird line"

    def test_should_still_clean_each_line_of_lyrics(self, atm):
        text = "Line one (Original Mix)\nsee https://example.com now\nline , three"

        assert atm.clean_string(text, tag_name="lyrics") == "Line one\nsee now\nline, three"

    def test_should_collapse_line_breaks_in_a_single_line_tag(self, atm):
        assert atm.clean_string("Track\nname", tag_name="tracktitle") == "Track name"

    @pytest.mark.parametrize("title", ["Originals", "Unoriginal", "Originality"])
    def test_should_not_cut_original_out_of_a_longer_word(self, atm, title):
        assert atm.clean_string(title) == title

    def test_should_not_cut_the_word_that_follows_original_in_half(self, atm):
        assert atm.clean_string("Original Mixtape") == "Original Mixtape"


class TestCleanStringMixMarkerWords:
    @pytest.mark.parametrize("input_val,expected", [
        ("Track (club dub mix)", "Track (Club Dub Mix)"),
        ("Track (chris lake club mix)", "Track (Chris Lake Club Mix)"),
        ("Track (CLUB dub edit)", "Track (CLUB Dub Edit)"),
        ("Track (dub version)", "Track (Dub Version)"),
        ("Track (club mix) and (dub edit)", "Track (Club Mix) and (Dub Edit)"),
    ])
    def test_should_keep_and_capitalise_every_word_before_the_marker(self, atm, input_val, expected):
        assert atm.clean_string(input_val) == expected

    @pytest.mark.parametrize("input_val,expected", [
        ("Track (club mix)", "Track (Club Mix)"),
        ("Track (CLUB mix)", "Track (CLUB Mix)"),
        ("Track ( mix )", "Track (Mix)"),
        ("Track (Club Mix)", "Track (Club Mix)"),
        ("Track (live at berghain)", "Track (live at berghain)"),
        ("Track (club mix 2)", "Track (club mix 2)"),
    ])
    def test_should_keep_the_cases_that_already_worked(self, atm, input_val, expected):
        assert atm.clean_string(input_val) == expected

    @pytest.mark.parametrize("input_val,expected", [
        ("Track (DJ Dub mix)", "Track (DJ Dub Mix)"),
        ("Track (DJ dub mix)", "Track (DJ Dub Mix)"),
        ("Track (MJ Cole edit)", "Track (MJ Cole Edit)"),
        ("Track (vocal edit)", "Track (Vocal Edit)"),
    ])
    def test_should_raise_only_the_first_letter_of_each_word(self, atm, input_val, expected):
        assert atm.clean_string(input_val) == expected


class TestCleanStringOriginalLabel:
    @pytest.mark.parametrize("input_val,expected", [
        ("Original Sin", "Original Sin"),
        ("The Original", "The Original"),
        ("Original Mixtape", "Original Mixtape"),
        ("Track (Original Remix)", "Track (Original Remix)"),
        ("Original Sin (Original Mix)", "Original Sin"),
        ("Original Sin - Original Mix", "Original Sin"),
    ])
    def test_should_keep_original_when_it_is_part_of_the_title(self, atm, input_val, expected):
        assert atm.clean_string(input_val) == expected

    @pytest.mark.parametrize("input_val", [
        "Track [Original Mix]",
        "Track [Original Version]",
        "Track [Original]",
        "Track [original mix]",
        "Track - Original Mix",
        "Track - original mix",
        "Track - ORIGINAL MIX",
    ])
    def test_should_remove_the_label_from_a_bracket_and_from_a_trailing_dash_suffix(self, atm, input_val):
        assert atm.clean_string(input_val) == "Track"

    @pytest.mark.parametrize("input_val", [
        "Track (original mix)",
        "Track (ORIGINAL MIX)",
        "Track (original version)",
        "Track (ORIGINAL VERSION)",
        "Track (original)",
        "Track (ORIGINAL)",
    ])
    def test_should_remove_the_parenthesised_label_in_any_case(self, atm, input_val):
        assert atm.clean_string(input_val) == "Track"


class TestCopyTag:
    class FakeTags:
        def __init__(self, **values):
            self.values = dict(values)
            self.saved = False

        def __getitem__(self, key):
            return self.values.get(key, "")

        def __setitem__(self, key, value):
            self.values[key] = value

        def save(self):
            self.saved = True

    def test_should_write_the_source_tags_into_the_destination_file(self, atm, tmp_path):
        source = tmp_path / "source.mp3"
        destination = tmp_path / "destination.mp3"
        source.touch()
        destination.touch()
        loaded = {
            str(source): self.FakeTags(artist="Source Artist", tracktitle="Source Title"),
            str(destination): self.FakeTags(artist="Old Artist", tracktitle="Old Title"),
        }

        with patch.object(atm.music_tag, "load_file", side_effect=lambda path: loaded[str(path)]):
            atm.copy_tag(str(source), str(destination))

        assert loaded[str(destination)].values["artist"] == "Source Artist"
        assert loaded[str(destination)].values["tracktitle"] == "Source Title"
        assert loaded[str(destination)].saved is True

    def test_should_leave_the_source_tags_unchanged(self, atm, tmp_path):
        source = tmp_path / "source.mp3"
        destination = tmp_path / "destination.mp3"
        source.touch()
        destination.touch()
        loaded = {
            str(source): self.FakeTags(artist="Source Artist"),
            str(destination): self.FakeTags(artist="Old Artist"),
        }

        with patch.object(atm.music_tag, "load_file", side_effect=lambda path: loaded[str(path)]):
            atm.copy_tag(str(source), str(destination))

        assert loaded[str(source)].values == {"artist": "Source Artist"}
        assert loaded[str(source)].saved is False


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


class TestArtistAndTitleFromFilename:
    @pytest.mark.parametrize("stem,expected", [
        ("Fred again.. - Delilah", ("Fred again..", "Delilah")),
        ("Fred again.. – Delilah", ("Fred again..", "Delilah")),
        ("01 - Fred again.. - Delilah", ("Fred again..", "Delilah")),
        ("03_Fred again.. - Delilah", ("Fred again..", "Delilah")),
        ("12. Fred again.. - Delilah", ("Fred again..", "Delilah")),
    ])
    def test_should_split_artist_and_title(self, atm, stem, expected):
        assert atm.artist_and_title_from_filename(stem) == expected

    @pytest.mark.parametrize("stem,expected_title", [
        ("Delilah", "Delilah"),
        ("Non-Stop", "Non-Stop"),
        ("07 - Delilah", "Delilah"),
    ])
    def test_should_use_the_whole_stem_as_title_when_there_is_no_separator(
        self, atm, stem, expected_title
    ):
        assert atm.artist_and_title_from_filename(stem) == ("", expected_title)

    @pytest.mark.parametrize("stem", ["50 Cent - In Da Club", "1979 - Remaster"])
    def test_should_not_mistake_a_leading_number_in_the_artist_for_a_track_number(
        self, atm, stem
    ):
        artist, _ = atm.artist_and_title_from_filename(stem)

        assert artist == stem.split(" - ")[0]

    def test_should_return_empty_strings_for_an_empty_stem(self, atm):
        assert atm.artist_and_title_from_filename("") == ("", "")


class TestSetMissingMetadataFromFilename:
    def test_should_fill_both_tags_when_the_file_has_none(self, atm, fake_metadata):
        metadata, written = fake_metadata(None, None)

        atm.set_missing_metadata_from_filename("/tracks/Fred again.. - Delilah.mp3", metadata)

        assert written == {"artist": "Fred again..", "tracktitle": "Delilah"}

    def test_should_fill_only_the_title_when_the_filename_has_no_separator(
        self, atm, fake_metadata
    ):
        metadata, written = fake_metadata(None, None)

        atm.set_missing_metadata_from_filename("/tracks/Delilah.mp3", metadata)

        assert written == {"tracktitle": "Delilah"}

    def test_should_leave_existing_tags_untouched(self, atm, fake_metadata):
        metadata, written = fake_metadata("Fred again..", "Delilah")

        atm.set_missing_metadata_from_filename("/tracks/Wrong - Name.mp3", metadata)

        assert written == {}

    def test_should_treat_a_whitespace_only_tag_as_missing(self, atm, fake_metadata):
        metadata, written = fake_metadata("   ", "  ")

        atm.set_missing_metadata_from_filename("/tracks/Fred again.. - Delilah.mp3", metadata)

        assert written == {"artist": "Fred again..", "tracktitle": "Delilah"}


class TestRenameByTag:
    @pytest.fixture
    def rename(self, atm):
        def _rename(track, artist, title):
            metadata = MagicMock()
            metadata.__getitem__.side_effect = lambda key: SimpleNamespace(
                first={"artist": artist, "tracktitle": title}.get(key)
            )
            with patch.object(atm.music_tag, "load_file", return_value=metadata), \
                    patch.object(atm, "compose_filename",
                                 return_value=f"{artist or ''} - {title or ''}"):
                atm.rename_by_tag(str(track))
        return _rename

    @pytest.mark.parametrize("artist,title", [
        (None, None),
        ("", ""),
        ("Fred again..", None),
        (None, "Delilah"),
        ("   ", "Delilah"),
    ])
    def test_should_not_rename_when_artist_or_title_is_empty(
        self, atm, tmp_path, rename, artist, title
    ):
        track = tmp_path / "untagged.mp3"
        track.write_bytes(b"audio")

        rename(track, artist, title)

        assert track.exists()
        assert [p.name for p in tmp_path.iterdir()] == ["untagged.mp3"]

    def test_should_never_produce_a_degenerate_dash_only_filename(
        self, atm, tmp_path, rename
    ):
        first = tmp_path / "one-untagged.mp3"
        second = tmp_path / "two-untagged.mp3"
        first.write_bytes(b"first")
        second.write_bytes(b"second")

        rename(first, None, None)
        rename(second, None, None)

        assert not (tmp_path / " - .mp3").exists()
        assert first.read_bytes() == b"first"
        assert second.read_bytes() == b"second"

    def test_should_rename_when_both_tags_are_present(self, atm, tmp_path, rename):
        track = tmp_path / "untagged.mp3"
        track.write_bytes(b"audio")

        rename(track, "Fred again..", "Delilah")

        assert (tmp_path / "Fred again.. - Delilah.mp3").read_bytes() == b"audio"
        assert not track.exists()

    def test_should_not_overwrite_a_different_file_that_already_has_the_target_name(
        self, atm, tmp_path, rename
    ):
        source = tmp_path / "untagged.mp3"
        occupied = tmp_path / "Fred again.. - Delilah.mp3"
        source.write_bytes(b"new")
        occupied.write_bytes(b"existing")

        rename(source, "Fred again..", "Delilah")

        assert occupied.read_bytes() == b"existing"
        assert source.read_bytes() == b"new"


class TestRenameByTagWithRealNormalisation:
    class Item:
        def __init__(self, value):
            self.first = value

        def __str__(self):
            return self.first or ""

    @pytest.fixture
    def rename(self, atm):
        def _rename(track, artist, title):
            metadata = MagicMock()
            metadata.__getitem__.side_effect = lambda key: self.Item(
                {"artist": artist, "tracktitle": title}.get(key)
            )
            with patch.object(atm.music_tag, "load_file", return_value=metadata):
                atm.rename_by_tag(str(track))
        return _rename

    @pytest.mark.parametrize("artist,title", [
        ("\u041a\u0438\u043d\u043e", "\u0413\u0440\u0443\u043f\u043f\u0430 \u043a\u0440\u043e\u0432\u0438"),
        ("\u5b87\u591a\u7530\u30d2\u30ab\u30ea", "First Love"),
        ("Hikaru Utada", "\u30d5\u30a1\u30fc\u30b9\u30c8\u30e9\u30d6"),
    ])
    def test_should_keep_the_filename_when_artist_or_title_has_no_ascii_characters(
        self, atm, tmp_path, rename, artist, title
    ):
        track = tmp_path / "original.mp3"
        track.write_bytes(b"audio")

        rename(track, artist, title)

        assert [p.name for p in tmp_path.iterdir()] == ["original.mp3"]
        assert track.read_bytes() == b"audio"

    def test_should_still_rename_when_accents_reduce_to_ascii(self, atm, tmp_path, rename):
        track = tmp_path / "original.mp3"
        track.write_bytes(b"audio")

        rename(track, "Beyonc\u00e9", "Halo")

        assert (tmp_path / "Beyonce - Halo.mp3").read_bytes() == b"audio"


class TestEnvifyFailures:
    @pytest.fixture
    def no_spotify_creds(self, monkeypatch):
        monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
        monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)

    def test_should_raise_a_cover_lookup_error_when_envify_fails(self, atm, no_spotify_creds):
        failed = SimpleNamespace(returncode=1, stdout="", stderr="keyguard cancelled")

        with patch.object(atm.subprocess, "run", return_value=failed):
            with pytest.raises(atm.CoverLookupError, match="keyguard cancelled"):
                atm.load_env_via_envify(atm.SPOTIFY_ENV_VARS)

    def test_should_raise_a_cover_lookup_error_when_envify_leaves_the_credentials_unset(
        self, atm, no_spotify_creds
    ):
        with patch.object(atm, "load_env_via_envify"):
            with pytest.raises(atm.CoverLookupError, match="SPOTIFY_CLIENT_ID"):
                atm.ensure_spotify_creds()

    def test_should_fall_back_to_soundcloud_when_envify_fails(
        self, atm, no_spotify_creds, make_candidate
    ):
        failed = SimpleNamespace(returncode=1, stdout="", stderr="keyguard cancelled")
        soundcloud = [make_candidate(atm.CoverSource.SOUNDCLOUD, "Fred again..", "Delilah")]

        with patch.object(atm.subprocess, "run", return_value=failed), \
                patch.object(atm, "fetch_soundcloud_candidates", return_value=soundcloud):
            best = atm.find_best_cover("Fred again..", "Delilah")

        assert best.candidate.source is atm.CoverSource.SOUNDCLOUD


ENVIFY_STAND_IN = """\
printf '%s\\n' "$@" >> "$ENVIFY_CALLS"
echo ENVIFY_EXTRA=leaked
if [ -n "${ENVIFY_FAIL+x}" ]; then
    printf '%s' "$ENVIFY_FAIL" >&2
    return 1
fi
for name in "$@"; do
    given="ENVIFY_STANDIN_$name"
    if [ -z "${!name}" ] && [ -n "${!given}" ]; then
        export "$name=${!given}"
    fi
done
"""


class TestEnvifyLoading:
    @pytest.fixture
    def asked_of_envify(self, tmp_path, monkeypatch):
        stand_in = tmp_path / "stand_in" / "envify"
        stand_in.parent.mkdir()
        stand_in.write_text(ENVIFY_STAND_IN)
        calls = tmp_path / "envify_calls"
        monkeypatch.setenv("PATH", f"{stand_in.parent}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv("ENVIFY_CALLS", str(calls))
        for name in ("ENVIFY_EXTRA", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"):
            monkeypatch.setenv(name, "")
            monkeypatch.delenv(name)
        return lambda: calls.read_text().split() if calls.exists() else []

    def test_should_ask_envify_for_both_credentials_and_keep_their_values_intact(
        self, atm, asked_of_envify, monkeypatch
    ):
        monkeypatch.setenv("ENVIFY_STANDIN_SPOTIFY_CLIENT_ID", "id-123")
        monkeypatch.setenv("ENVIFY_STANDIN_SPOTIFY_CLIENT_SECRET", "se cr=et==")

        atm.ensure_spotify_creds()

        assert asked_of_envify() == ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"]
        assert (os.environ["SPOTIFY_CLIENT_ID"], os.environ["SPOTIFY_CLIENT_SECRET"]) == ("id-123", "se cr=et==")

    def test_should_not_ask_envify_when_both_credentials_are_set(self, atm, asked_of_envify, monkeypatch):
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "kept-id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "kept-secret")

        atm.ensure_spotify_creds()

        assert asked_of_envify() == []

    def test_should_ask_for_both_names_and_keep_the_one_already_set(self, atm, asked_of_envify, monkeypatch):
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "kept-id")
        monkeypatch.setenv("ENVIFY_STANDIN_SPOTIFY_CLIENT_ID", "other-id")
        monkeypatch.setenv("ENVIFY_STANDIN_SPOTIFY_CLIENT_SECRET", "fresh-secret")

        atm.ensure_spotify_creds()

        assert asked_of_envify() == ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"]
        assert (os.environ["SPOTIFY_CLIENT_ID"], os.environ["SPOTIFY_CLIENT_SECRET"]) == ("kept-id", "fresh-secret")

    def test_should_copy_nothing_but_the_requested_names_into_the_environment(
        self, atm, asked_of_envify, monkeypatch
    ):
        monkeypatch.setenv("ENVIFY_STANDIN_SPOTIFY_CLIENT_ID", "id-123")
        monkeypatch.setenv("ENVIFY_STANDIN_SPOTIFY_CLIENT_SECRET", "secret")

        atm.ensure_spotify_creds()

        assert "ENVIFY_EXTRA" not in os.environ

    def test_should_name_the_credential_envify_did_not_provide(self, atm, asked_of_envify, monkeypatch):
        monkeypatch.setenv("ENVIFY_STANDIN_SPOTIFY_CLIENT_ID", "id-123")

        with pytest.raises(atm.CoverLookupError) as raised:
            atm.ensure_spotify_creds()

        assert str(raised.value) == "Spotify credentials missing after envify: SPOTIFY_CLIENT_SECRET"

    @pytest.mark.parametrize("stderr,message", [
        ("keyguard cancelled\n", "keyguard cancelled"),
        ("", "envify failed with no output"),
    ])
    def test_should_raise_the_stripped_stderr_when_envify_fails(
        self, atm, asked_of_envify, monkeypatch, stderr, message
    ):
        monkeypatch.setenv("ENVIFY_FAIL", stderr)

        with pytest.raises(atm.CoverLookupError) as raised:
            atm.ensure_spotify_creds()

        assert str(raised.value) == message


class TestNormalizeForMatch:
    @pytest.mark.parametrize("input_val,expected", [
        ("Björk", "bjork"),
        ("FRED AGAIN..", "fred again"),
        ("Delilah (pull me out of this)", "delilah pull me out of this"),
        ("Title [FREE DOWNLOAD]", "title"),
        ("Title (Original Mix)", "title"),
        ("Title (Extended Mix)", "title"),
        ("Title - Radio Edit", "title"),
        ("Title | PREMIERE", "title"),
        ("Artist feat. Guest", "artist guest"),
        ("Artist ft Guest", "artist guest"),
    ])
    def test_should_reduce_text_to_comparable_tokens(self, atm, input_val, expected):
        assert atm.normalize_for_match(input_val) == expected

    @pytest.mark.parametrize("distinguishing_word", [
        "remix", "bootleg", "flip", "vip", "mashup", "dub",
    ])
    def test_should_keep_words_that_mark_a_different_recording(self, atm, distinguishing_word):
        assert distinguishing_word in atm.normalize_for_match(f"Title ({distinguishing_word})")


class TestTitleSimilarity:
    def test_should_score_identical_titles_as_perfect(self, atm):
        assert atm.title_similarity("Delilah", "Delilah") == 1.0

    def test_should_treat_original_mix_suffix_as_the_same_title(self, atm):
        assert atm.title_similarity("Delilah (Original Mix)", "Delilah") == 1.0

    def test_should_rank_the_original_above_a_remix_of_it(self, atm):
        original = atm.title_similarity("Delilah", "Delilah")
        remix = atm.title_similarity("Delilah (WNTRZ Festival Remix)", "Delilah")

        assert remix < original

    def test_should_score_an_unrelated_title_low(self, atm):
        assert atm.title_similarity("Family Matters", "Delilah") < 0.5


class TestArtistSimilarity:
    def test_should_score_identical_artists_as_perfect(self, atm):
        assert atm.artist_similarity("Fred again..", "Fred again..") == 1.0

    def test_should_tolerate_extra_featured_artists_on_the_candidate(self, atm):
        assert atm.artist_similarity("Fred again.., Delilah Montagu", "Fred again..") == 1.0

    def test_should_score_an_unrelated_artist_low(self, atm):
        assert atm.artist_similarity("Drake", "Fred again..") < 0.5

    def test_should_score_an_empty_artist_as_zero(self, atm):
        assert atm.artist_similarity("", "Fred again..") == 0.0


class TestScoreCandidate:
    def test_should_score_on_title_alone_when_the_track_has_no_artist_tag(
        self, atm, make_candidate
    ):
        candidate = make_candidate(atm.CoverSource.SPOTIFY, "Fred again..", "Delilah")

        assert atm.score_candidate(candidate, "", "Delilah") == 1.0

    def test_should_not_penalise_a_title_only_match_below_the_threshold(
        self, atm, make_candidate
    ):
        candidate = make_candidate(atm.CoverSource.SPOTIFY, "Fred again..", "Delilah")

        assert atm.score_candidate(candidate, "", "Delilah") >= atm.MIN_MATCH_SCORE

    def test_should_weight_title_more_heavily_than_artist(self, atm, make_candidate):
        right_title = make_candidate(atm.CoverSource.SPOTIFY, "Wrong Artist", "Delilah")
        right_artist = make_candidate(atm.CoverSource.SPOTIFY, "Fred again..", "Wrong Title")

        assert atm.score_candidate(right_title, "Fred again..", "Delilah") > \
            atm.score_candidate(right_artist, "Fred again..", "Delilah")


class TestSearchQuery:
    @pytest.mark.parametrize("artist,title,expected", [
        ("Fred again..", "Delilah", "Fred again.. Delilah"),
        ("", "Delilah", "Delilah"),
        ("Fred again..", "", "Fred again.."),
    ])
    def test_should_join_only_the_parts_that_are_present(self, atm, artist, title, expected):
        assert atm.search_query(artist, title) == expected


class TestSplitArtistTitle:
    @pytest.mark.parametrize("title,expected", [
        ("Fred again.. - Delilah", ("Fred again..", "Delilah")),
        ("Fred again.. – Delilah", ("Fred again..", "Delilah")),
        ("Fred again.. — Delilah", ("Fred again..", "Delilah")),
        ("Delilah", ("", "")),
        ("Non-Stop", ("", "")),
    ])
    def test_should_split_only_on_a_spaced_separator(self, atm, title, expected):
        assert atm.split_artist_title(title) == expected

    def test_should_keep_later_separators_in_the_title(self, atm):
        assert atm.split_artist_title("A - B - C") == ("A", "B - C")


class TestUpsizeSoundcloudArtwork:
    def test_should_replace_the_thumbnail_size_token(self, atm):
        upsized = atm.upsize_soundcloud_artwork(
            "https://i1.sndcdn.com/artworks-TQsXyXtynfe2-0-large.jpg"
        )

        assert upsized == "https://i1.sndcdn.com/artworks-TQsXyXtynfe2-0-t500x500.jpg"

    def test_should_leave_an_already_sized_url_untouched(self, atm):
        sized = "https://i1.sndcdn.com/artworks-abc-t500x500.jpg"

        assert atm.upsize_soundcloud_artwork(sized) == sized

    @pytest.mark.parametrize("missing", [None, ""])
    def test_should_return_none_when_there_is_no_artwork(self, atm, missing):
        assert atm.upsize_soundcloud_artwork(missing) is None


class TestSoundcloudReadings:
    def test_should_read_publisher_metadata_uploader_and_split_title(self, atm):
        track = {
            "title": "Fred again.. - Delilah (pull me out of this)",
            "user": {"username": "Fred again.."},
            "publisher_metadata": {
                "artist": "Fred again.., Delilah Montagu",
                "release_title": "Delilah (pull me out of this)",
            },
        }

        assert atm.soundcloud_readings(track) == [
            ("Fred again.., Delilah Montagu", "Delilah (pull me out of this)"),
            ("Fred again..", "Fred again.. - Delilah (pull me out of this)"),
            ("Fred again..", "Delilah (pull me out of this)"),
        ]

    def test_should_fall_back_to_uploader_when_publisher_metadata_is_absent(self, atm):
        track = {"title": "Delilah", "user": {"username": "WNTRZ"}}

        assert atm.soundcloud_readings(track) == [("WNTRZ", "Delilah")]

    def test_should_return_no_readings_when_the_track_is_empty(self, atm):
        assert atm.soundcloud_readings({}) == []

    def test_should_drop_a_track_that_has_no_artwork(self, atm):
        track = {"title": "Delilah", "user": {"username": "Fred again.."}}

        assert atm.to_soundcloud_candidates(track) == ()


class TestSoundcloudClientIdCache:
    @pytest.fixture
    def cache_path(self, atm, tmp_path, monkeypatch):
        path = tmp_path / "cache" / "soundcloud_client_id"
        monkeypatch.setattr(atm, "CLIENT_ID_CACHE_PATH", path)
        return path

    def test_should_scrape_and_cache_when_there_is_no_cache_yet(self, atm, cache_path):
        with patch.object(atm, "scrape_soundcloud_client_id", return_value="abc123") as scrape:
            assert atm.fetch_soundcloud_client_id() == "abc123"

        scrape.assert_called_once()
        assert cache_path.read_text() == "abc123"

    def test_should_reuse_the_cached_id_without_scraping(self, atm, cache_path):
        cache_path.parent.mkdir(parents=True)
        cache_path.write_text("cached999")

        with patch.object(atm, "scrape_soundcloud_client_id") as scrape:
            assert atm.fetch_soundcloud_client_id() == "cached999"

        scrape.assert_not_called()

    def test_should_rescrape_when_the_cache_is_older_than_the_ttl(self, atm, cache_path):
        cache_path.parent.mkdir(parents=True)
        cache_path.write_text("stale")
        expired = (datetime.now() - atm.CLIENT_ID_CACHE_TTL - timedelta(minutes=1)).timestamp()
        os.utime(cache_path, (expired, expired))

        with patch.object(atm, "scrape_soundcloud_client_id", return_value="fresh") as scrape:
            assert atm.fetch_soundcloud_client_id() == "fresh"

        scrape.assert_called_once()
        assert cache_path.read_text() == "fresh"

    def test_should_ignore_an_empty_cache_file(self, atm, cache_path):
        cache_path.parent.mkdir(parents=True)
        cache_path.write_text("   ")

        with patch.object(atm, "scrape_soundcloud_client_id", return_value="fresh"):
            assert atm.fetch_soundcloud_client_id() == "fresh"

    def test_should_still_return_an_id_when_the_cache_cannot_be_written(self, atm, tmp_path,
                                                                       monkeypatch):
        unwritable = tmp_path / "file-in-the-way" / "soundcloud_client_id"
        unwritable.parent.write_text("not a directory")
        monkeypatch.setattr(atm, "CLIENT_ID_CACHE_PATH", unwritable)

        with patch.object(atm, "scrape_soundcloud_client_id", return_value="abc123"):
            assert atm.fetch_soundcloud_client_id() == "abc123"


class TestSoundcloudRequestHeaders:
    def test_should_send_a_browser_user_agent_on_every_soundcloud_request(self, atm):
        assert atm.SOUNDCLOUD_HEADERS["User-Agent"] == atm.BROWSER_USER_AGENT

    def test_should_send_the_user_agent_when_searching(self, atm):
        response = MagicMock(status_code=200)
        response.json.return_value = {"collection": []}

        with patch.object(atm, "fetch_soundcloud_client_id", return_value="abc"), \
                patch.object(atm.requests, "get", return_value=response) as get:
            atm.fetch_soundcloud_candidates("Fred again..", "Delilah")

        assert get.call_args.kwargs["headers"] == atm.SOUNDCLOUD_HEADERS

    def test_should_send_the_user_agent_when_scraping_the_client_id(self, atm):
        home = MagicMock(status_code=200, text="https://a-v2.sndcdn.com/assets/55-abc.js")
        bundle = MagicMock(status_code=200, text='client_id:"' + "a" * 32 + '"')

        with patch.object(atm.requests, "get", side_effect=[home, bundle]) as get:
            assert atm.scrape_soundcloud_client_id() == "a" * 32

        for call in get.call_args_list:
            assert call.kwargs["headers"] == atm.SOUNDCLOUD_HEADERS


class TestFindBestCover:
    def _stub_providers(self, atm, spotify, soundcloud):
        return (
            patch.object(atm, "fetch_spotify_candidates", return_value=spotify),
            patch.object(atm, "fetch_soundcloud_candidates", return_value=soundcloud),
        )

    def _best(self, atm, spotify, soundcloud, artist="Fred again..", title="Delilah"):
        spotify_patch, soundcloud_patch = self._stub_providers(atm, spotify, soundcloud)
        with spotify_patch, soundcloud_patch:
            return atm.find_best_cover(artist, title)

    def test_should_choose_soundcloud_when_it_matches_the_tags_more_closely(
        self, atm, make_candidate
    ):
        spotify = [make_candidate(atm.CoverSource.SPOTIFY, "Drake", "Family Matters")]
        soundcloud = [make_candidate(atm.CoverSource.SOUNDCLOUD, "Fred again..", "Delilah")]

        best = self._best(atm, spotify, soundcloud)

        assert best.candidate.source is atm.CoverSource.SOUNDCLOUD

    def test_should_choose_spotify_when_it_matches_the_tags_more_closely(
        self, atm, make_candidate
    ):
        spotify = [make_candidate(atm.CoverSource.SPOTIFY, "Fred again..", "Delilah")]
        soundcloud = [
            make_candidate(atm.CoverSource.SOUNDCLOUD, "WNTRZ", "Delilah (WNTRZ Remix)")
        ]

        best = self._best(atm, spotify, soundcloud)

        assert best.candidate.source is atm.CoverSource.SPOTIFY

    def test_should_prefer_spotify_when_both_sources_match_equally_well(
        self, atm, make_candidate
    ):
        spotify = [make_candidate(atm.CoverSource.SPOTIFY, "Fred again..", "Delilah")]
        soundcloud = [make_candidate(atm.CoverSource.SOUNDCLOUD, "Fred again..", "Delilah")]

        best = self._best(atm, spotify, soundcloud)

        assert best.candidate.source is atm.CoverSource.SPOTIFY
        assert best.score == 1.0

    def test_should_pick_the_original_over_a_remix_within_one_source(
        self, atm, make_candidate
    ):
        soundcloud = [
            make_candidate(atm.CoverSource.SOUNDCLOUD, "WNTRZ", "Delilah (WNTRZ Remix)"),
            make_candidate(atm.CoverSource.SOUNDCLOUD, "Fred again..", "Delilah"),
        ]

        best = self._best(atm, [], soundcloud)

        assert best.candidate.title == "Delilah"

    def test_should_return_none_when_neither_source_yields_candidates(self, atm):
        assert self._best(atm, [], []) is None

    def test_should_still_return_a_cover_when_one_provider_fails(self, atm, make_candidate):
        soundcloud = [make_candidate(atm.CoverSource.SOUNDCLOUD, "Fred again..", "Delilah")]

        with patch.object(atm, "fetch_spotify_candidates", side_effect=OSError("no network")), \
                patch.object(atm, "fetch_soundcloud_candidates", return_value=soundcloud):
            best = atm.find_best_cover("Fred again..", "Delilah")

        assert best.candidate.source is atm.CoverSource.SOUNDCLOUD

    def test_should_return_none_when_both_providers_fail(self, atm):
        with patch.object(atm, "fetch_spotify_candidates", side_effect=OSError("no network")), \
                patch.object(
                    atm, "fetch_soundcloud_candidates",
                    side_effect=atm.CoverLookupError("no client_id"),
                ):
            assert atm.find_best_cover("Fred again..", "Delilah") is None


class TestDownloadAndSetCoverPhoto:
    def test_should_write_artwork_from_the_best_scoring_candidate(
        self, atm, make_candidate, fake_metadata
    ):
        metadata, written = fake_metadata("Fred again..", "Delilah")
        winner = make_candidate(atm.CoverSource.SOUNDCLOUD, "Fred again..", "Delilah")

        with patch.object(atm, "find_best_cover", return_value=atm.ScoredCover(winner, 0.98)), \
                patch.object(atm, "download_image", return_value=b"JPEG") as download:
            atm.download_and_set_cover_photo(metadata)

        assert written == {"artwork": b"JPEG"}
        download.assert_called_once_with(winner.image_url)

    def test_should_not_write_artwork_when_the_best_match_is_too_weak(
        self, atm, make_candidate, fake_metadata
    ):
        metadata, written = fake_metadata("Fred again..", "Delilah")
        weak = make_candidate(atm.CoverSource.SPOTIFY, "Drake", "Family Matters")

        with patch.object(atm, "find_best_cover", return_value=atm.ScoredCover(weak, 0.2)), \
                patch.object(atm, "download_image") as download:
            atm.download_and_set_cover_photo(metadata)

        assert written == {}
        download.assert_not_called()

    def test_should_not_write_artwork_when_no_candidate_was_found(self, atm, fake_metadata):
        metadata, written = fake_metadata("Fred again..", "Delilah")

        with patch.object(atm, "find_best_cover", return_value=None):
            atm.download_and_set_cover_photo(metadata)

        assert written == {}

    @pytest.mark.parametrize("artist,title", [
        ("Fred again..", None),
        ("Fred again..", "   "),
        (None, None),
        ("", ""),
    ])
    def test_should_skip_lookup_when_no_title_can_be_determined(
        self, atm, fake_metadata, artist, title
    ):
        metadata, written = fake_metadata(artist, title)

        with patch.object(atm, "find_best_cover") as lookup:
            atm.download_and_set_cover_photo(metadata)

        lookup.assert_not_called()
        assert written == {}

    def test_should_look_up_by_title_alone_when_the_artist_tag_is_missing(
        self, atm, make_candidate, fake_metadata
    ):
        metadata, written = fake_metadata(None, "Delilah")
        winner = make_candidate(atm.CoverSource.SPOTIFY, "Fred again..", "Delilah")

        with patch.object(atm, "find_best_cover", return_value=atm.ScoredCover(winner, 1.0)) as lookup, \
                patch.object(atm, "download_image", return_value=b"JPEG"):
            atm.download_and_set_cover_photo(metadata)

        lookup.assert_called_once_with("", "Delilah")
        assert written == {"artwork": b"JPEG"}

    def test_should_not_write_artwork_when_the_image_download_fails(
        self, atm, make_candidate, fake_metadata
    ):
        metadata, written = fake_metadata("Fred again..", "Delilah")
        winner = make_candidate(atm.CoverSource.SOUNDCLOUD, "Fred again..", "Delilah")

        with patch.object(atm, "find_best_cover", return_value=atm.ScoredCover(winner, 0.98)), \
                patch.object(atm, "download_image", return_value=None):
            atm.download_and_set_cover_photo(metadata)

        assert written == {}
