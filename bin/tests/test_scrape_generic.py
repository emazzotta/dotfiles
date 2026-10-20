from datetime import datetime, timezone

import pytest

from .scrape_support import LOREM, FakeFetcher

URL = "https://news.example.org/2026/10/artikel"
JSON_LD = (
    '<script type="application/ld+json">{"@context": "https://schema.org", "@graph": ['
    '{"@type": "WebSite", "name": "Site"},'
    '{"@type": ["NewsArticle"], "headline": "Titre JSON-LD", "description": "Chapeau",'
    ' "datePublished": "2026-10-20T10:00:00Z",'
    ' "author": [{"@type": "Person", "name": "Anne"}, {"name": "Paul"}],'
    ' "publisher": {"name": "Le Journal"}}]}</script>'
)
OPEN_GRAPH = (
    '<meta property="og:title" content="Titre OG">'
    '<meta property="og:description" content="Résumé OG">'
    '<meta property="og:site_name" content="Journal OG">'
    '<meta property="article:published_time" content="2026-10-19">'
    '<meta name="author" content="Rédaction">'
)


@pytest.fixture
def generic(load_module):
    return load_module("scrapelib.experts.generic")


@pytest.fixture
def page_of(load_module):
    base = load_module("scrapelib.experts.base")
    bs4 = load_module("bs4")
    return lambda html: base.Page(URL, html, bs4.BeautifulSoup(html, "html5lib"))


def document(head="", body=""):
    return f'<!doctype html><html lang="fr-CH"><head>{head}</head><body>{body}</body></html>'


def should_prefer_json_ld_over_open_graph(generic, page_of):
    header = generic.header_from(
        page_of(document(JSON_LD + OPEN_GRAPH + "<title>Page</title>")).soup
    )

    assert (header.title, header.lead, header.author) == (
        "Titre JSON-LD",
        "Chapeau",
        "Anne, Paul",
    )
    assert header.published == datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)
    assert (header.site, header.language) == ("Journal OG", "fr-CH")


def should_fall_back_to_open_graph_and_then_the_page_title(generic, page_of):
    with_open_graph = generic.header_from(
        page_of(document(OPEN_GRAPH + "<title>Page</title>")).soup
    )
    bare = generic.header_from(page_of(document("<title>Page</title>")).soup)

    assert (with_open_graph.title, with_open_graph.lead, with_open_graph.author) == (
        "Titre OG",
        "Résumé OG",
        "Rédaction",
    )
    assert with_open_graph.published == datetime(2026, 10, 19)
    assert (bare.title, bare.lead, bare.author, bare.published) == (
        "Page",
        "",
        "",
        None,
    )


def should_find_plain_media_files_and_hls_streams(load_module, generic, page_of):
    namer = load_module("scrapelib.article").AssetNamer()
    html = document(
        '<meta property="og:video" content="https://cdn.example.org/live/master.m3u8">'
        '<meta property="og:video:url" content="https://player.example.org/embed/1">',
        '<video poster="/p.jpg"><source src="/media/clip.mp4" type="video/mp4"></video>'
        '<audio src="/media/sound.mp3"></audio>',
    )

    clips = generic.media_clips(page_of(html), namer, "Titre")

    assert [
        (clip.kind.name, clip.media.url, clip.media.transfer.name) for clip in clips
    ] == [
        ("VIDEO", "https://news.example.org/media/clip.mp4", "FILE"),
        ("AUDIO", "https://news.example.org/media/sound.mp3", "FILE"),
        ("VIDEO", "https://cdn.example.org/live/master.m3u8", "HLS"),
    ]
    assert clips[0].poster.url == "https://news.example.org/p.jpg"


def should_add_the_open_graph_image_only_when_the_body_has_none(generic, page_of):
    html = document(
        '<meta property="og:image" content="https://news.example.org/hero.jpg"><title>T</title>'
    )
    text_only = generic.GenericExpert(lambda page_html, url: f"<p>{LOREM}</p>")
    illustrated = generic.GenericExpert(
        lambda page_html, url: '<p><img src="/inline.jpg"></p>'
    )

    plain_blocks = text_only.extract(page_of(html), FakeFetcher()).blocks
    illustrated_blocks = illustrated.extract(page_of(html), FakeFetcher()).blocks

    assert [type(block).__name__ for block in plain_blocks] == ["Figure", "Paragraph"]
    assert plain_blocks[0].image.url == "https://news.example.org/hero.jpg"
    assert [block.image.url for block in illustrated_blocks] == [
        "https://news.example.org/inline.jpg"
    ]


def should_warn_when_the_page_has_no_article_text(generic, page_of):
    expert = generic.GenericExpert(lambda page_html, url: None)

    article = expert.extract(page_of(document("<title>T</title>")), FakeFetcher())

    assert article.warnings == ("found no article text on the page",)


def should_extract_the_main_text_with_trafilatura(generic, page_of):
    pytest.importorskip("trafilatura")
    paragraphs = "".join(f"<p>{LOREM} Absatz {number}.</p>" for number in range(8))
    html = document(
        "<title>T</title>",
        '<nav><a href="/">Start</a> <a href="/archiv">Archiv</a></nav>'
        f"<article><h1>T</h1>{paragraphs}</article><footer>Impressum und Kontakt</footer>",
    )

    article = generic.GenericExpert().extract(page_of(html), FakeFetcher())

    texts = [
        block.html for block in article.blocks if type(block).__name__ == "Paragraph"
    ]
    assert texts == [f"{LOREM} Absatz {number}." for number in range(8)]
