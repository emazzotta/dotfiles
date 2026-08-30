"""Site-specific values for the scripts in this directory.

Three layers, highest first: the environment, the machine's own overrides in
~/.config/dotfiles/site.env, and the defaults in site.env next to this module.
Both files are plain KEY=value, so shell scripts can source them directly.
"""
from __future__ import annotations

import os
from pathlib import Path

OVERRIDE_ENV = "DOTFILES_SITE_ENV"
DEFAULTS_ENV = "DOTFILES_SITE_DEFAULTS"
FILENAME = "site.env"


def defaults_path() -> Path:
    override = os.environ.get(DEFAULTS_ENV)
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / FILENAME


def override_path() -> Path:
    override = os.environ.get(OVERRIDE_ENV)
    if override:
        return Path(override)
    config_home = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(config_home) / "dotfiles" / FILENAME


def parse(path: Path) -> dict[str, str]:
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


def load() -> dict[str, str]:
    values = parse(defaults_path())
    values.update(parse(override_path()))
    return values


def value(key: str, default: str = "") -> str:
    return os.environ.get(key) or load().get(key, default)
