"""SRF article markup: header, top media and the body components of the CMS."""

from __future__ import annotations

import html
from collections.abc import Iterable, Mapping
from typing import Any, Callable, Final
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from scrapelib.article import (
    Article,
    Block,
    Box,
    Embed,
    Figure,
    Gallery,
    Header,
    Heading,
    ListBlock,
    Paragraph,
    Quote,
    Url,
)
from scrapelib.experts.base import Extraction
from scrapelib.experts.srf.media import SrfMedia
from scrapelib.experts.srf.ticker import SrfTicker
from scrapelib.markup import (
    absolutize_links,
    all_matches,
    attribute,
    contains,
    first_match,
    inline_html,
    json_attribute,
    own_text_of,
    required,
    text_at,
    text_of,
    web_url,
)
from scrapelib.values import first_text, parse_datetime

ARTICLE: Final = "article.js-article"
TOP_MEDIA: Final = ".articlepage__topmedia"
BODY: Final = ".articlepage__article-content"
PLAYER: Final = ".player-widget[data-asset]"
TICKER: Final = "#ticker[data-api-endpoint]"
BOX: Final = ".expandable-box"
GALLERY: Final = ".image-gallery"
PHOTO_SLIDER: Final = ".js-photo-slider[data-images]"
CLIP_GALLERY: Final = ".js-video-gallery[data-assets], .js-audio-gallery[data-assets]"
FIGURE: Final = "figure.image-figure"
IMAGE: Final = "[data-image-provider][data-image-id]"
DATAWRAPPER: Final = "[id^=datawrapper-vis-]"
DATAWRAPPER_PREFIX: Final = "datawrapper-vis-"
DATAWRAPPER_IMAGE: Final = "https://datawrapper.dwcdn.net/{chart}/full.png"
DATAWRAPPER_CHART: Final = "https://datawrapper.dwcdn.net/{chart}/"
CONSENT_EMBED: Final = ".js-cmp-embed[data-cmp-protected-embed]"
LINK_BOX: Final = "a.block-link[href]"
IGNORED: Final = ", ".join(
    (
        ".js-mehr-zum-thema",
        ".js-related-items-list",
        ".podcast-box",
        ".election-widget",
        ".articlepage__banner-container",
        ".js-end-of-article",
    )
)
IGNORED_TAG_PREFIXES: Final = ("crk-", "logora")
WIDGET_SCRIPT: Final = "script[src*='srf.ch/widgets/']"
LANGUAGE: Final = "de"
SITE: Final = "SRF"
AUTHOR_SEPARATOR: Final = ", "

Predicate = Callable[[Tag], bool]
Reader = Callable[[Tag], "tuple[Block, ...]"]


def has(selector: str) -> Predicate:
    return lambda element: contains(element, selector)


def is_named(*names: str) -> Predicate:
    return lambda element: element.name in names


def is_ignored(element: Tag) -> bool:
    if contains(element, IGNORED) or element.name.startswith(IGNORED_TAG_PREFIXES):
        return True
    if any(tag.name.startswith(IGNORED_TAG_PREFIXES) for tag in element.find_all(True)):
        return True
    return contains(element, WIDGET_SCRIPT) and not text_of(element)


def header_from(root: Tag) -> Header:
    authors = (
        text_of(name) for name in root.select(".article-author__name [itemprop=name]")
    )
    dateline = attribute(
        root.select_one("[data-publicationdate]"), "data-publicationdate"
    )
    microdata = attribute(root.select_one("meta[itemprop=datePublished]"), "content")
    return Header(
        title=first_text(text_at(root, ".article-title__text"), text_at(root, "h1")),
        overline=text_at(root, ".article-title__overline"),
        lead=text_at(root, ".article-lead"),
        author=AUTHOR_SEPARATOR.join(author for author in authors if author),
        published=parse_datetime(first_text(dateline, microdata)),
        language=LANGUAGE,
        site=SITE,
    )


def heading(element: Tag) -> tuple[Block, ...]:
    text = text_of(element)
    return (Heading(int(element.name[1]), text),) if text else ()


def bullet_list(element: Tag) -> tuple[Block, ...]:
    items = tuple(inline_html(item) for item in element.find_all("li", recursive=False))
    return (ListBlock(items, element.name == "ol"),) if any(items) else ()


def paragraph(element: Tag) -> tuple[Block, ...]:
    markup = inline_html(element)
    return (Paragraph(markup),) if markup else ()


def quote(element: Tag) -> tuple[Block, ...]:
    block = required(first_match(element, "blockquote"), "blockquote")
    text = block.select_one(".blockquote__text") or block
    author = text_at(block, ".blockquote__author")
    source = AUTHOR_SEPARATOR.join(
        part for part in (author, text_at(block, ".blockquote__function")) if part
    )
    markup = inline_html(text)
    return (Quote(markup, source),) if markup else ()


def iframe_source(markup: str) -> str:
    iframe = BeautifulSoup(markup, "html5lib").select_one("iframe[src]")
    return attribute(iframe, "src")


def embed_from(data: Any, base: Url) -> Embed | None:
    if not isinstance(data, Mapping):
        return None
    source = data.get("url") or iframe_source(
        str(data.get("html") or data.get("embed") or "")
    )
    url = web_url(source, base)
    if url is None:
        return None
    return Embed(url, first_text(data.get("title"), urlparse(url).hostname))


class SrfPageReader:
    def __init__(
        self, extraction: Extraction, media: SrfMedia, ticker: SrfTicker
    ) -> None:
        self._extraction = extraction
        self._media = media
        self._ticker = ticker
        self._readers: tuple[tuple[Predicate, Reader], ...] = (
            (is_named("p"), paragraph),
            (is_named("h2", "h3", "h4"), heading),
            (is_named("ul", "ol"), bullet_list),
            (has(TICKER), self._live_ticker),
            (has(BOX), self._box),
            (has(GALLERY), self._gallery),
            (has(PHOTO_SLIDER), self._photo_slider),
            (has(CLIP_GALLERY), self._clip_gallery),
            (has("blockquote"), quote),
            (has(FIGURE), self._figures),
            (has(DATAWRAPPER), self._datawrapper),
            (has(CONSENT_EMBED), self._consent_embeds),
            (has(PLAYER), self._clips),
            (has(LINK_BOX), self._link_boxes),
        )

    def article(self) -> Article:
        page = self._extraction.page
        root = required(page.soup.select_one(ARTICLE), "SRF article")
        absolutize_links(root, page.url)
        top_media = self._top_media(root)
        body = self._blocks_in(required(root.select_one(BODY), "SRF article body"))
        warnings = tuple(self._extraction.warnings)
        return Article(header_from(root), page.url, top_media + body, warnings)

    def _top_media(self, root: Tag) -> tuple[Block, ...]:
        top = root.select_one(TOP_MEDIA)
        if top is None:
            return ()
        if contains(top, PLAYER):
            return self._clips(top)
        image = self._figure_from(top)
        if image is None:
            self._extraction.warn(
                "skipped top media that holds neither a player nor an image"
            )
            return ()
        return (image,)

    def _blocks_in(self, container: Tag) -> tuple[Block, ...]:
        children = container.find_all(True, recursive=False)
        return tuple(block for child in children for block in self._blocks_from(child))

    def _blocks_from(self, element: Tag) -> tuple[Block, ...]:
        for matches, read in self._readers:
            if matches(element):
                return read(element)
        if not is_ignored(element):
            classes = " ".join(element.get("class") or [])
            self._extraction.warn(
                f"skipped an unknown component <{element.name} class={classes!r}>"
            )
        return ()

    def _figure_from(self, holder: Tag) -> Figure | None:
        image = holder.select_one(IMAGE)
        if image is None:
            return None
        asset = self._media.image(
            attribute(image, "data-image-provider"), attribute(image, "data-image-id")
        )
        if asset is None:
            return None
        description = holder.select_one(".media-caption__description")
        caption = own_text_of(description) or text_of(description)
        alt = attribute(holder.select_one("img"), "alt")
        return Figure(asset, caption, text_at(holder, ".media-caption__source"), alt)

    def _figures(self, element: Tag) -> tuple[Block, ...]:
        figures = (self._figure_from(figure) for figure in all_matches(element, FIGURE))
        return tuple(figure for figure in figures if figure is not None)

    def _gallery(self, element: Tag) -> tuple[Block, ...]:
        items = element.select("li.image-gallery__item")
        figures = tuple(
            figure for figure in map(self._figure_from, items) if figure is not None
        )
        return (Gallery(figures),) if figures else ()

    def _photo_slider(self, element: Tag) -> tuple[Block, ...]:
        slider = required(first_match(element, PHOTO_SLIDER), "photo slider")
        images = json_attribute(slider, "data-images")
        credit = attribute(slider, "data-source")
        figures = tuple(
            self._slide(image, credit)
            for image in images or []
            if isinstance(image, Mapping)
        )
        present = tuple(figure for figure in figures if figure is not None)
        title, caption = (
            attribute(slider, "data-title"),
            attribute(slider, "data-legend"),
        )
        return (Gallery(present, title, caption),) if present else ()

    def _slide(self, image: Mapping[str, Any], credit: str) -> Figure | None:
        asset = self._media.image(
            str(image.get("provider") or ""), str(image.get("imageId") or "")
        )
        if asset is None:
            return None
        caption = first_text(image.get("legend"), image.get("title"))
        return Figure(
            asset,
            caption,
            first_text(image.get("source"), credit),
            first_text(image.get("alt")),
        )

    def _clips(self, element: Tag) -> tuple[Block, ...]:
        return self._clip_blocks(
            json_attribute(player, "data-asset")
            for player in all_matches(element, PLAYER)
        )

    def _clip_gallery(self, element: Tag) -> tuple[Block, ...]:
        holder = required(first_match(element, CLIP_GALLERY), "clip gallery")
        assets = json_attribute(holder, "data-assets")
        return self._clip_blocks(assets if isinstance(assets, list) else [])

    def _clip_blocks(self, assets: Iterable[Any]) -> tuple[Block, ...]:
        clips = (
            self._media.clip(asset) for asset in assets if isinstance(asset, Mapping)
        )
        return tuple(clip for clip in clips if clip is not None)

    def _box(self, element: Tag) -> tuple[Block, ...]:
        box = required(first_match(element, BOX), "box")
        title = first_text(
            text_at(box, ".content-heading"), text_at(box, ".person-details__name")
        )
        content = box.select_one(".expandable-box__content")
        blocks = self._person(box) + (
            () if content is None else self._blocks_in(content)
        )
        links = tuple(
            block
            for link in box.select(".expandable-box__body > a.block-link[href]")
            for block in self._link_boxes(link)
        )
        return (Box(title, blocks + links),)

    def _person(self, box: Tag) -> tuple[Block, ...]:
        details = box.select_one(".person-details")
        if details is None:
            return ()
        portrait = self._figure_from(box.select_one(".expandable-box__header") or box)
        role = text_at(details, ".person-details__function")
        return tuple(
            block
            for block in (portrait, Paragraph(html.escape(role)) if role else None)
            if block
        )

    def _live_ticker(self, element: Tag) -> tuple[Block, ...]:
        ticker = required(first_match(element, TICKER), "live ticker")
        endpoint = Url(
            urljoin(self._extraction.page.url, attribute(ticker, "data-api-endpoint"))
        )
        title = text_at(ticker, "h2")
        return ((Heading(2, title),) if title else ()) + self._ticker.entries(endpoint)

    def _datawrapper(self, element: Tag) -> tuple[Block, ...]:
        chart = required(first_match(element, DATAWRAPPER), "Datawrapper chart")
        chart_id = attribute(chart, "id").removeprefix(DATAWRAPPER_PREFIX)
        image = self._extraction.namer.image(
            Url(DATAWRAPPER_IMAGE.format(chart=chart_id))
        )
        return (Figure(image, link=Url(DATAWRAPPER_CHART.format(chart=chart_id))),)

    def _consent_embeds(self, element: Tag) -> tuple[Block, ...]:
        base = self._extraction.page.url
        embeds = (
            embed_from(json_attribute(holder, "data-cmp-protected-embed"), base)
            for holder in all_matches(element, CONSENT_EMBED)
        )
        return tuple(embed for embed in embeds if embed is not None)

    def _link_boxes(self, element: Tag) -> tuple[Block, ...]:
        base = self._extraction.page.url
        links = (
            (web_url(attribute(link, "href"), base), link)
            for link in all_matches(element, LINK_BOX)
        )
        return tuple(
            Embed(url, first_text(text_at(link, ".block-link__title"), text_of(link)))
            for url, link in links
            if url is not None
        )
