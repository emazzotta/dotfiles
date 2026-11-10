from __future__ import annotations

import sys
import unicodedata
from collections.abc import Iterator
from typing import Final

NORMAL_FORMS: Final = ("NFD", "NFC", "NFKC", "NFKD")
MOJIBAKE_CODECS: Final = ("latin-1", "mac_roman")
LEGACY_CODECS: Final = ("latin-1", "cp1252", "mac_roman", "cp437", "cp850")
SEPARATOR: Final = b"\0"
STORED: Final = "as stored"


def strip_accents(password: str) -> str:
    decomposed = unicodedata.normalize("NFKD", password)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def replace_non_ascii(password: str, replacement: str) -> str:
    return "".join(c if c.isascii() else replacement for c in password)


def lossy_ascii_spellings(password: str) -> Iterator[tuple[str, str]]:
    stripped = strip_accents(password)
    yield "accents stripped, rest as ?", replace_non_ascii(stripped, "?")
    yield "accents stripped, rest dropped", replace_non_ascii(stripped, "")
    yield "non-ASCII as ?", replace_non_ascii(password, "?")
    yield "non-ASCII dropped", replace_non_ascii(password, "")


def spellings(password: str) -> Iterator[tuple[str, bytes]]:
    utf8 = password.encode()
    yield STORED, utf8
    for form in NORMAL_FORMS:
        yield form, unicodedata.normalize(form, password).encode()
    for codec in MOJIBAKE_CODECS:
        yield f"UTF-8 read as {codec}", utf8.decode(codec).encode()
    for codec in LEGACY_CODECS:
        yield f"{codec} bytes", password.encode(codec, "replace")
    for label, spelling in lossy_ascii_spellings(password):
        yield label, spelling.encode()


def unique_spellings(password: str) -> list[tuple[str, bytes]]:
    seen: set[bytes] = set()
    result: list[tuple[str, bytes]] = []
    for label, value in spellings(password):
        if value and value not in seen:
            seen.add(value)
            result.append((label, value))
    return result


def candidates(raw: bytes) -> list[tuple[str, bytes]]:
    try:
        return unique_spellings(raw.decode())
    except UnicodeDecodeError:
        return [(STORED, raw)]


def main() -> None:
    out = sys.stdout.buffer
    for label, value in candidates(sys.stdin.buffer.read()):
        out.write(label.encode() + SEPARATOR + value + SEPARATOR)


if __name__ == "__main__":
    main()
