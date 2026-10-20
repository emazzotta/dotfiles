"""SRF images (rokka, il) and clips, streamed per the SRG SSR integration layer."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import parse_qs, urlparse

from scrapelib.article import Asset, Clip, ClipKind, Transfer, Url
from scrapelib.experts.base import Extraction
from scrapelib.values import first_text, milliseconds, parse_datetime

ROKKA_IMAGE_URL: Final = "https://www.srf.ch/static/cms/images/1280w/{image_id}.jpg"
MEDIA_COMPOSITION_URL: Final = (
    "https://il.srgssr.ch/integrationlayer/2.0/mediaComposition/byUrn/"
    "{urn}.json?onlyChapters=true"
)
PROGRESSIVE_PROTOCOLS: Final = frozenset({"HTTP", "HTTPS"})
HLS_STREAMING: Final = "HLS"
UNSUPPORTED_TOKEN: Final = "AKAMAI"
QUALITY_RANK: Final = {"HD": 2, "SD": 1}
MIME_PREFIX: Final = {ClipKind.AUDIO: "audio/", ClipKind.VIDEO: "video/"}


@dataclass(frozen=True)
class Stream:
    url: Url
    transfer: Transfer


def image_url(provider: str, image_id: str) -> Url | None:
    if not image_id:
        return None
    if provider == "rokka":
        return Url(ROKKA_IMAGE_URL.format(image_id=image_id))
    if provider == "il":
        originals = parse_qs(urlparse(image_id).query).get("imageUrl")
        return Url(originals[0]) if originals else None
    return None


def chapter_of(composition: Any, urn: str) -> Mapping[str, Any] | None:
    chapters = (
        composition.get("chapterList", []) if isinstance(composition, Mapping) else []
    )
    return next((chapter for chapter in chapters if chapter.get("urn") == urn), None)


def unplayable_reason(chapter: Mapping[str, Any] | None) -> str:
    if chapter is None:
        return "missing from its media composition"
    if chapter.get("blockReason"):
        return f"blocked ({chapter['blockReason']})"
    if chapter.get("drmList"):
        return "DRM-protected"
    resources = chapter.get("resourceList", [])
    if resources and all(
        item.get("tokenType") == UNSUPPORTED_TOKEN for item in resources
    ):
        return "needs an Akamai token, which scrape does not fetch"
    return ""


def best_quality(resources: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    return max(
        resources,
        key=lambda item: QUALITY_RANK.get(item.get("quality"), 0),
        default=None,
    )


def is_progressive(resource: Mapping[str, Any], kind: ClipKind) -> bool:
    mime = str(resource.get("mimeType", ""))
    return resource.get("protocol") in PROGRESSIVE_PROTOCOLS and mime.startswith(
        MIME_PREFIX[kind]
    )


def pick_stream(chapter: Mapping[str, Any], kind: ClipKind) -> Stream | None:
    resources = [
        item
        for item in chapter.get("resourceList", [])
        if item.get("tokenType") != UNSUPPORTED_TOKEN
    ]
    progressive = best_quality(item for item in resources if is_progressive(item, kind))
    whole_clip = kind is ClipKind.AUDIO or not chapter.get("fullLengthUrn")
    if progressive is not None and whole_clip:
        return Stream(Url(str(progressive["url"])), Transfer.FILE)
    hls = best_quality(
        item for item in resources if item.get("streaming") == HLS_STREAMING
    )
    return None if hls is None else Stream(Url(str(hls["url"])), Transfer.HLS)


class SrfMedia:
    def __init__(self, extraction: Extraction) -> None:
        self._extraction = extraction

    def image(self, provider: str, image_id: str) -> Asset | None:
        url = image_url(provider, image_id)
        return None if url is None else self._extraction.namer.image(url)

    def clip(self, asset: Mapping[str, Any]) -> Clip | None:
        urn = str(asset.get("urn", ""))
        kind = ClipKind.VIDEO if asset.get("type") == "video" else ClipKind.AUDIO
        title = first_text(asset.get("title"), urn)
        stream = self._stream(urn, kind, title)
        if stream is None:
            return None
        media = self._extraction.namer.clip(kind, stream.url, title, stream.transfer)
        published = parse_datetime(asset.get("date"))
        duration = milliseconds(asset.get("duration"))
        return Clip(
            kind, title, media, published, duration, self._poster(asset.get("image"))
        )

    def _poster(self, image: object) -> Asset | None:
        if not isinstance(image, Mapping):
            return None
        return self.image(str(image.get("provider") or ""), str(image.get("id") or ""))

    def _stream(self, urn: str, kind: ClipKind, title: str) -> Stream | None:
        url = Url(MEDIA_COMPOSITION_URL.format(urn=urn))
        chapter = chapter_of(self._extraction.fetcher.fetch_json(url), urn)
        reason = unplayable_reason(chapter)
        if reason or chapter is None:
            self._extraction.warn(f"skipped the clip {title!r}: {reason}")
            return None
        stream = pick_stream(chapter, kind)
        if stream is None:
            self._extraction.warn(f"skipped the clip {title!r}: no downloadable stream")
        return stream
