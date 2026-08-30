"""Host-specific values that must not live in this public repo.

Read from ~/.config/dotfiles/private.env (override with DOTFILES_PRIVATE_ENV),
a plain KEY=value file that shell scripts can source directly.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_OVERRIDE = "DOTFILES_PRIVATE_ENV"


def config_path() -> Path:
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return Path(override)
    config_home = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(config_home) / "dotfiles" / "private.env"


def load() -> dict[str, str]:
    path = config_path()
    if not path.is_file():
        return {}

    values = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, raw_value = stripped.partition("=")
        if separator:
            values[key.strip()] = raw_value.strip().strip('"').strip("'")
    return values


def value(key: str, default: str = "") -> str:
    return os.environ.get(key) or load().get(key, default)
