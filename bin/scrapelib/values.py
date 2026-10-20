"""Loosely typed values from pages and JSON APIs, parsed without raising."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final

UTC_SUFFIX: Final = "Z"
UTC_OFFSET: Final = "+00:00"


def parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(UTC_SUFFIX):
        text = text[: -len(UTC_SUFFIX)] + UTC_OFFSET
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def milliseconds(value: object) -> timedelta | None:
    try:
        return timedelta(milliseconds=int(str(value)))
    except (TypeError, ValueError):
        return None


def first_text(*candidates: object) -> str:
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""
