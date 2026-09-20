import asyncio
import base64
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = "snl-sync"
ANSI_CODE = re.compile(r"\x1b\[[0-9;]*m")
BOT_USERNAME_LITERAL = re.compile(r'"[A-Za-z0-9]+[Bb]ot"')


@pytest.fixture
def snl(load_script):
    return load_script(SCRIPT)


def make_track(snl, track_id="abc", name="Song", artists=("A", "B")):
    return snl.Track(id=track_id, name=name, artists=tuple(artists))


class TestTrack:
    def should_build_a_track_from_a_playlist_item(self, snl):
        item = {"track": {"id": "abc", "name": "Song", "is_local": False,
                          "artists": [{"name": "A"}, {"name": "B"}]}}

        track = snl.Track.from_playlist_item(item)

        assert track == make_track(snl)

    @pytest.mark.parametrize("item", [
        {"track": None},
        {"track": {"id": None, "name": "Local", "is_local": True, "artists": []}},
    ])
    def should_skip_local_and_missing_tracks(self, snl, item):
        assert snl.Track.from_playlist_item(item) is None

    def should_render_the_spotify_url_and_label(self, snl):
        track = make_track(snl)

        assert track.url == "https://open.spotify.com/track/abc"
        assert track.label == "A, B - Song"


class TestFindPlaylist:
    PLAYLISTS = [{"id": "p0", "name": "00 Listen Later"}, {"id": "p1", "name": "01 Sort'n'Load"}]

    @pytest.mark.parametrize("wanted", ["01 Sort'n'Load", "01_Sort'n'Load", "01 sort'n'load"])
    def should_match_names_ignoring_case_and_underscores(self, snl, wanted):
        playlist = snl.find_playlist(self.PLAYLISTS, wanted)

        assert playlist == snl.Playlist(id="p1", name="01 Sort'n'Load")

    def should_fail_when_no_playlist_matches(self, snl):
        with pytest.raises(snl.SyncError, match="not found"):
            snl.find_playlist(self.PLAYLISTS, "nope")


class TestSyncState:
    def should_start_empty_when_the_state_file_is_missing(self, snl, tmp_path):
        state = snl.SyncState.load(tmp_path / "done.json")

        assert not state.is_done("abc")

    def should_persist_done_tracks_across_loads(self, snl, tmp_path):
        path = tmp_path / "nested" / "done.json"
        state = snl.SyncState.load(path)

        state.mark_done(make_track(snl), Path("/x/A - Song.mp3"))
        state.save()

        assert snl.SyncState.load(path).is_done("abc")
        assert json.loads(path.read_text())["abc"]["file"] == "/x/A - Song.mp3"


class TestSelectNewTracks:
    def should_keep_playlist_order_and_skip_done_tracks(self, snl, tmp_path):
        state = snl.SyncState.load(tmp_path / "done.json")
        done = make_track(snl, "old", "Old")
        state.mark_done(done, Path("/x/old.mp3"))
        tracks = [make_track(snl, "n1", "New 1"), done, make_track(snl, "n2", "New 2")]

        assert snl.select_new_tracks(tracks, state) == [tracks[0], tracks[2]]


class FakeFile:
    def __init__(self, name, mime_type):
        self.name = name
        self.mime_type = mime_type


class FakeMessage:
    def __init__(self, text="", audio=False, document=False, file=None, buttons=None):
        self.raw_text = text
        self.audio = object() if audio else None
        self.document = object() if document else None
        self.file = file
        self.buttons = buttons
        self.clicked = None

    async def click(self, *, text):
        self.clicked = text

    async def download_media(self, file):
        target = Path(file) / self.file.name
        target.write_bytes(b"audio")
        return str(target)


def audio_reply(name="A - Song.mp3"):
    return FakeMessage(audio=True, file=FakeFile(name, "audio/mpeg"))


def buttons_reply(rows):
    buttons = [[SimpleNamespace(text=label) for label in row] for row in rows]
    return FakeMessage(text="Choose format", buttons=buttons)


class FakeConversation:
    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send_message(self, text):
        self.sent.append(text)

    async def get_response(self):
        if not self.replies:
            raise asyncio.TimeoutError()
        return self.replies.pop(0)


def fetch(snl, replies, tmp_path, quality="flac", **kwargs):
    conv = FakeConversation(replies)
    track = make_track(snl)
    preferences = snl.QUALITY_PREFERENCES[quality]
    return conv, asyncio.run(snl.fetch_track(conv, track, tmp_path, preferences, **kwargs))


class TestFetchTrack:
    def should_send_the_track_link_and_download_the_audio_reply(self, snl, tmp_path):
        conv, saved = fetch(snl, [audio_reply()], tmp_path)

        assert conv.sent == ["https://open.spotify.com/track/abc"]
        assert saved == tmp_path / "A - Song.mp3"
        assert saved.read_bytes() == b"audio"

    def should_treat_an_audio_document_as_audio(self, snl, tmp_path):
        reply = FakeMessage(document=True, file=FakeFile("A - Song.flac", "audio/flac"))

        _, saved = fetch(snl, [reply], tmp_path)

        assert saved == tmp_path / "A - Song.flac"

    def should_click_the_preferred_quality_button_before_downloading(self, snl, tmp_path):
        choice = buttons_reply([["MP3 128", "MP3 320"], ["FLAC"]])

        fetch(snl, [choice, audio_reply()], tmp_path, quality="flac")

        assert choice.clicked == "FLAC"

    def should_fall_back_to_the_next_quality_when_the_preferred_is_missing(self, snl, tmp_path):
        choice = buttons_reply([["MP3 128", "MP3 320"]])

        fetch(snl, [choice, audio_reply()], tmp_path, quality="flac")

        assert choice.clicked == "MP3 320"

    def should_fail_naming_the_buttons_when_none_matches_a_quality(self, snl, tmp_path):
        choice = buttons_reply([["Track A", "Track B"]])

        with pytest.raises(snl.FetchError, match="Track A, Track B"):
            fetch(snl, [choice, audio_reply()], tmp_path)

        assert choice.clicked is None

    def should_wait_through_progress_texts_until_the_audio_arrives(self, snl, tmp_path):
        replies = [FakeMessage(text="Searching..."), FakeMessage(text="Downloading"), audio_reply()]

        _, saved = fetch(snl, replies, tmp_path)

        assert saved.name == "A - Song.mp3"

    def should_fail_with_the_last_bot_text_when_no_audio_arrives_in_time(self, snl, tmp_path):
        with pytest.raises(snl.FetchError, match="Not found"):
            fetch(snl, [FakeMessage(text="Not found")], tmp_path)

    def should_fail_with_a_timeout_message_when_the_bot_stays_silent(self, snl, tmp_path):
        with pytest.raises(snl.FetchError, match="no reply"):
            fetch(snl, [], tmp_path)

    def should_give_up_after_too_many_replies(self, snl, tmp_path):
        replies = [FakeMessage(text=f"step {i}") for i in range(3)] + [audio_reply()]

        with pytest.raises(snl.FetchError, match="3 replies"):
            fetch(snl, replies, tmp_path, max_replies=3)

    def should_send_artist_and_title_when_querying_by_text(self, snl, tmp_path):
        conv, _ = fetch(snl, [audio_reply()], tmp_path, query=snl.QueryMode.TEXT)

        assert conv.sent == ["A, B - Song"]


class TestRunSync:
    def run(self, snl, tmp_path, scripts):
        state = snl.SyncState.load(tmp_path / "state" / "done.json")
        tracks = [make_track(snl, f"t{i}", f"Song {i}") for i in range(len(scripts))]
        conversations = [FakeConversation(replies) for replies in scripts]
        opened = iter(conversations)
        report = asyncio.run(snl.run_sync(
            tracks, lambda: next(opened), tmp_path / "inbox", state,
            snl.QUALITY_PREFERENCES["flac"], delay=0,
        ))
        return report, state, conversations

    def should_download_every_track_and_record_each_success_immediately(self, snl, tmp_path):
        scripts = [[audio_reply("t0.mp3")], [audio_reply("t1.mp3")]]

        report, state, _ = self.run(snl, tmp_path, scripts)

        assert [saved.name for _, saved in report.downloaded] == ["t0.mp3", "t1.mp3"]
        assert report.failed == []
        assert snl.SyncState.load(state.path).is_done("t1")

    def should_keep_going_after_a_failure_and_report_it(self, snl, tmp_path):
        scripts = [[FakeMessage(text="Not found")], [audio_reply("t1.mp3")]]

        report, state, _ = self.run(snl, tmp_path, scripts)

        assert [track.id for track, _ in report.downloaded] == ["t1"]
        assert report.failed == [(snl.Track("t0", "Song 0", ("A", "B")), "bot said 'Not found'")]
        assert not snl.SyncState.load(state.path).is_done("t0")

    def should_open_one_conversation_per_track(self, snl, tmp_path):
        scripts = [[audio_reply("t0.mp3")], [audio_reply("t1.mp3")]]

        _, _, conversations = self.run(snl, tmp_path, scripts)

        assert [conv.sent for conv in conversations] == [["https://open.spotify.com/track/t0"],
                                                         ["https://open.spotify.com/track/t1"]]

    def should_create_the_destination_directory(self, snl, tmp_path):
        self.run(snl, tmp_path, [[audio_reply("t0.mp3")]])

        assert (tmp_path / "inbox" / "t0.mp3").exists()

    def should_announce_each_track_then_its_outcome(self, snl, tmp_path, capsys):
        scripts = [[FakeMessage(text="Not found")], [audio_reply("t1.mp3")]]

        self.run(snl, tmp_path, scripts)

        plain = ANSI_CODE.sub("", capsys.readouterr().out)
        lines = [line.split("] ", 1)[1] for line in plain.splitlines()]
        assert [line.split(":")[0] for line in lines] == [
            "fetching A, B - Song 0", "WARN",
            "fetching A, B - Song 1", "\u2713 A, B - Song 1 -> t1.mp3",
        ]


class FakeHttp:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, url, headers, data=None):
        self.calls.append((url, headers, data))
        return self.responses[url]


def playlist_item(track_id, name="Song"):
    return {"track": {"id": track_id, "name": name, "is_local": False, "artists": [{"name": "A"}]}}


class TestSpotify:
    def should_mint_a_user_token_with_basic_auth_and_the_refresh_grant(self, snl):
        http = FakeHttp({snl.SPOTIFY_TOKEN_URL: {"access_token": "tok"}})

        token = snl.mint_user_token("id", "secret", "refresh", http=http)

        _, headers, data = http.calls[0]
        assert token == "tok"
        assert headers["Authorization"] == "Basic " + base64.b64encode(b"id:secret").decode()
        assert data == b"grant_type=refresh_token&refresh_token=refresh"

    def should_page_through_all_tracks_skipping_unusable_items(self, snl):
        first = snl.SPOTIFY_TRACKS_URL.format(id="p1")
        http = FakeHttp({
            first: {"items": [playlist_item("t1"), {"track": None}], "next": "https://next"},
            "https://next": {"items": [playlist_item("t2")], "next": None},
        })

        playlist = snl.Playlist(id="p1", name="x")

        tracks = snl.SpotifyClient("tok", http=http).fetch_tracks(playlist)

        assert [track.id for track in tracks] == ["t1", "t2"]
        assert http.calls[0][1] == {"Authorization": "Bearer tok"}

    def should_find_the_playlist_on_a_later_page(self, snl):
        http = FakeHttp({
            snl.SPOTIFY_PLAYLISTS_URL: {"items": [{"id": "p0", "name": "00 Listen Later"}],
                                        "next": "https://next"},
            "https://next": {"items": [{"id": "p1", "name": "01 Sort'n'Load"}], "next": None},
        })

        playlist = snl.SpotifyClient("tok", http=http).find_playlist("01_sort'n'load")

        assert playlist == snl.Playlist(id="p1", name="01 Sort'n'Load")


class FakeSpotify:
    tracks = []

    def __init__(self, token, http=None):
        self.token = token

    def find_playlist(self, name):
        return SimpleNamespace(id="p1", name=name)

    def fetch_tracks(self, playlist):
        return list(self.tracks)


class FakeTelegramClient:
    scripts = []
    started = []

    def __init__(self, session, api_id, api_hash):
        self.session = SimpleNamespace(save=lambda: "SESSION-STRING")
        self.api = (api_id, api_hash)
        self._scripts = iter(self.scripts)
        self.entities = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def start(self):
        self.started.append(self.api)

    async def connect(self):
        pass

    async def is_user_authorized(self):
        return True

    async def disconnect(self):
        pass

    async def get_input_entity(self, name):
        if name == "nobody":
            raise ValueError(f'No user has "{name}" as username')
        return f"entity:{name}"

    def conversation(self, entity, timeout):
        self.entities.append(entity)
        return FakeConversation(next(self._scripts))


@pytest.fixture
def cli(snl, tmp_path, monkeypatch):
    loaded = []
    monkeypatch.setattr(snl, "load_env", lambda keys: loaded.append(keys))
    monkeypatch.setattr(snl, "mint_user_token", lambda *args, **kwargs: "tok")
    monkeypatch.setattr(snl, "SpotifyClient", FakeSpotify)
    monkeypatch.setattr(snl, "TelegramClient", FakeTelegramClient)
    monkeypatch.setattr(snl, "StringSession", lambda value=None: value)
    for var in snl.SPOTIFY_VARS + snl.TELEGRAM_VARS:
        monkeypatch.setenv(var, "x")
    monkeypatch.setenv("TELEGRAM_API_ID", "123")
    monkeypatch.setenv("TELEGRAM_MUSIC_BOT", "musicbot")
    monkeypatch.setattr(FakeSpotify, "tracks",
                        [make_track(snl, "t0", "Song 0"), make_track(snl, "t1", "Song 1")])
    monkeypatch.setattr(FakeTelegramClient, "scripts", [])
    monkeypatch.setattr(FakeTelegramClient, "started", [])
    state = tmp_path / "state.json"
    dest = tmp_path / "inbox"

    def _run(*args):
        return snl.main(["--state", str(state), "--dest", str(dest), *args])

    return SimpleNamespace(run=_run, state=state, dest=dest, loaded=loaded, snl=snl)


class TestCli:
    def should_show_usage_for_help(self, run_cli):
        result = run_cli(SCRIPT, ["--help"])

        assert result.returncode == 0
        assert "Sort'n'Load" in result.stdout

    def should_list_pending_tracks_without_telegram_in_dry_run(self, cli, capsys):
        cli.snl.TelegramClient = None

        code = cli.run("--dry-run")

        out = capsys.readouterr().out
        assert code == 0
        assert "A, B - Song 0" in out and "A, B - Song 1" in out
        assert cli.loaded == [cli.snl.SPOTIFY_VARS]
        assert not cli.state.exists()

    def should_fail_clearly_when_telethon_is_missing(self, cli, capsys):
        cli.snl.TelegramClient = None

        code = cli.run()

        assert code == 1
        assert "telethon" in capsys.readouterr().err

    def should_download_pending_tracks_and_exit_zero(self, cli):
        FakeTelegramClient.scripts.extend([[audio_reply("t0.mp3")], [audio_reply("t1.mp3")]])

        code = cli.run("--delay", "0")

        assert code == 0
        assert sorted(p.name for p in cli.dest.iterdir()) == ["t0.mp3", "t1.mp3"]
        assert set(json.loads(cli.state.read_text())) == {"t0", "t1"}
        assert cli.loaded == [cli.snl.SPOTIFY_VARS + cli.snl.TELEGRAM_VARS]

    def should_exit_one_when_a_track_failed(self, cli, capsys):
        FakeTelegramClient.scripts.extend([[FakeMessage(text="Not found")],
                                           [audio_reply("t1.mp3")]])

        code = cli.run("--delay", "0")

        assert code == 1
        assert "Not found" in capsys.readouterr().out

    def should_stop_after_the_limit(self, cli):
        FakeTelegramClient.scripts.extend([[audio_reply("t0.mp3")]])

        code = cli.run("--limit", "1", "--delay", "0")

        assert code == 0
        assert [p.name for p in cli.dest.iterdir()] == ["t0.mp3"]

    def should_talk_to_the_bot_named_in_keyguard(self, cli, monkeypatch):
        clients = []
        monkeypatch.setattr(cli.snl, "TelegramClient",
                            lambda *args: clients.append(FakeTelegramClient(*args)) or clients[-1])
        FakeTelegramClient.scripts.extend([[audio_reply("t0.mp3")], [audio_reply("t1.mp3")]])

        cli.run("--delay", "0")

        assert clients[0].entities == ["entity:musicbot", "entity:musicbot"]

    def should_fail_clearly_when_the_bot_username_does_not_exist(self, cli, monkeypatch, capsys):
        monkeypatch.setenv("TELEGRAM_MUSIC_BOT", "nobody")

        code = cli.run()

        assert code == 1
        assert "TELEGRAM_MUSIC_BOT='nobody'" in capsys.readouterr().err

    def should_hardcode_no_telegram_bot_username(self):
        source = (Path(__file__).parent.parent / SCRIPT).read_text()

        assert BOT_USERNAME_LITERAL.search(source) is None

    def should_store_the_session_after_login(self, cli, monkeypatch):
        stored = []
        monkeypatch.setattr(cli.snl, "store_param", lambda key, value: stored.append((key, value)))

        code = cli.run("--login")

        assert code == 0
        assert stored == [("TELEGRAM_SESSION", "SESSION-STRING")]
        assert FakeTelegramClient.started == [(123, "x")]
        assert cli.loaded == [cli.snl.TELEGRAM_APP_VARS]
