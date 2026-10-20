from datetime import datetime, timedelta, timezone

import pytest

from .scrape_support import (
    CLIP_MP3,
    HLS,
    LOREM,
    MP3,
    PAGE_URL,
    POSTER,
    FakeFetcher,
    attribute_json,
    composition,
    resource,
    srf_asset,
    srf_page,
    srf_player,
)

VIDEO_URN = "urn:srf:video:d02702ea-bf3b-45eb-889a-3e9229f46b6c"
AUDIO_URN = "urn:srf:audio:7a1af3be-b996-3602-b224-27d0f9a2edb0"
ROKKA = "https://www.srf.ch/static/cms/images/1280w/{}.jpg"
TICKER_ENDPOINT = "/aron/api/liveticker/urn:srf:article:01a1524e"
FIGURE = (
    '<div class="article-element article-element--bleed"><figure class="image-figure">'
    '<div class="image js-image" data-image-provider="rokka" data-image-id="bdf5f6"><picture>'
    '<img alt="Alternativtext" src="data:image/gif;base64,R0lGODlhAQABAAAAACw="></picture></div>'
    '<figcaption class="media-caption"><span class="h-offscreen">Legende:</span>'
    '<span class="media-caption__description">Bildlegende</span>'
    '<span class="media-caption__source">Keystone</span></figcaption></figure></div>'
)


@pytest.fixture
def media(load_module):
    return load_module("scrapelib.experts.srf.media")


@pytest.fixture
def clip_kind(load_module):
    return load_module("scrapelib.article").ClipKind


@pytest.fixture
def page_of(load_module):
    base = load_module("scrapelib.experts.base")
    bs4 = load_module("bs4")
    return lambda html, url=PAGE_URL: base.Page(
        url, html, bs4.BeautifulSoup(html, "html5lib")
    )


@pytest.fixture
def read_srf(load_module, page_of):
    srf = load_module("scrapelib.experts.srf")
    return lambda html, fetcher=None: srf.SrfExpert().extract(
        page_of(html), fetcher or FakeFetcher()
    )


def names(blocks):
    return [type(block).__name__ for block in blocks]


def wrapped(html, modifier=""):
    classes = f"article-element {modifier}".strip()
    return f'<div class="{classes}">{html}</div>'


def gallery_item(image_id, caption):
    return (
        '<li class="image-gallery__item"><div class="image-gallery__figure">'
        f'<span class="h-offscreen">Bild 1 von 2. {caption}</span>'
        f'<div class="image" data-image-provider="rokka" data-image-id="{image_id}"><img alt="Alt"></div>'
        f'<div class="media-caption"><span class="media-caption__description">{caption}'
        '<span class="media-caption__source">SRF</span></span></div></div></li>'
    )


def should_read_the_header(read_srf):
    header = read_srf(srf_page("")).header

    assert (header.title, header.overline, header.lead) == (
        "Beispieltitel: Teil 1",
        "Überzeile",
        LOREM,
    )
    assert header.author == "Erika Muster"
    assert header.published == datetime(
        2026, 10, 19, 7, 22, 30, tzinfo=timezone(timedelta(hours=2))
    )
    assert (header.language, header.site) == ("de", "SRF")


def should_claim_only_srf_article_pages(load_module, page_of):
    expert = load_module("scrapelib.experts.srf").SrfExpert()

    assert expert.matches(page_of(srf_page("")))
    assert not expert.matches(page_of(srf_page(""), "https://www.example.org/news/x"))
    assert not expert.matches(page_of("<html><body><p>Wetter</p></body></html>"))


def should_read_text_components_in_order_and_drop_empty_paragraphs(read_srf):
    body = (
        '<p class="article-paragraph">Eins <a href="/news/zwei">zwei</a></p>'
        '<p class="article-paragraph"> </p>'
        '<h2 class="article-heading">Kapitel</h2><h3 class="article-subheading">Abschnitt</h3>'
        '<ul class="article-list"><li>a</li></ul><ol class="article-list"><li>b</li></ol>'
    )

    blocks = read_srf(srf_page(body)).blocks

    assert names(blocks) == [
        "Paragraph",
        "Heading",
        "Heading",
        "ListBlock",
        "ListBlock",
    ]
    assert blocks[0].html == 'Eins <a href="https://www.srf.ch/news/zwei">zwei</a>'
    assert (blocks[1].level, blocks[2].level) == (2, 3)
    assert (blocks[3].ordered, blocks[4].ordered) == (False, True)


def should_read_a_figure_at_the_largest_rokka_size(read_srf):
    (figure,) = read_srf(srf_page(FIGURE)).blocks

    assert figure.image.url == ROKKA.format("bdf5f6")
    assert (figure.caption, figure.credit, figure.alt) == (
        "Bildlegende",
        "Keystone",
        "Alternativtext",
    )


def should_read_gallery_items_without_repeating_the_credit_in_the_caption(read_srf):
    items = gallery_item("e86395", "Erstes") + gallery_item("131ceb", "Zweites")
    body = wrapped(
        f'<div class="image-gallery"><ul>{items}</ul></div>', "article-element--bleed"
    )

    (gallery,) = read_srf(srf_page(body)).blocks

    assert [figure.image.url for figure in gallery.figures] == [
        ROKKA.format("e86395"),
        ROKKA.format("131ceb"),
    ]
    assert [(figure.caption, figure.credit) for figure in gallery.figures] == [
        ("Erstes", "SRF"),
        ("Zweites", "SRF"),
    ]


def should_read_a_photo_slider_as_a_gallery(read_srf):
    images = [
        {"provider": "rokka", "imageId": "b0dde1", "alt": "Vorher"},
        {"provider": "rokka", "imageId": "b0dde2", "alt": "Nachher"},
    ]
    slider = (
        f'<div class="js-photo-slider" data-images="{attribute_json(images)}" data-title="Vergleich" '
        'data-legend="Links 2015, rechts 2026." data-source="Keystone/SRF"></div>'
    )

    (gallery,) = read_srf(srf_page(wrapped(slider))).blocks

    assert (gallery.title, gallery.caption) == ("Vergleich", "Links 2015, rechts 2026.")
    assert [(figure.alt, figure.credit) for figure in gallery.figures] == [
        ("Vorher", "Keystone/SRF"),
        ("Nachher", "Keystone/SRF"),
    ]


def should_read_a_quote_with_its_author_and_function(read_srf):
    quote_html = (
        '<blockquote class="blockquote"><div class="blockquote__quote">'
        '<span class="blockquote__text">Ein Zitat.</span></div><footer class="blockquote__footer"><cite>'
        '<span class="blockquote__author"><span class="h-offscreen">Zitat von</span>Erika Muster</span>'
        '<span class="blockquote__function">Ökonomin</span></cite></footer></blockquote>'
    )

    (quote,) = read_srf(
        srf_page(wrapped(quote_html, "article-element--inset-quote"))
    ).blocks

    assert (quote.html, quote.source) == ("Ein Zitat.", "Erika Muster, Ökonomin")


def should_read_text_boxes_and_person_boxes(read_srf):
    text_box = wrapped(
        '<div class="expandable-box"><div class="expandable-box__header">'
        '<h2 class="content-heading content-heading--box-title">Hintergrund</h2>'
        '<button><span class="h-offscreen">Box aufklappen</span></button></div>'
        '<div class="expandable-box__body"><div class="expandable-box__content">'
        f'<p class="article-paragraph">{LOREM}</p>{FIGURE}</div></div></div>',
        "article-element--inset-box",
    )
    person_box = wrapped(
        '<div class="expandable-box" itemtype="http://schema.org/Person"><div class="expandable-box__header">'
        '<div class="circle-image"><div class="image" data-image-provider="rokka" data-image-id="8a004d4"></div></div>'
        '<div class="person-details"><p class="person-details__name"><span itemprop="name">Max Muster</span></p>'
        '<p class="person-details__function" itemprop="jobTitle">Politologe</p></div></div>'
        f'<div class="expandable-box__body"><div class="expandable-box__content"><p class="article-paragraph">{LOREM}</p></div>'
        '<a href="https://www.srf.ch/unternehmen/max-muster" class="block-link block-link--box">'
        '<span class="block-link__title">Mehr von Max Muster</span></a></div></div>',
        "article-element--inset-box",
    )

    text, person = read_srf(srf_page(text_box + person_box)).blocks

    assert (text.title, names(text.blocks)) == ("Hintergrund", ["Paragraph", "Figure"])
    assert (person.title, names(person.blocks)) == (
        "Max Muster",
        ["Figure", "Paragraph", "Paragraph", "Embed"],
    )
    assert person.blocks[0].image.url == ROKKA.format("8a004d4")
    assert person.blocks[1].html == "Politologe"
    assert (person.blocks[3].url, person.blocks[3].title) == (
        "https://www.srf.ch/unternehmen/max-muster",
        "Mehr von Max Muster",
    )


def should_turn_a_datawrapper_chart_into_a_linked_image(read_srf):
    chart = (
        '<div class="embed embed--html"><div class="embed__content"><div id="datawrapper-vis-wVzdI">'
        '<script src="https://datawrapper.dwcdn.net/wVzdI/embed.js"></script>'
        '<noscript><img src="https://datawrapper.dwcdn.net/wVzdI/full.png"></noscript></div></div></div>'
    )

    (figure,) = read_srf(srf_page(wrapped(chart))).blocks

    assert (figure.image.url, figure.link) == (
        "https://datawrapper.dwcdn.net/wVzdI/full.png",
        "https://datawrapper.dwcdn.net/wVzdI/",
    )


def should_turn_consent_gated_embeds_into_links(read_srf):
    youtube = {
        "type": "html",
        "title": "",
        "html": '<iframe src="https://www.youtube.com/embed/abc123"></iframe>',
    }
    instagram = {"type": "instagram", "url": "https://www.instagram.com/p/xyz/"}
    body = "".join(
        wrapped(
            f'<div class="embed js-cmp-embed" data-cmp-protected-embed="{attribute_json(data)}"></div>'
        )
        for data in (youtube, instagram)
    )

    embeds = read_srf(srf_page(body)).blocks

    assert [(embed.url, embed.title) for embed in embeds] == [
        ("https://www.youtube.com/embed/abc123", "www.youtube.com"),
        ("https://www.instagram.com/p/xyz/", "www.instagram.com"),
    ]


def should_read_every_live_ticker_entry_from_the_api(media, read_srf):
    paragraph = {
        "type": "paragraph",
        "children": [
            {"text": "Mit "},
            {"text": "Betonung", "italic": True},
            {"text": " und "},
            {
                "type": "link",
                "link": "https://www.srf.ch/news/a",
                "children": [{"text": "Link"}],
            },
        ],
    }
    first = [
        paragraph,
        {
            "type": "bulletList",
            "children": [{"type": "listItem", "children": [{"text": "Punkt"}]}],
        },
        {
            "type": "image",
            "provider": "rokka",
            "imageId": "644846",
            "legend": "Legende",
            "source": "Reuters",
        },
        {
            "type": "twitter",
            "url": "https://x.com/user/status/1",
            "children": [{"text": ""}],
        },
        {
            "type": "article",
            "title": "Weiterlesen",
            "representationLinks": {"web": "/news/international/b"},
        },
        {"type": "poll"},
    ]
    entries = {
        "items": [
            {
                "title": "Neuster Eintrag",
                "publishedAt": "2026-10-20T20:05:56+02:00",
                "text": first,
            },
            {"title": "Gelöscht", "delete": True, "text": []},
            {
                "title": "Mit Video",
                "publishedAt": "2026-10-20T19:00:00+02:00",
                "text": [srf_asset(VIDEO_URN)],
            },
        ]
    }
    fetcher = FakeFetcher(
        json_responses={
            "https://www.srf.ch" + TICKER_ENDPOINT: entries,
            media.MEDIA_COMPOSITION_URL.format(urn=VIDEO_URN): composition(
                VIDEO_URN, [HLS]
            ),
        }
    )
    ticker = (
        f'<div id="ticker" data-api-endpoint="{TICKER_ENDPOINT}" itemtype="https://schema.org/LiveBlogPosting">'
        "<h2>Ticker</h2><ul><li>Nur zehn Titel</li></ul></div>"
    )

    article = read_srf(srf_page(wrapped(ticker)), fetcher)

    heading, newest, with_video = article.blocks
    assert heading.text == "Ticker"
    assert (newest.title, with_video.title) == ("Neuster Eintrag", "Mit Video")
    assert names(newest.blocks) == [
        "Paragraph",
        "ListBlock",
        "Figure",
        "Embed",
        "Embed",
    ]
    assert (
        newest.blocks[0].html
        == 'Mit <em>Betonung</em> und <a href="https://www.srf.ch/news/a">Link</a>'
    )
    assert newest.blocks[4].url == "https://www.srf.ch/news/international/b"
    assert names(with_video.blocks) == ["Clip"]
    assert article.warnings == ("skipped a live-ticker part of type 'poll'",)


def should_read_every_clip_of_a_video_gallery(media, read_srf):
    urns = [VIDEO_URN, "urn:srf:video:24b114e1-075f-4d87-8dda-38048ac39037"]
    mp4 = {
        urn: resource(
            f"https://download.example.org/{n}.mp4",
            "HTTP",
            "HD",
            "video/mp4",
            "PROGRESSIVE",
        )
        for n, urn in enumerate(urns)
    }
    fetcher = FakeFetcher(
        json_responses={
            media.MEDIA_COMPOSITION_URL.format(urn=urn): composition(urn, [mp4[urn]])
            for urn in urns
        }
    )
    assets = [srf_asset(urn, title=f"Clip {n}") for n, urn in enumerate(urns, 1)]
    body = wrapped(
        f'<div class="js-video-gallery" data-assets="{attribute_json(assets)}"></div>'
    )

    clips = read_srf(srf_page(body), fetcher).blocks

    assert [clip.title for clip in clips] == ["Clip 1", "Clip 2"]
    assert [clip.media.local_path.as_posix() for clip in clips] == [
        "video/01 Clip 1.mp4",
        "video/02 Clip 2.mp4",
    ]


def should_ignore_known_page_furniture_and_warn_about_unknown_components(read_srf):
    body = (
        wrapped('<div class="js-mehr-zum-thema"></div>')
        + '<div class="podcast-box"></div><crk-psi-widget></crk-psi-widget>'
        + wrapped(
            '<div class="embed embed--html"><a href="#"></a>'
            '<script src="https://www.srf.ch/widgets/wahlen/index.js"></script></div>'
        )
        + wrapped('<div class="raetsel-widget"></div>')
    )

    article = read_srf(srf_page(body))

    assert article.blocks == ()
    assert article.warnings == (
        "skipped an unknown component <div class='article-element'>",
    )


def should_turn_the_top_media_player_into_the_first_clip(media, read_srf):
    player = srf_player(srf_asset(AUDIO_URN, "audio", "Echo"))
    top = f'<section class="articlepage__topmedia"><div class="articlepage__topmedia-content">{player}</div></section>'
    full_show = composition(AUDIO_URN, [MP3], fullLengthUrn="urn:srf:audio:full")
    fetcher = FakeFetcher(
        json_responses={media.MEDIA_COMPOSITION_URL.format(urn=AUDIO_URN): full_show}
    )

    (clip,) = read_srf(srf_page("", top_media=top), fetcher).blocks

    assert (clip.kind.name, clip.title, clip.media.url) == ("AUDIO", "Echo", CLIP_MP3)
    assert clip.media.local_path.as_posix() == "audio/01 Echo.mp3"
    assert clip.poster.url == POSTER
    assert clip.duration == timedelta(milliseconds=32160)
