from pathlib import Path

import pytest

from .scrape_support import FakeFetcher

MASTER = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=596000,RESOLUTION=480x270
v1.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=6130000,RESOLUTION=1920x1080
v5.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=298000,RESOLUTION=320x180
v0.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=6130000,RESOLUTION=1280x720
v4.m3u8
"""


@pytest.fixture
def fetch(load_module):
    return load_module("scrapelib.fetch")


@pytest.fixture
def article(load_module):
    return load_module("scrapelib.article")


def unexpected_failure(asset, reason):
    pytest.fail(f"{asset.local_path} failed: {reason}")


def should_pick_the_highest_bandwidth_then_resolution_from_an_unsorted_master(fetch):
    assert fetch.best_variant(MASTER) == 1


def should_find_no_variant_in_a_media_playlist(fetch):
    assert fetch.best_variant("#EXTM3U\n#EXTINF:6.0,\nsegment0.ts\n") is None


def should_map_one_program_when_building_the_ffmpeg_command(fetch, tmp_path):
    target = tmp_path / "v.mp4.part"

    command = fetch.hls_command("https://x.example/master.m3u8", 3, target)

    maps = [command[index + 1] for index, arg in enumerate(command) if arg == "-map"]
    assert command[command.index("-i") + 1] == "https://x.example/master.m3u8"
    assert maps == ["0:p:3:v:0?", "0:p:3:a:0?"]
    assert command[-3:] == ["-f", "mp4", str(target)]


def should_save_files_atomically_and_keep_files_already_finished(
    fetch, article, tmp_path
):
    fresh = article.Asset("https://x.example/new.jpg", Path("images/01.jpg"))
    kept = article.Asset("https://x.example/old.jpg", Path("images/02.jpg"))
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "02.jpg").write_bytes(b"old")
    fetcher = FakeFetcher(files={fresh.url: b"new"})
    saved = []

    fetch.Downloader(fetcher).save_all(
        [fresh, kept],
        tmp_path,
        lambda asset, path: saved.append(asset.local_path),
        unexpected_failure,
    )

    assert (tmp_path / "images" / "01.jpg").read_bytes() == b"new"
    assert (tmp_path / "images" / "02.jpg").read_bytes() == b"old"
    assert fetcher.requested == [fresh.url]
    assert saved == [Path("images/01.jpg"), Path("images/02.jpg")]
    assert list(tmp_path.rglob("*.part")) == []


def should_report_a_failed_download_and_continue_with_the_rest(
    fetch, article, tmp_path
):
    missing = article.Asset("https://x.example/missing.jpg", Path("images/01.jpg"))
    present = article.Asset("https://x.example/ok.jpg", Path("images/02.jpg"))
    failures = []

    fetch.Downloader(FakeFetcher(files={present.url: b"ok"})).save_all(
        [missing, present],
        tmp_path,
        lambda asset, path: None,
        lambda asset, reason: failures.append((asset.local_path, reason)),
    )

    assert failures == [
        (Path("images/01.jpg"), "HTTP Error 404: https://x.example/missing.jpg")
    ]
    assert (tmp_path / "images" / "02.jpg").read_bytes() == b"ok"
    assert not (tmp_path / "images" / "01.jpg").exists()


def should_download_hls_through_ffmpeg_into_a_partial_file(fetch, article, tmp_path):
    asset = article.Asset(
        "https://x.example/master.m3u8", Path("video/01 Clip.mp4"), article.Transfer.HLS
    )
    commands = []

    def fake_ffmpeg(command):
        commands.append(command)
        Path(command[-1]).write_bytes(b"mp4")

    downloader = fetch.Downloader(
        FakeFetcher(texts={asset.url: MASTER}), run=fake_ffmpeg
    )
    downloader.save_all([asset], tmp_path, lambda asset, path: None, unexpected_failure)

    assert (tmp_path / "video" / "01 Clip.mp4").read_bytes() == b"mp4"
    assert commands[0][-1] == str(tmp_path / "video" / "01 Clip.mp4.part")
    assert "0:p:1:v:0?" in commands[0]
