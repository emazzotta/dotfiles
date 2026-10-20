"""Fetching and downloads: plain files over HTTP, HLS streams through ffmpeg."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import urllib.request
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Final

from scrapelib.article import Asset, Transfer, Url

USER_AGENT: Final = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
TIMEOUT_SECONDS: Final = 60
CHUNK_BYTES: Final = 1 << 20
PARTIAL_SUFFIX: Final = ".part"
DEFAULT_CHARSET: Final = "utf-8"
STREAM_INF: Final = re.compile(r"^#EXT-X-STREAM-INF:(.*)$", re.MULTILINE)
BANDWIDTH: Final = re.compile(r"(?:^|,)BANDWIDTH=(\d+)")
RESOLUTION: Final = re.compile(r"(?:^|,)RESOLUTION=(\d+)x(\d+)")
DOWNLOAD_ERRORS: Final = (OSError, ValueError, subprocess.CalledProcessError)

Runner = Callable[[Sequence[str]], None]
Saved = Callable[[Asset, Path], None]
Failed = Callable[[Asset, str], None]


class Fetcher:
    def __init__(
        self, user_agent: str = USER_AGENT, timeout: float = TIMEOUT_SECONDS
    ) -> None:
        self._headers = {"User-Agent": user_agent}
        self._timeout = timeout

    def fetch_html(self, url: Url) -> tuple[Url, str]:
        request = urllib.request.Request(url, headers=self._headers)
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            charset = response.headers.get_content_charset() or DEFAULT_CHARSET
            return Url(response.geturl()), response.read().decode(
                charset, errors="replace"
            )

    def fetch_text(self, url: Url) -> str:
        return self.fetch_html(url)[1]

    def fetch_json(self, url: Url) -> Any:
        return json.loads(self.fetch_text(url))

    def download(self, url: Url, target: Path) -> None:
        request = urllib.request.Request(url, headers=self._headers)
        response = urllib.request.urlopen(request, timeout=self._timeout)
        with response, target.open("wb") as file:
            shutil.copyfileobj(response, file, CHUNK_BYTES)


def run_quietly(command: Sequence[str]) -> None:
    subprocess.run(list(command), check=True, capture_output=True, text=True)


@dataclass(frozen=True)
class Variant:
    index: int
    bandwidth: int
    pixels: int


def variant_from(index: int, attributes: str) -> Variant:
    bandwidth = BANDWIDTH.search(attributes)
    resolution = RESOLUTION.search(attributes)
    pixels = int(resolution.group(1)) * int(resolution.group(2)) if resolution else 0
    return Variant(index, int(bandwidth.group(1)) if bandwidth else 0, pixels)


def best_variant(master_playlist: str) -> int | None:
    variants = [
        variant_from(index, attributes)
        for index, attributes in enumerate(STREAM_INF.findall(master_playlist))
    ]
    if not variants:
        return None
    return max(variants, key=lambda variant: (variant.bandwidth, variant.pixels)).index


def hls_command(url: Url, variant: int | None, target: Path) -> list[str]:
    program = "" if variant is None else f"p:{variant}:"
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        url,
        "-map",
        f"0:{program}v:0?",
        "-map",
        f"0:{program}a:0?",
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        "-f",
        "mp4",
        str(target),
    ]


def describe_failure(error: Exception) -> str:
    if isinstance(error, subprocess.CalledProcessError):
        lines = (error.stderr or "").strip().splitlines()
        return lines[-1] if lines else f"ffmpeg exited with {error.returncode}"
    return str(error)


class Downloader:
    def __init__(self, fetcher: Fetcher, run: Runner = run_quietly) -> None:
        self._fetcher = fetcher
        self._run = run

    def save_all(
        self, assets: Iterable[Asset], folder: Path, saved: Saved, failed: Failed
    ) -> None:
        for asset in assets:
            target = folder / asset.local_path
            try:
                if not target.exists():
                    self._save(asset, target)
            except DOWNLOAD_ERRORS as error:
                failed(asset, describe_failure(error))
            else:
                saved(asset, target)

    def _save(self, asset: Asset, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + PARTIAL_SUFFIX)
        if asset.transfer is Transfer.HLS:
            variant = best_variant(self._fetcher.fetch_text(asset.url))
            self._run(hls_command(asset.url, variant, partial))
        else:
            self._fetcher.download(asset.url, partial)
        partial.replace(target)
