from datetime import datetime, timedelta
from pathlib import Path

import pytest


@pytest.fixture
def article(load_module):
    return load_module("scrapelib.article")


@pytest.fixture
def render(load_module):
    return load_module("scrapelib.render")


@pytest.fixture
def make_article(article):
    def _make(blocks, language="de"):
        header = article.Header(
            title="Titel <b>",
            overline="Über",
            lead="Lead & mehr",
            author="Erika Muster",
            published=datetime(2026, 10, 19, 7, 22),
            language=language,
            site="SRF",
        )
        return article.Article(
            header, "https://www.srf.ch/news/x?a=1&b=2", tuple(blocks)
        )

    return _make


def should_escape_header_text_and_the_source_url(render, make_article):
    page = render.render_page(make_article([]))

    assert "<title>Titel &lt;b&gt;</title>" in page
    assert '<p class="lead">Lead &amp; mehr</p>' in page
    assert 'href="https://www.srf.ch/news/x?a=1&amp;b=2"' in page


def should_reference_assets_by_percent_encoded_relative_path(
    article, render, make_article
):
    namer = article.AssetNamer()
    audio = namer.clip(
        article.ClipKind.AUDIO,
        "https://x.example/a.mp3",
        "Ä Titel",
        article.Transfer.FILE,
    )

    page = render.render_page(
        make_article([article.Clip(article.ClipKind.AUDIO, "Ä Titel", audio)])
    )

    assert 'src="audio/01%20%C3%84%20Titel.mp3"' in page


def should_render_video_with_poster_and_audio_with_cover(article, render, make_article):
    poster = article.Asset("https://x.example/p.jpg", Path("images/01.jpg"))
    video = article.Asset(
        "https://x.example/v.m3u8", Path("video/01 V.mp4"), article.Transfer.HLS
    )
    sound = article.Asset("https://x.example/a.mp3", Path("audio/01 A.mp3"))
    clips = [
        article.Clip(
            article.ClipKind.VIDEO,
            "V",
            video,
            duration=timedelta(seconds=152.5),
            poster=poster,
        ),
        article.Clip(article.ClipKind.AUDIO, "A", sound, poster=poster),
    ]

    page = render.render_page(make_article(clips))

    assert (
        '<video controls preload="metadata" poster="images/01.jpg" src="video/01%20V.mp4">'
        in page
    )
    assert (
        '<img src="images/01.jpg" alt=""><audio controls preload="metadata" src="audio/01%20A.mp3">'
        in page
    )
    assert "V · 2:32" in page


def should_use_the_labels_and_date_format_of_the_article_language(
    article, render, make_article
):
    figure = article.Figure(
        article.Asset("https://x.example/1.jpg", Path("images/01.jpg")), "C", "K"
    )

    german = render.render_page(make_article([figure], "de"))
    english = render.render_page(make_article([figure], "en-GB"))

    assert '<html lang="de">' in german
    assert '<span class="credit">Bild: K</span>' in german
    assert "19.10.2026, 07:22" in german
    assert '<span class="credit">Image: K</span>' in english
    assert "2026-10-19 07:22" in english


def should_link_a_figure_to_its_live_source_when_it_has_one(
    article, render, make_article
):
    chart = article.Figure(
        article.Asset("https://charts.example/1/full.png", Path("images/01.png")),
        link="https://charts.example/1/",
    )

    page = render.render_page(make_article([chart]))

    assert '<a href="https://charts.example/1/"><img src="images/01.png"' in page
