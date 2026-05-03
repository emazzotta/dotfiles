#!/usr/bin/env python3
"""envify.py - resolve keyguard secrets or invoke Mac bridge endpoints.

Called by the envify bash wrapper. Outputs export statements for eval,
or plain output for flags like --list, --bridge-list, --bridge.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import NoReturn

_SERVER_PORT: int = int(os.environ.get("PARAM_SERVER_PORT", "7777"))
_CACHE_TIMEOUT: int = int(os.environ.get("ENVIFY_CACHE_TIMEOUT", "120"))
_GLOBAL_ENV_FILE: Path = Path.home() / "dotfiles" / ".env"
_BRIDGE_TOKEN_KEY: str = "MAC_BRIDGE_TOKEN"
_CANDIDATE_HOSTS: tuple[str, ...] = ("localhost", "host.docker.internal")


# ---------------------------------------------------------------------------
# Global env file
# ---------------------------------------------------------------------------


def _load_global_env() -> None:
    if not _GLOBAL_ENV_FILE.exists():
        return
    with _GLOBAL_ENV_FILE.open() as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------


def _find_reachable_host() -> str | None:
    for host in _CANDIDATE_HOSTS:
        try:
            req = urllib.request.Request(f"http://{host}:{_SERVER_PORT}/")
            urllib.request.urlopen(req, timeout=2)
        except urllib.error.HTTPError:
            return host  # Any HTTP response means the server is up
        except (urllib.error.URLError, OSError, TimeoutError):
            pass
    return None


def _require_host() -> str:
    host = _find_reachable_host()
    if host is None:
        candidates = ", ".join(f"{h}:{_SERVER_PORT}" for h in _CANDIDATE_HOSTS)
        _die(f"param server unreachable on {candidates}")
    return host


def _server_get(host: str, path: str, *, timeout: int | None = None) -> str:
    qs = f"?timeout={timeout}" if timeout else ""
    req = urllib.request.Request(
        f"http://{host}:{_SERVER_PORT}/{path}{qs}",
        headers={"X-Keyguard-Source": socket.gethostname()},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        _die(f"server returned {e.code}: {e.read().decode().strip()}")
    except urllib.error.URLError as e:
        _die(f"server unreachable: {e.reason}")


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _die(msg: str) -> NoReturn:
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def _keyguard_available() -> bool:
    return shutil.which("keyguard") is not None


def _parse_kv_output(output: str, keys: tuple[str, ...]) -> dict[str, str]:
    if len(keys) == 1:
        return {keys[0]: output.strip()}
    result: dict[str, str] = {}
    for line in output.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _decode_value(value: str) -> str:
    if not value.startswith("base64:"):
        return value
    try:
        return base64.b64decode(value[7:]).decode()
    except Exception:
        return value


# ---------------------------------------------------------------------------
# Secret resolution
# ---------------------------------------------------------------------------


def _resolve_via_keyguard(*keys: str) -> dict[str, str]:
    result = subprocess.run(["keyguard", "get", *keys], capture_output=True, text=True)
    if result.returncode != 0:
        _die(f"keyguard failed: {result.stderr.strip()}")
    return _parse_kv_output(result.stdout, keys)


def _resolve_via_server(*keys: str) -> dict[str, str]:
    host = _require_host()
    path = ",".join(keys) if len(keys) > 1 else keys[0]
    output = _server_get(host, path, timeout=_CACHE_TIMEOUT)
    return _parse_kv_output(output, tuple(keys))


def resolve_params(keys: list[str]) -> None:
    missing = [k for k in keys if k not in os.environ]
    if not missing:
        return
    resolved = (
        _resolve_via_keyguard(*missing)
        if _keyguard_available()
        else _resolve_via_server(*missing)
    )
    for key, value in resolved.items():
        print(f"export {key}={shlex.quote(_decode_value(value))}")


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def list_params() -> None:
    if _keyguard_available():
        result = subprocess.run(["keyguard", "list"])
        sys.exit(result.returncode)
    host = _require_host()
    print(_server_get(host, "_keys", timeout=_CACHE_TIMEOUT), end="")


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------


def _resolve_bridge_token() -> str:
    if _keyguard_available():
        result = subprocess.run(
            ["keyguard", "get", _BRIDGE_TOKEN_KEY],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            _die(f"keyguard failed resolving bridge token: {result.stderr.strip()}")
        return result.stdout.strip()
    host = _require_host()
    return _server_get(host, _BRIDGE_TOKEN_KEY).strip()


def _bridge_call(host: str, path: str, *, method: str = "GET", token: str | None = None) -> str:
    headers: dict[str, str] = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"http://{host}:{_SERVER_PORT}/_bridge/{path}",
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        _die(f"bridge returned {e.code}: {e.read().decode().strip()}")
    except urllib.error.URLError as e:
        _die(f"bridge unreachable: {e.reason}")


def _public_bridge_names(host: str) -> set[str]:
    raw = _bridge_call(host, "list")
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return set()
    return {
        item["name"] for item in items
        if isinstance(item, dict) and "name" in item
    }


def list_bridge_endpoints(*, include_private: bool = False) -> None:
    host = _require_host()
    token = _resolve_bridge_token() if include_private else None
    print(_bridge_call(host, "list", token=token), end="")


def call_bridge_endpoint(name: str) -> None:
    host = _require_host()
    if name in _public_bridge_names(host):
        print(_bridge_call(host, name, method="POST"), end="")
        return
    token = _resolve_bridge_token()
    print(_bridge_call(host, name, method="POST", token=token), end="")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="envify",
        description="Resolve keyguard secrets or invoke Mac bridge endpoints.",
        epilog='Load secrets into the shell with: source envify VAR1 VAR2',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--list", action="store_true", dest="list_keys",
        help="list all available secret names",
    )
    group.add_argument(
        "--bridge-list", action="store_true", dest="bridge_list",
        help="list public Mac bridge endpoints (JSON; no auth)",
    )
    group.add_argument(
        "--bridge", metavar="ENDPOINT",
        help="call a Mac bridge endpoint via POST (auth resolved only if private)",
    )
    parser.add_argument(
        "--all", action="store_true", dest="all_endpoints",
        help="with --bridge-list: include private endpoints (requires auth token)",
    )
    parser.add_argument(
        "vars", nargs="*", metavar="VAR",
        help="secret names to resolve (outputs export statements)",
    )
    return parser


def main() -> None:
    _load_global_env()
    args = _build_parser().parse_args()

    if args.list_keys:
        list_params()
    elif args.bridge_list:
        list_bridge_endpoints(include_private=args.all_endpoints)
    elif args.bridge:
        call_bridge_endpoint(args.bridge)
    elif args.vars:
        resolve_params(args.vars)


if __name__ == "__main__":
    main()
