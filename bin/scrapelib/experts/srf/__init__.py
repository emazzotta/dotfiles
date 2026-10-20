"""Expert for srf.ch articles: CMS markup plus SRG SSR's integration layer for media."""

from __future__ import annotations

from typing import Final
from urllib.parse import urlparse

from scrapelib.article import Article
from scrapelib.experts.base import Extraction, Page
from scrapelib.experts.srf.media import SrfMedia
from scrapelib.experts.srf.page import ARTICLE, SrfPageReader
from scrapelib.experts.srf.ticker import SrfTicker
from scrapelib.fetch import Fetcher

SRF_HOSTS: Final = frozenset({"srf.ch", "www.srf.ch"})


class SrfExpert:
    name = "srf"

    def matches(self, page: Page) -> bool:
        host = urlparse(page.url).hostname or ""
        return host in SRF_HOSTS and page.soup.select_one(ARTICLE) is not None

    def extract(self, page: Page, fetcher: Fetcher) -> Article:
        extraction = Extraction(page, fetcher)
        media = SrfMedia(extraction)
        return SrfPageReader(extraction, media, SrfTicker(extraction, media)).article()
