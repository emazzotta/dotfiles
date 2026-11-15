"""How claude-sync and claude-move reach the dev box: both share one ssh control master, so one set of options."""
from __future__ import annotations

import os
from typing import Final

REMOTE_ENV: Final = "CLAUDE_SYNC_REMOTE"
DEFAULT_REMOTE: Final = "devbox"
SSH_OPTIONS: Final = (
    "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "RequestTTY=no",
    "-o", "ControlMaster=auto", "-o", "ControlPath=~/.ssh/claude-sync-%C", "-o", "ControlPersist=60",
)


def remote() -> str:
    return os.environ.get(REMOTE_ENV, DEFAULT_REMOTE)
