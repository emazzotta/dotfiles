"""One scrape: fetch the page, let an expert read it, save media, write article.html."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from bs4 import BeautifulSoup

from scrapelib.article import Article, Asset, Url, article_assets, safe_filename
from scrapelib.experts import expert_for
from scrapelib.experts.base import Page
from scrapelib.fetch import Downloader, Fetcher, Runner, Saved, run_quietly
from scrapelib.render import render_page

PAGE_NAME: Final = "article.html"
UNTITLED: Final = "article"


@dataclass(frozen=True)
class Result:
    page: Path
    expert: str
    warnings: tuple[str, ...]


def ignore_saved(asset: Asset, path: Path) -> None:
    return None


def folder_name(article: Article) -> str:
    title = safe_filename(article.header.title) or UNTITLED
    published = article.header.published
    return f"{published:%Y-%m-%d} {title}" if published is not None else title


def fetch_page(url: Url, fetcher: Fetcher) -> Page:
    final_url, page_html = fetcher.fetch_html(url)
    return Page(final_url, page_html, BeautifulSoup(page_html, "html5lib"))


class Scraper:
    def __init__(
        self,
        fetcher: Fetcher,
        run: Runner = run_quietly,
        on_saved: Saved = ignore_saved,
    ) -> None:
        self._fetcher = fetcher
        self._downloader = Downloader(fetcher, run)
        self._on_saved = on_saved

    def scrape(
        self, url: Url, out_parent: Path, expert_name: str | None = None
    ) -> Result:
        page = fetch_page(url, self._fetcher)
        expert = expert_for(page, expert_name)
        article = expert.extract(page, self._fetcher)
        folder = out_parent / folder_name(article)
        folder.mkdir(parents=True, exist_ok=True)
        failures: list[str] = []
        self._downloader.save_all(
            article_assets(article),
            folder,
            self._on_saved,
            lambda asset, reason: failures.append(
                f"could not save {asset.local_path}: {reason}"
            ),
        )
        target = folder / PAGE_NAME
        target.write_text(render_page(article), encoding="utf-8")
        return Result(target, expert.name, article.warnings + tuple(failures))
