"""Site-independent article model: experts build it, downloads and rendering use it."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
from functools import singledispatch
from pathlib import Path
from typing import Final, NewType, Union
from urllib.parse import urlparse

Url = NewType("Url", str)

IMAGE_DIR: Final = Path("images")
AUDIO_DIR: Final = Path("audio")
VIDEO_DIR: Final = Path("video")
MAX_NAME_LENGTH: Final = 80
UNSAFE_FILENAME_CHARS: Final = re.compile(r'[\x00-\x1f/\\:*?"<>|]+')
WHITESPACE: Final = re.compile(r"\s+")
NAME_TRIM: Final = " .-"
IMAGE_SUFFIXES: Final = frozenset(
    {".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
)
AUDIO_SUFFIXES: Final = frozenset(
    {".aac", ".m4a", ".mp3", ".oga", ".ogg", ".opus", ".wav"}
)
VIDEO_SUFFIXES: Final = frozenset({".m4v", ".mov", ".mp4", ".webm"})


class Transfer(Enum):
    FILE = auto()
    HLS = auto()


class ClipKind(Enum):
    AUDIO = auto()
    VIDEO = auto()


@dataclass(frozen=True)
class Asset:
    url: Url
    local_path: Path
    transfer: Transfer = Transfer.FILE


@dataclass(frozen=True)
class Paragraph:
    html: str


@dataclass(frozen=True)
class Heading:
    level: int
    text: str


@dataclass(frozen=True)
class ListBlock:
    items: tuple[str, ...]
    ordered: bool = False


@dataclass(frozen=True)
class Quote:
    html: str
    source: str = ""


@dataclass(frozen=True)
class Figure:
    image: Asset
    caption: str = ""
    credit: str = ""
    alt: str = ""
    link: Url | None = None


@dataclass(frozen=True)
class Gallery:
    figures: tuple[Figure, ...]
    title: str = ""
    caption: str = ""


@dataclass(frozen=True)
class Clip:
    kind: ClipKind
    title: str
    media: Asset
    published: datetime | None = None
    duration: timedelta | None = None
    poster: Asset | None = None


@dataclass(frozen=True)
class Embed:
    url: Url
    title: str = ""


@dataclass(frozen=True)
class Table:
    rows: tuple[tuple[str, ...], ...]
    header: bool = False


@dataclass(frozen=True)
class Box:
    title: str
    blocks: tuple[Block, ...]
    published: datetime | None = None


Block = Union[
    Paragraph, Heading, ListBlock, Quote, Figure, Gallery, Clip, Embed, Table, Box
]


@dataclass(frozen=True)
class Header:
    title: str
    overline: str = ""
    lead: str = ""
    author: str = ""
    published: datetime | None = None
    language: str = "en"
    site: str = ""


@dataclass(frozen=True)
class Article:
    header: Header
    source_url: Url
    blocks: tuple[Block, ...]
    warnings: tuple[str, ...] = ()


def safe_filename(text: str, limit: int = MAX_NAME_LENGTH) -> str:
    cleaned = WHITESPACE.sub(" ", UNSAFE_FILENAME_CHARS.sub(" - ", text)).strip(
        NAME_TRIM
    )
    if len(cleaned) <= limit:
        return cleaned
    head = cleaned[: limit + 1]
    cut = head.rsplit(" ", 1)[0] if " " in head else cleaned[:limit]
    return cut.rstrip(NAME_TRIM)


def url_suffix(url: Url, known: frozenset[str], default: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in known else default


def clip_suffix(kind: ClipKind, url: Url, transfer: Transfer) -> str:
    if kind is ClipKind.VIDEO:
        return (
            ".mp4"
            if transfer is Transfer.HLS
            else url_suffix(url, VIDEO_SUFFIXES, ".mp4")
        )
    return (
        ".m4a" if transfer is Transfer.HLS else url_suffix(url, AUDIO_SUFFIXES, ".mp3")
    )


class AssetNamer:
    def __init__(self) -> None:
        self._counts: Counter[Path] = Counter()
        self._assets: dict[Url, Asset] = {}

    def image(self, url: Url) -> Asset:
        suffix = url_suffix(url, IMAGE_SUFFIXES, ".jpg")
        return self._asset(url, IMAGE_DIR, "", suffix, Transfer.FILE)

    def clip(self, kind: ClipKind, url: Url, title: str, transfer: Transfer) -> Asset:
        folder = VIDEO_DIR if kind is ClipKind.VIDEO else AUDIO_DIR
        suffix = clip_suffix(kind, url, transfer)
        return self._asset(url, folder, safe_filename(title), suffix, transfer)

    def _asset(
        self, url: Url, folder: Path, label: str, suffix: str, transfer: Transfer
    ) -> Asset:
        known = self._assets.get(url)
        if known is not None:
            return known
        self._counts[folder] += 1
        stem = (
            f"{self._counts[folder]:02d} {label}"
            if label
            else f"{self._counts[folder]:02d}"
        )
        asset = Asset(url, folder / f"{stem}{suffix}", transfer)
        self._assets[url] = asset
        return asset


@singledispatch
def assets_in(block: object) -> Iterator[Asset]:
    return iter(())


@assets_in.register
def figure_assets(block: Figure) -> Iterator[Asset]:
    return iter((block.image,))


@assets_in.register
def gallery_assets(block: Gallery) -> Iterator[Asset]:
    return (figure.image for figure in block.figures)


@assets_in.register
def clip_assets(block: Clip) -> Iterator[Asset]:
    return iter((block.media,) if block.poster is None else (block.poster, block.media))


@assets_in.register
def box_assets(block: Box) -> Iterator[Asset]:
    return (asset for child in block.blocks for asset in assets_in(child))


def article_assets(article: Article) -> tuple[Asset, ...]:
    found = (asset for block in article.blocks for asset in assets_in(block))
    return tuple(dict.fromkeys(found))
