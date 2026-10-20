"""BeautifulSoup helpers for experts: lookups, visible text, sanitised inline HTML."""

from __future__ import annotations

import html
import json
import re
from collections.abc import Iterator
from typing import Any, Callable, Final
from urllib.parse import urljoin, urlparse

from bs4 import NavigableString, Tag
from bs4.element import PageElement, PreformattedString

from scrapelib.article import (
    AssetNamer,
    Block,
    Figure,
    Heading,
    ListBlock,
    Paragraph,
    Quote,
    Table,
    Url,
)

WHITESPACE: Final = re.compile(r"\s+")
SRCSET_WIDTH: Final = re.compile(r"^(\d+)[wx]$")
FORMATTING_TAGS: Final = frozenset(
    {"b", "code", "em", "i", "strong", "sub", "sup", "u"}
)
HIDDEN_TAGS: Final = frozenset(
    {"button", "form", "iframe", "noscript", "script", "style", "svg", "template"}
)
HIDDEN_CLASSES: Final = frozenset(
    {"h-offscreen", "screen-reader-text", "sr-only", "visually-hidden"}
)
HEADING_TAGS: Final = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
WEB_SCHEMES: Final = frozenset({"http", "https"})
TOP_HEADING_LEVEL: Final = 2
DEEPEST_HEADING_LEVEL: Final = 4

BlockReader = Callable[[Tag], "tuple[Block, ...]"]


def required(element: Tag | None, what: str) -> Tag:
    if element is None:
        raise ValueError(f"the page has no {what}")
    return element


def first_match(element: Tag, selector: str) -> Tag | None:
    return element if element.css.match(selector) else element.select_one(selector)


def all_matches(element: Tag, selector: str) -> list[Tag]:
    return [element] if element.css.match(selector) else list(element.select(selector))


def contains(element: Tag, selector: str) -> bool:
    return first_match(element, selector) is not None


def is_hidden(tag: Tag) -> bool:
    classes = tag.get("class") or []
    return tag.name in HIDDEN_TAGS or any(name in HIDDEN_CLASSES for name in classes)


def visible_strings(element: Tag) -> Iterator[str]:
    for node in element.children:
        if isinstance(node, PreformattedString):
            continue
        if isinstance(node, NavigableString):
            yield str(node)
        elif isinstance(node, Tag) and node.name == "br":
            yield " "
        elif isinstance(node, Tag) and not is_hidden(node):
            yield from visible_strings(node)


def collapse(text: str) -> str:
    return WHITESPACE.sub(" ", text).strip()


def text_of(element: Tag | None) -> str:
    return "" if element is None else collapse("".join(visible_strings(element)))


def text_at(root: Tag, selector: str) -> str:
    return text_of(root.select_one(selector))


def own_text_of(element: Tag | None) -> str:
    if element is None:
        return ""
    strings = element.find_all(string=True, recursive=False)
    return collapse("".join(str(text) for text in strings))


def attribute(element: Tag | None, name: str) -> str:
    value = None if element is None else element.get(name)
    return " ".join(value) if isinstance(value, list) else str(value or "")


def json_attribute(element: Tag, name: str) -> Any:
    try:
        return json.loads(attribute(element, name) or "null")
    except json.JSONDecodeError:
        return None


def web_url(href: object, base: Url) -> Url | None:
    if not isinstance(href, str) or not href.strip():
        return None
    absolute = urljoin(base, href.strip())
    return Url(absolute) if urlparse(absolute).scheme in WEB_SCHEMES else None


def absolutize_links(root: Tag, base: Url) -> None:
    for link in root.select("a[href]"):
        link["href"] = urljoin(base, attribute(link, "href"))


def inline_html(element: Tag) -> str:
    return inner_html(element).strip()


def inner_html(element: Tag) -> str:
    return "".join(render_inline(node) for node in element.children)


def render_inline(node: PageElement) -> str:
    if isinstance(node, PreformattedString):
        return ""
    if isinstance(node, NavigableString):
        return html.escape(WHITESPACE.sub(" ", str(node)), quote=False)
    if not isinstance(node, Tag) or is_hidden(node):
        return ""
    return render_inline_tag(node)


def render_inline_tag(tag: Tag) -> str:
    if tag.name == "br":
        return "<br>"
    inner = inner_html(tag)
    if tag.name == "a":
        return link_html(attribute(tag, "href"), inner)
    if tag.name in FORMATTING_TAGS:
        return f"<{tag.name}>{inner}</{tag.name}>"
    return inner


def link_html(href: str, inner: str) -> str:
    if urlparse(href).scheme not in WEB_SCHEMES:
        return inner
    return f'<a href="{html.escape(href)}">{inner}</a>'


def largest_srcset_candidate(srcset: str) -> str:
    best_url, best_size = "", -1
    for candidate in srcset.split(","):
        parts = candidate.split()
        if not parts:
            continue
        width = SRCSET_WIDTH.match(parts[-1]) if len(parts) > 1 else None
        size = int(width.group(1)) if width else 0
        if size > best_size:
            best_url, best_size = parts[0], size
    return best_url


def image_source(image: Tag) -> str:
    srcset = attribute(image, "srcset") or attribute(image, "data-srcset")
    if srcset:
        return largest_srcset_candidate(srcset)
    return attribute(image, "data-src") or attribute(image, "src")


class SemanticReader:
    def __init__(self, base: Url, namer: AssetNamer) -> None:
        self._base = base
        self._namer = namer
        self._readers: dict[str, BlockReader] = {
            **{name: self._heading for name in HEADING_TAGS},
            "p": self._paragraph,
            "ul": self._list,
            "ol": self._list,
            "blockquote": self._quote,
            "figure": self._figure,
            "img": self._image,
            "table": self._table,
        }

    def blocks(self, root: Tag | None) -> tuple[Block, ...]:
        if root is None:
            return ()
        children = root.find_all(True, recursive=False)
        return tuple(block for child in children for block in self._blocks_from(child))

    def _blocks_from(self, element: Tag) -> tuple[Block, ...]:
        if is_hidden(element):
            return ()
        reader = self._readers.get(element.name)
        return reader(element) if reader is not None else self.blocks(element)

    def _heading(self, element: Tag) -> tuple[Block, ...]:
        text = text_of(element)
        level = min(max(int(element.name[1]), TOP_HEADING_LEVEL), DEEPEST_HEADING_LEVEL)
        return (Heading(level, text),) if text else ()

    def _paragraph(self, element: Tag) -> tuple[Block, ...]:
        markup = inline_html(element)
        text = (Paragraph(markup),) if markup else ()
        images = tuple(
            block for img in element.find_all("img") for block in self._image(img)
        )
        return text + images

    def _list(self, element: Tag) -> tuple[Block, ...]:
        items = tuple(
            inline_html(item) for item in element.find_all("li", recursive=False)
        )
        return (ListBlock(items, element.name == "ol"),) if any(items) else ()

    def _quote(self, element: Tag) -> tuple[Block, ...]:
        markup = inline_html(element)
        return (Quote(markup),) if markup else ()

    def _figure(self, element: Tag) -> tuple[Block, ...]:
        image = element.find("img")
        if image is None:
            return self.blocks(element)
        return self._image(image, text_of(element.find("figcaption")))

    def _image(self, image: Tag, caption: str = "") -> tuple[Block, ...]:
        url = web_url(image_source(image), self._base)
        if url is None:
            return ()
        return (
            Figure(
                self._namer.image(url), caption=caption, alt=attribute(image, "alt")
            ),
        )

    def _table(self, element: Tag) -> tuple[Block, ...]:
        rows = tuple(
            tuple(text_of(cell) for cell in row.find_all(["th", "td"]))
            for row in element.find_all("tr")
        )
        first_row = element.find("tr")
        header = first_row is not None and first_row.find("td") is None
        return (Table(rows, header),) if rows else ()
