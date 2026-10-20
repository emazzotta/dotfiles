"""SRF live tickers: each API entry becomes a box, its rich text becomes blocks."""

from __future__ import annotations

import html
from collections.abc import Mapping
from typing import Any, Callable, Final
from urllib.parse import urljoin

from scrapelib.article import Block, Box, Embed, Figure, ListBlock, Paragraph, Url
from scrapelib.experts.base import Extraction
from scrapelib.experts.srf.media import SrfMedia
from scrapelib.markup import link_html, web_url
from scrapelib.values import first_text, parse_datetime

LEAF_MARKS: Final = (("bold", "strong"), ("italic", "em"), ("underline", "u"))
ORDERED_LIST: Final = "orderedList"

NodeReader = Callable[[Mapping[str, Any]], "tuple[Block, ...]"]


def children_of(node: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [child for child in node.get("children") or [] if isinstance(child, Mapping)]


def leaf_html(leaf: Mapping[str, Any]) -> str:
    markup = html.escape(str(leaf.get("text", "")), quote=False)
    for mark, tag in LEAF_MARKS:
        if leaf.get(mark):
            markup = f"<{tag}>{markup}</{tag}>"
    return markup


def inline_nodes(nodes: list[Mapping[str, Any]]) -> str:
    return "".join(inline_node(node) for node in nodes)


def inline_node(node: Mapping[str, Any]) -> str:
    if "type" not in node:
        return leaf_html(node)
    inner = inline_nodes(children_of(node))
    return (
        link_html(str(node.get("link") or ""), inner)
        if node.get("type") == "link"
        else inner
    )


def node_html(node: Mapping[str, Any]) -> str:
    return inline_nodes(children_of(node)).strip()


class SrfTicker:
    def __init__(self, extraction: Extraction, media: SrfMedia) -> None:
        self._extraction = extraction
        self._media = media
        self._readers: dict[str, NodeReader] = {
            "paragraph": self._paragraph,
            "bulletList": self._list,
            ORDERED_LIST: self._list,
            "image": self._image,
            "video": self._clip,
            "audio": self._clip,
            "twitter": self._embed,
            "link": self._embed,
            "article": self._embed,
        }

    def entries(self, endpoint: Url) -> tuple[Block, ...]:
        payload = self._extraction.fetcher.fetch_json(endpoint)
        items = payload.get("items", []) if isinstance(payload, Mapping) else []
        live = (
            item
            for item in items
            if isinstance(item, Mapping) and not item.get("delete")
        )
        return tuple(self._entry(item) for item in live)

    def _entry(self, item: Mapping[str, Any]) -> Box:
        nodes = [node for node in item.get("text") or [] if isinstance(node, Mapping)]
        blocks = tuple(block for node in nodes for block in self._blocks_from(node))
        return Box(
            first_text(item.get("title")),
            blocks,
            parse_datetime(item.get("publishedAt")),
        )

    def _blocks_from(self, node: Mapping[str, Any]) -> tuple[Block, ...]:
        reader = self._readers.get(str(node.get("type")))
        if reader is None:
            self._extraction.warn(
                f"skipped a live-ticker part of type {node.get('type')!r}"
            )
            return ()
        return reader(node)

    def _paragraph(self, node: Mapping[str, Any]) -> tuple[Block, ...]:
        markup = node_html(node)
        return (Paragraph(markup),) if markup else ()

    def _list(self, node: Mapping[str, Any]) -> tuple[Block, ...]:
        items = tuple(node_html(item) for item in children_of(node))
        return (
            (ListBlock(items, node.get("type") == ORDERED_LIST),) if any(items) else ()
        )

    def _image(self, node: Mapping[str, Any]) -> tuple[Block, ...]:
        asset = self._media.image(
            str(node.get("provider") or ""), str(node.get("imageId") or "")
        )
        if asset is None:
            return ()
        caption, credit = first_text(node.get("legend")), first_text(node.get("source"))
        return (Figure(asset, caption, credit, first_text(node.get("alt"))),)

    def _clip(self, node: Mapping[str, Any]) -> tuple[Block, ...]:
        clip = self._media.clip(node)
        return () if clip is None else (clip,)

    def _embed(self, node: Mapping[str, Any]) -> tuple[Block, ...]:
        base = self._extraction.page.url
        url = web_url(node.get("url") or node.get("link") or self._web_link(node), base)
        title = first_text(node.get("title"), node.get("contentTitle"), node_html(node))
        return () if url is None else (Embed(url, title),)

    def _web_link(self, node: Mapping[str, Any]) -> str:
        links = node.get("representationLinks")
        web = links.get("web") if isinstance(links, Mapping) else None
        return urljoin(self._extraction.page.url, web) if isinstance(web, str) else ""
