"""Shared by the scripts that run on both ends of the keyguard bridge.

In the container they map paths to the Mac paths Docker Desktop shares them from; on the
Mac, launchd starts a bridge command with a PATH that has neither Homebrew nor Docker on it.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Final

MOUNTINFO: Final = Path("/proc/self/mountinfo")
MAC_USERS_DIR: Final = Path("/Users")
# Docker Desktop shares /Users as virtiofs0 (the first file-sharing entry) or, with the
# fakeowner driver, from /run/host_mark/Users; /tmp and /Volumes come from other sources.
USERS_SHARE_SOURCES: Final = (
    ("virtiofs", "virtiofs0"),
    ("fakeowner", "/run/host_mark/Users"),
)
OCTAL_ESCAPE: Final = re.compile(r"\\([0-7]{3})")
TOOL_DIRS: Final = ("/opt/homebrew/bin", "/usr/local/bin", str(Path.home() / ".docker" / "bin"))


def unescape(field: str) -> str:
    return OCTAL_ESCAPE.sub(lambda match: chr(int(match.group(1), 8)), field)


def parse_users_mounts(mountinfo: str) -> list[tuple[Path, Path]]:
    mounts = []
    for line in mountinfo.splitlines():
        fields, _, tail = line.partition(" - ")
        parts, source = fields.split(), tail.split()
        if len(parts) < 5 or tuple(source[:2]) not in USERS_SHARE_SOURCES:
            continue
        mac_path = MAC_USERS_DIR / unescape(parts[3]).lstrip("/")
        mounts.append((Path(unescape(parts[4])), mac_path))
    return mounts


def read_users_mounts(mountinfo: Path) -> list[tuple[Path, Path]]:
    return parse_users_mounts(mountinfo.read_text()) if mountinfo.is_file() else []


def to_mac_path(path: Path, mounts: Sequence[tuple[Path, Path]]) -> Path | None:
    candidates = [pair for pair in mounts if path == pair[0] or pair[0] in path.parents]
    if not candidates:
        return None
    mount_point, mac_root = max(candidates, key=lambda pair: len(pair[0].parts))
    return mac_root / path.relative_to(mount_point)
