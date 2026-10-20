"""Offline article.html: a renderer per block type, inline CSS, local paths only."""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import singledispatch
from string import Template
from typing import Final
from urllib.parse import quote

from scrapelib.article import (
    Article,
    Asset,
    Box,
    Clip,
    ClipKind,
    Embed,
    Figure,
    Gallery,
    Header,
    Heading,
    ListBlock,
    Paragraph,
    Quote,
    Table,
)

SECONDS_PER_MINUTE: Final = 60
SEPARATOR: Final = " · "


@dataclass(frozen=True)
class Labels:
    source: str
    gallery: str
    credit: str
    external: str
    date_format: str


GERMAN: Final = Labels(
    "Quelle", "Bildergalerie", "Bild", "Externer Inhalt", "%d.%m.%Y, %H:%M"
)
ENGLISH: Final = Labels(
    "Source", "Gallery", "Image", "External content", "%Y-%m-%d %H:%M"
)
LABELS: Final = {"de": GERMAN, "en": ENGLISH}


def labels_for(language: str) -> Labels:
    return LABELS.get(language.split("-", maxsplit=1)[0].lower(), ENGLISH)


def escape(text: str) -> str:
    return html.escape(text)


def asset_href(asset: Asset) -> str:
    return html.escape(quote(asset.local_path.as_posix()))


def joined(*parts: str) -> str:
    return SEPARATOR.join(part for part in parts if part)


def format_date(moment: datetime | None, labels: Labels) -> str:
    return "" if moment is None else moment.strftime(labels.date_format)


def format_duration(duration: timedelta | None) -> str:
    if duration is None:
        return ""
    minutes, seconds = divmod(round(duration.total_seconds()), SECONDS_PER_MINUTE)
    return f"{minutes}:{seconds:02d}"


@singledispatch
def render_block(block: object, labels: Labels) -> str:
    raise TypeError(f"no renderer for {type(block).__name__}")


@render_block.register
def render_paragraph(block: Paragraph, labels: Labels) -> str:
    return f"<p>{block.html}</p>"


@render_block.register
def render_heading(block: Heading, labels: Labels) -> str:
    return f"<h{block.level}>{escape(block.text)}</h{block.level}>"


@render_block.register
def render_list(block: ListBlock, labels: Labels) -> str:
    tag = "ol" if block.ordered else "ul"
    items = "".join(f"<li>{item}</li>" for item in block.items)
    return f"<{tag}>{items}</{tag}>"


@render_block.register
def render_quote(block: Quote, labels: Labels) -> str:
    source = f"<footer>{escape(block.source)}</footer>" if block.source else ""
    return f"<blockquote><p>{block.html}</p>{source}</blockquote>"


@render_block.register
def render_figure(block: Figure, labels: Labels) -> str:
    src = asset_href(block.image)
    target = escape(block.link) if block.link else src
    image = f'<img src="{src}" alt="{escape(block.alt)}" loading="lazy">'
    caption = figure_caption(block, labels)
    return f'<figure><a href="{target}">{image}</a>{caption}</figure>'


def figure_caption(block: Figure, labels: Labels) -> str:
    credit = (
        f'<span class="credit">{escape(labels.credit)}: {escape(block.credit)}</span>'
    )
    parts = [escape(block.caption)] if block.caption else []
    parts += [credit] if block.credit else []
    return f"<figcaption>{' '.join(parts)}</figcaption>" if parts else ""


@render_block.register
def render_gallery(block: Gallery, labels: Labels) -> str:
    title = f"<h3>{escape(block.title)}</h3>" if block.title else ""
    caption = f'<p class="caption">{escape(block.caption)}</p>' if block.caption else ""
    figures = "\n".join(render_figure(figure, labels) for figure in block.figures)
    label = escape(block.title or labels.gallery)
    opening = f'<section class="gallery" aria-label="{label}">'
    return f"{opening}{title}\n{figures}\n{caption}</section>"


@render_block.register
def render_clip(block: Clip, labels: Labels) -> str:
    details = joined(
        block.title,
        format_date(block.published, labels),
        format_duration(block.duration),
    )
    caption = f"<figcaption>{escape(details)}</figcaption>"
    return f'<figure class="clip">{clip_player(block)}{caption}</figure>'


def clip_player(block: Clip) -> str:
    media = asset_href(block.media)
    if block.kind is ClipKind.VIDEO:
        poster = f' poster="{asset_href(block.poster)}"' if block.poster else ""
        return f'<video controls preload="metadata"{poster} src="{media}"></video>'
    cover = f'<img src="{asset_href(block.poster)}" alt="">' if block.poster else ""
    return f'{cover}<audio controls preload="metadata" src="{media}"></audio>'


@render_block.register
def render_embed(block: Embed, labels: Labels) -> str:
    title = escape(block.title or block.url)
    link = f'<a href="{escape(block.url)}">{title}</a>'
    return f'<p class="embed">{escape(labels.external)}: {link}</p>'


@render_block.register
def render_table(block: Table, labels: Labels) -> str:
    rows = [
        table_row(row, block.header and index == 0)
        for index, row in enumerate(block.rows)
    ]
    return f"<table>{''.join(rows)}</table>"


def table_row(cells: tuple[str, ...], header: bool) -> str:
    tag = "th" if header else "td"
    return (
        "<tr>" + "".join(f"<{tag}>{escape(cell)}</{tag}>" for cell in cells) + "</tr>"
    )


@render_block.register
def render_box(block: Box, labels: Labels) -> str:
    published = format_date(block.published, labels)
    time = f'<p class="byline">{escape(published)}</p>' if published else ""
    inner = "\n".join(render_block(child, labels) for child in block.blocks)
    return (
        f'<aside class="box">\n<h2>{escape(block.title)}</h2>{time}\n{inner}\n</aside>'
    )


def render_header(header: Header, labels: Labels) -> str:
    overline = (
        f'<p class="overline">{escape(header.overline)}</p>' if header.overline else ""
    )
    lead = f'<p class="lead">{escape(header.lead)}</p>' if header.lead else ""
    byline = joined(header.author, format_date(header.published, labels), header.site)
    title = f"<h1>{escape(header.title)}</h1>"
    return f'{overline}{title}{lead}<p class="byline">{escape(byline)}</p>'


STYLE: Final = """
:root { color-scheme: light dark; --text: #1d1d1f; --muted: #5c5c60;
  --bg: #ffffff; --panel: #f3f3f4; --accent: #af001d; }
@media (prefers-color-scheme: dark) {
  :root { --text: #ececee; --muted: #a1a1a6; --bg: #141416; --panel: #222226;
    --accent: #ff5a6e; }
}
body { margin: 0; background: var(--bg); color: var(--text);
  font: 18px/1.6 -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial,
  sans-serif; }
main { max-width: 46rem; margin: 0 auto; padding: 2rem 1rem 4rem; }
.overline { margin: 0; color: var(--accent); font-weight: 600; }
h1 { margin: .25rem 0 1rem; font-size: 2rem; line-height: 1.2; }
.lead { font-size: 1.15rem; font-weight: 600; }
.byline, figcaption, footer, .caption, .embed { color: var(--muted); font-size: .9rem; }
figure { margin: 2rem 0; }
img, video { display: block; width: 100%; height: auto; border-radius: 6px; }
audio { width: 100%; margin-top: .75rem; }
.gallery { display: grid; gap: 1.5rem;
  grid-template-columns: repeat(auto-fill, minmax(17rem, 1fr)); }
.gallery figure { margin: 0; }
.box { margin: 2rem 0; padding: .25rem 1.25rem; background: var(--panel);
  border-left: 4px solid var(--accent); }
blockquote { margin: 2rem 0; padding-left: 1.25rem;
  border-left: 4px solid var(--accent);
  font-size: 1.1rem; }
table { border-collapse: collapse; width: 100%; font-size: .95rem; }
th, td { border-bottom: 1px solid var(--panel); padding: .4rem .5rem;
  text-align: left; }
a { color: inherit; }
footer.source { margin-top: 3rem; overflow-wrap: anywhere; }
"""

PAGE: Final = Template(
    """<!doctype html>
<html lang="$language">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<style>$style</style>
</head>
<body>
<main>
<header>$header</header>
$content
<footer class="source">$source_label: <a href="$source_url">$source_url</a></footer>
</main>
</body>
</html>
"""
)


def render_page(article: Article) -> str:
    labels = labels_for(article.header.language)
    return PAGE.substitute(
        language=escape(article.header.language),
        title=escape(article.header.title),
        style=STYLE,
        header=render_header(article.header, labels),
        content="\n".join(render_block(block, labels) for block in article.blocks),
        source_label=escape(labels.source),
        source_url=escape(article.source_url),
    )
