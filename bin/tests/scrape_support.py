"""Fakes and synthetic pages for the scrape tests. Placeholder text only: the repo is public."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

LOREM = "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod."
PAGE_URL = "https://www.srf.ch/news/schweiz/beispiel-artikel"
POSTER = "https://download-media.srf.ch/world/image/video/2026/09/poster.jpg"
POSTER_ID = f"https://il.srf.ch/images/?imageUrl={POSTER}&format=webp&width=720"
CLIP_HLS = "https://vod.example.org/clip/master.m3u8?start=99.04&end=131.2&hdnts=signed"
CLIP_MP4_HD = "https://download.example.org/clip_hd.mp4"
CLIP_MP4_SD = "https://download.example.org/clip_sd.mp4"
CLIP_MP3 = "https://download-media.srf.ch/world/audio/2026/10/clip.mp3"


class FakeFetcher:
    """Answers from dictionaries and records every URL it was asked for."""

    def __init__(self, pages=None, json_responses=None, files=None, texts=None) -> None:
        self.pages = dict(pages or {})
        self.json_responses = dict(json_responses or {})
        self.files = dict(files or {})
        self.texts = dict(texts or {})
        self.requested: list[str] = []

    def fetch_html(self, url):
        self.requested.append(url)
        return url, self.pages[url]

    def fetch_text(self, url):
        self.requested.append(url)
        return self.texts[url]

    def fetch_json(self, url):
        self.requested.append(url)
        return self.json_responses[url]

    def download(self, url, target: Path) -> None:
        self.requested.append(url)
        if url not in self.files:
            raise OSError(f"HTTP Error 404: {url}")
        target.write_bytes(self.files[url])


def attribute_json(data: Any) -> str:
    return html.escape(json.dumps(data), quote=True)


def srf_asset(urn: str, kind: str = "video", title: str = "Beispielclip") -> dict:
    return {
        "urn": urn,
        "type": kind,
        "title": title,
        "duration": 32160,
        "date": "2026-09-29T12:45:00+02:00",
        "image": {"provider": "il", "id": POSTER_ID},
    }


def srf_player(asset: dict) -> str:
    return f'<div class="player-widget js-player-widget" data-asset="{attribute_json(asset)}"></div>'


def resource(url: str, protocol: str, quality: str, mime: str, streaming: str) -> dict:
    return {
        "url": url,
        "protocol": protocol,
        "quality": quality,
        "mimeType": mime,
        "streaming": streaming,
        "tokenType": "NONE",
    }


HLS = resource(CLIP_HLS, "HLS", "HD", "application/x-mpegURL", "HLS")
MP4_HD = resource(CLIP_MP4_HD, "HTTP", "HD", "video/mp4", "PROGRESSIVE")
MP4_SD = resource(CLIP_MP4_SD, "HTTP", "SD", "video/mp4", "PROGRESSIVE")
MP3 = resource(CLIP_MP3, "HTTPS", "HD", "audio/mpeg", "PROGRESSIVE")


def composition(urn: str, resources: list[dict], **chapter: Any) -> dict:
    other = {
        "urn": "urn:srf:video:00000000-0000-0000-0000-000000000000",
        "resourceList": [HLS],
    }
    return {"chapterList": [other, {"urn": urn, "resourceList": resources, **chapter}]}


def srf_page(body: str, top_media: str = "") -> str:
    return f"""<!doctype html><html lang="de"><head><title>Beispiel</title></head><body>
<article class="articlepage__article js-article">
<header>
<h1 class="article-title"><span class="article-title__overline">Überzeile</span>
<span class="h-offscreen"> - </span><span class="article-title__text">Beispieltitel: Teil 1</span></h1>
<p class="article-lead">{LOREM}</p>
<div class="article-author"><p class="article-author__name"><span class="h-offscreen">Autoren:</span>
<span itemprop="author"><span itemprop="name">Erika Muster</span></span></p>
<p class="article-author__date" data-publicationdate="2026-10-19T07:22:30+02:00">19.10.2026</p></div>
</header>
{top_media}
<section class="articlepage__article-content">{body}</section>
</article></body></html>"""
