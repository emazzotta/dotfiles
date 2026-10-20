import pytest

from .scrape_support import (
    CLIP_HLS,
    CLIP_MP3,
    CLIP_MP4_HD,
    HLS,
    MP3,
    MP4_HD,
    MP4_SD,
    PAGE_URL,
    POSTER,
    POSTER_ID,
    FakeFetcher,
    composition,
    srf_asset,
)

VIDEO_URN = "urn:srf:video:d02702ea-bf3b-45eb-889a-3e9229f46b6c"
AUDIO_URN = "urn:srf:audio:7a1af3be-b996-3602-b224-27d0f9a2edb0"


@pytest.fixture
def media(load_module):
    return load_module("scrapelib.experts.srf.media")


@pytest.fixture
def clip_kind(load_module):
    return load_module("scrapelib.article").ClipKind


@pytest.fixture
def media_for(load_module, media):
    base = load_module("scrapelib.experts.base")
    bs4 = load_module("bs4")

    def _media(responses):
        page = base.Page(
            PAGE_URL, "<html></html>", bs4.BeautifulSoup("<html></html>", "html5lib")
        )
        extraction = base.Extraction(page, FakeFetcher(json_responses=responses))
        return media.SrfMedia(extraction), extraction

    return _media


def should_resolve_rokka_ids_and_il_resizer_urls_to_the_largest_image(media):
    assert (
        media.image_url("rokka", "bdf5f6")
        == "https://www.srf.ch/static/cms/images/1280w/bdf5f6.jpg"
    )
    assert media.image_url("il", POSTER_ID) == POSTER
    assert media.image_url("other", "x") is None


@pytest.mark.parametrize(
    ("resources", "chapter", "expected_url", "transfer"),
    [
        pytest.param(
            [MP4_HD, HLS],
            {"fullLengthUrn": "urn:srf:video:full"},
            CLIP_HLS,
            "HLS",
            id="cut-out",
        ),
        pytest.param(
            [MP4_SD, MP4_HD, HLS], {}, CLIP_MP4_HD, "FILE", id="standalone-with-mp4"
        ),
        pytest.param([HLS], {}, CLIP_HLS, "HLS", id="standalone-hls-only"),
    ],
)
def should_pick_the_stream_that_holds_exactly_the_clip(
    media, clip_kind, resources, chapter, expected_url, transfer
):
    stream = media.pick_stream(
        {"urn": VIDEO_URN, "resourceList": resources, **chapter}, clip_kind.VIDEO
    )

    assert (stream.url, stream.transfer.name) == (expected_url, transfer)


def should_use_the_mp3_for_audio_even_when_it_belongs_to_a_broadcast(media, clip_kind):
    chapter = {
        "urn": AUDIO_URN,
        "resourceList": [MP3],
        "fullLengthUrn": "urn:srf:audio:full",
    }

    stream = media.pick_stream(chapter, clip_kind.AUDIO)

    assert (stream.url, stream.transfer.name) == (CLIP_MP3, "FILE")


@pytest.mark.parametrize(
    ("chapter", "reason"),
    [
        pytest.param(
            {"blockReason": "GEOBLOCK"}, "blocked (GEOBLOCK)", id="geoblocked"
        ),
        pytest.param({"drmList": [{"type": "WIDEVINE"}]}, "DRM-protected", id="drm"),
        pytest.param(
            {"resourceList": [{**HLS, "tokenType": "AKAMAI"}]},
            "needs an Akamai token, which scrape does not fetch",
            id="akamai-token",
        ),
    ],
)
def should_skip_a_clip_it_cannot_download_with_a_warning(
    media, media_for, chapter, reason
):
    responses = {
        media.MEDIA_COMPOSITION_URL.format(urn=VIDEO_URN): composition(
            VIDEO_URN, [HLS], **chapter
        )
    }
    srf_media, extraction = media_for(responses)

    clip = srf_media.clip(srf_asset(VIDEO_URN))

    assert clip is None
    assert extraction.warnings == [f"skipped the clip 'Beispielclip': {reason}"]
