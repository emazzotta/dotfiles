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
