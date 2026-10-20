"""What every expert implements, and the per-article state its helpers share."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from bs4 import BeautifulSoup

from scrapelib.article import Article, AssetNamer, Url
from scrapelib.fetch import Fetcher


@dataclass(frozen=True)
class Page:
    url: Url
    html: str
    soup: BeautifulSoup


class Expert(Protocol):
    name: str

    def matches(self, page: Page) -> bool: ...

    def extract(self, page: Page, fetcher: Fetcher) -> Article: ...


@dataclass
class Extraction:
    page: Page
    fetcher: Fetcher
    namer: AssetNamer = field(default_factory=AssetNamer)
    warnings: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        self.warnings.append(message)
