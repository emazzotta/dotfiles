"""Send a notice to Telegram through the unlock service, from the dev box, the Mac or a Mac container.

The service holds the bot token and composes the message. The dev box reaches it with its request
token, the Mac with its tailnet identity, and a Mac container through the public keyguard bridge
endpoint `claude-notify`, which runs `claude-notify send` on the Mac. A notice is the JSON
{"session", "container", "title", "text", "kind"}; the session must be a Claude conversation UUID,
the one a Telegram reply goes back to. An `answer` also carries "presence" and "seen", the presence
and the last use at a web terminal when it went out, which the bot reads to decide on a voice.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import timedelta
from enum import Enum
from pathlib import Path
from typing import Final
from uuid import UUID

import presence
import session_title

SEND_TIMEOUT: Final = timedelta(seconds=10)
DEFAULT_STORE_URL: Final = "https://unlock.asymptote-bass.ts.net"
DEVBOX_TOKEN_FILE: Final = Path("/etc/devbox-unlock/request-token")
BRIDGE_ENDPOINT: Final = "claude-notify"
IS_MAC: Final = sys.platform == "darwin"


class PingKind(Enum):
    FINISHED = "finished"
    PROMPT = "prompt"
    ANSWER = "answer"


def container_label() -> str | None:
    return None if IS_MAC else socket.gethostname().split(".")[0]


def notice(session: UUID, text: str, kind: PingKind, reading: presence.Reading | None = None) -> dict:
    body = {"session": str(session), "container": container_label(), "title": session_title.find(session) or None,
            "text": text, "kind": kind.value}
    if reading is not None:
        body.update({"presence": reading.presence.value, "seen": reading.last_use})
    return body


def post_to_store(body: str, bearer: str | None) -> int:
    url = f"{os.environ.get('KEYGUARD_STORE_URL', DEFAULT_STORE_URL)}/notify"
    headers = {"Content-Type": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    request = urllib.request.Request(url, data=body.encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=SEND_TIMEOUT.total_seconds()) as response:
            response.read()
    except (OSError, ValueError) as error:
        detail = f"HTTP {error.code}" if isinstance(error, urllib.error.HTTPError) else type(error).__name__
        print(f"{Path(sys.argv[0]).name}: not sent ({detail})", file=sys.stderr)
        return 1
    return 0


def deliver(body: str) -> int:
    if DEVBOX_TOKEN_FILE.is_file():
        return post_to_store(body, DEVBOX_TOKEN_FILE.read_text().strip())
    if IS_MAC:
        return post_to_store(body, None)
    command = ["envify", "--bridge", BRIDGE_ENDPOINT, "--stdin"]
    return subprocess.run(command, input=body, text=True, stdout=subprocess.DEVNULL, check=False).returncode


def send(session: UUID, text: str, kind: PingKind) -> int:
    return deliver(json.dumps(notice(session, text, kind)))
