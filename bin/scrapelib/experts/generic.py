"""Fallback expert: JSON-LD and Open Graph metadata, main text via trafilatura."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from pathlib import PurePosixPath
from typing import Any, Callable, Final, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from scrapelib.article import (
    AUDIO_SUFFIXES,
    VIDEO_SUFFIXES,
    Article,
    AssetNamer,
    Block,
    Clip,
    ClipKind,
    Figure,
    Header,
    Transfer,
    Url,
)
from scrapelib.experts.base import Extraction, Page
from scrapelib.fetch import Fetcher
from scrapelib.markup import SemanticReader, attribute, text_of, web_url
from scrapelib.values import first_text, parse_datetime

ARTICLE_TYPES: Final = frozenset(
    {
        "AnalysisNewsArticle",
        "Article",
        "BlogPosting",
        "LiveBlogPosting",
        "NewsArticle",
        "OpinionNewsArticle",
        "ReportageNewsArticle",
        "ReviewNewsArticle",
        "TechArticle",
    }
)
HLS_SUFFIX: Final = ".m3u8"
PLAYER_TAGS: Final = ("video", "audio")
MEDIA_ELEMENTS: Final = "video[src], video source[src], audio[src], audio source[src]"
MEDIA_META: Final = (
    ("og:video:secure_url", ClipKind.VIDEO),
    ("og:video:url", ClipKind.VIDEO),
    ("og:video", ClipKind.VIDEO),
    ("og:audio:secure_url", ClipKind.AUDIO),
    ("og:audio", ClipKind.AUDIO),
)
DEFAULT_LANGUAGE: Final = "en"
AUTHOR_SEPARATOR: Final = ", "

ContentExtractor = Callable[[str, Url], Optional[str]]


def trafilatura_html(page_html: str, url: Url) -> str | None:
    # Imported here: trafilatura needs Python 3.10+, and the bin/tests venv may be 3.9.
    import trafilatura  # noqa: PLC0415

    return trafilatura.extract(
        page_html,
        url=url,
        output_format="html",
        include_images=True,
        include_links=True,
        include_formatting=True,
        include_tables=True,
        favor_recall=True,
    )


def meta(soup: BeautifulSoup, key: str) -> str:
    tag = soup.select_one(f'meta[property="{key}"], meta[name="{key}"]')
    return attribute(tag, "content").strip()


def json_ld_objects(soup: BeautifulSoup) -> Iterator[Mapping[str, Any]]:
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        yield from flatten_json_ld(data)


def flatten_json_ld(data: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(data, list):
        for item in data:
            yield from flatten_json_ld(item)
    elif isinstance(data, Mapping):
        yield data
        yield from flatten_json_ld(data.get("@graph", []))


def is_article(data: Mapping[str, Any]) -> bool:
    kinds = data.get("@type")
    names = kinds if isinstance(kinds, list) else [kinds]
    return any(name in ARTICLE_TYPES for name in names)


def article_data(soup: BeautifulSoup) -> Mapping[str, Any]:
    return next((data for data in json_ld_objects(soup) if is_article(data)), {})


def names_of(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return first_text(value.get("name"))
    if isinstance(value, list):
        return AUTHOR_SEPARATOR.join(name for name in map(names_of, value) if name)
    return ""


def page_language(soup: BeautifulSoup) -> str:
    root = soup.find("html")
    language = attribute(root, "lang") if isinstance(root, Tag) else ""
    return (language or meta(soup, "og:locale") or DEFAULT_LANGUAGE).replace("_", "-")


def header_from(soup: BeautifulSoup) -> Header:
    data = article_data(soup)
    time = soup.select_one("time[datetime]")
    return Header(
        title=first_text(
            data.get("headline"), meta(soup, "og:title"), text_of(soup.title)
        ),
        lead=first_text(
            data.get("description"),
            meta(soup, "og:description"),
            meta(soup, "description"),
        ),
        author=first_text(
            names_of(data.get("author")),
            meta(soup, "author"),
            meta(soup, "article:author"),
        ),
        published=parse_datetime(
            first_text(
                data.get("datePublished"),
                meta(soup, "article:published_time"),
                attribute(time, "datetime"),
            )
        ),
        language=page_language(soup),
        site=first_text(meta(soup, "og:site_name"), names_of(data.get("publisher"))),
    )


def path_suffix(url: Url) -> str:
    return PurePosixPath(urlparse(url).path).suffix.lower()


def media_kind(suffix: str, hint: ClipKind) -> ClipKind | None:
    if suffix == HLS_SUFFIX:
        return hint
    if suffix in VIDEO_SUFFIXES:
        return ClipKind.VIDEO
    return ClipKind.AUDIO if suffix in AUDIO_SUFFIXES else None


def player_of(element: Tag) -> Tag | None:
    if element.name in PLAYER_TAGS:
        return element
    return element.find_parent(list(PLAYER_TAGS))


def media_candidates(page: Page) -> Iterator[tuple[Url, ClipKind, str]]:
    for element in page.soup.select(MEDIA_ELEMENTS):
        player = player_of(element)
        is_video = player is not None and player.name == "video"
        url = web_url(attribute(element, "src"), page.url)
        if url is not None:
            kind = ClipKind.VIDEO if is_video else ClipKind.AUDIO
            yield url, kind, attribute(player, "poster")
    for key, kind in MEDIA_META:
        url = web_url(meta(page.soup, key), page.url)
        if url is not None:
            yield url, kind, ""


def media_clips(page: Page, namer: AssetNamer, title: str) -> tuple[Block, ...]:
    clips: dict[Url, Clip] = {}
    for url, hint, poster in media_candidates(page):
        suffix = path_suffix(url)
        kind = media_kind(suffix, hint)
        if kind is None or url in clips:
            continue
        transfer = Transfer.HLS if suffix == HLS_SUFFIX else Transfer.FILE
        poster_url = web_url(poster, page.url)
        cover = None if poster_url is None else namer.image(poster_url)
        media = namer.clip(kind, url, title, transfer)
        clips[url] = Clip(kind, title, media, poster=cover)
    return tuple(clips.values())


def has_image(blocks: tuple[Block, ...]) -> bool:
    return any(isinstance(block, (Figure, Clip)) for block in blocks)


class GenericExpert:
    name = "generic"

    def __init__(self, content: ContentExtractor = trafilatura_html) -> None:
        self._content = content

    def matches(self, page: Page) -> bool:
        return True

    def extract(self, page: Page, fetcher: Fetcher) -> Article:
        extraction = Extraction(page, fetcher)
        header = header_from(page.soup)
        body = self._body(page, extraction)
        media = media_clips(page, extraction.namer, header.title)
        hero = () if has_image(body + media) else self._hero(page, extraction.namer)
        return Article(
            header, page.url, hero + media + body, tuple(extraction.warnings)
        )

    def _body(self, page: Page, extraction: Extraction) -> tuple[Block, ...]:
        content = self._content(page.html, page.url)
        if not content:
            extraction.warn("found no article text on the page")
            return ()
        root = BeautifulSoup(content, "html5lib").body
        return SemanticReader(page.url, extraction.namer).blocks(root)

    def _hero(self, page: Page, namer: AssetNamer) -> tuple[Block, ...]:
        url = web_url(meta(page.soup, "og:image"), page.url)
        return () if url is None else (Figure(namer.image(url)),)
