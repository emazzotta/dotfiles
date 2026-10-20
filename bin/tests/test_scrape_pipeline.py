import pytest

from .scrape_support import (
    CLIP_MP3,
    LOREM,
    MP3,
    PAGE_URL,
    POSTER,
    FakeFetcher,
    composition,
    srf_asset,
    srf_page,
    srf_player,
)

AUDIO_URN = "urn:srf:audio:7a1af3be-b996-3602-b224-27d0f9a2edb0"


@pytest.fixture
def scraper_for(load_module):
    pipeline = load_module("scrapelib.pipeline")
    media = load_module("scrapelib.experts.srf.media")

    def _scraper(files, saved):
        player = srf_player(srf_asset(AUDIO_URN, "audio", "Echo"))
        page = srf_page(
            f'<p class="article-paragraph">{LOREM}</p>',
            top_media=f'<section class="articlepage__topmedia">{player}</section>',
        )
        fetcher = FakeFetcher(
            pages={PAGE_URL: page},
            json_responses={
                media.MEDIA_COMPOSITION_URL.format(urn=AUDIO_URN): composition(
                    AUDIO_URN, [MP3]
                )
            },
            files=files,
        )
        return pipeline.Scraper(
            fetcher, on_saved=lambda asset, path: saved.append(path)
        )

    return _scraper


def should_save_the_page_and_its_media_in_a_folder_named_by_date_and_title(
    scraper_for, tmp_path
):
    saved = []

    result = scraper_for({CLIP_MP3: b"mp3", POSTER: b"jpg"}, saved).scrape(
        PAGE_URL, tmp_path
    )

    folder = tmp_path / "2026-10-19 Beispieltitel - Teil 1"
    assert result.page == folder / "article.html"
    assert (result.expert, result.warnings) == ("srf", ())
    assert saved == [folder / "images" / "01.jpg", folder / "audio" / "01 Echo.mp3"]
    page = result.page.read_text(encoding="utf-8")
    assert 'src="audio/01%20Echo.mp3"' in page
    assert LOREM in page


def should_report_a_download_that_failed_as_a_warning(scraper_for, tmp_path):
    result = scraper_for({CLIP_MP3: b"mp3"}, []).scrape(PAGE_URL, tmp_path)

    assert result.warnings == (
        f"could not save images/01.jpg: HTTP Error 404: {POSTER}",
    )
    assert result.page.exists()
