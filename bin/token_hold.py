"""Holds one secret in memory for this user's processes on this box, for `fleet master on`.

The holder reads the value from stdin, listens on a Unix socket in a folder only this user
opens, answers `get` with the value and exits on `stop`. The value never reaches argv, the
environment, a file or a log. The folder sits in the container's own /dev/shm on Linux and in
the user's $TMPDIR on macOS, never in /tmp, which every container on the Mac shares.
"""
from __future__ import annotations

import os
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Final, Mapping, Optional

SHM: Final = Path("/dev/shm")
FOLDER_PREFIX: Final = "fleet-"
SOCKET_NAME: Final = "token.sock"
PRIVATE_FOLDER_MODE: Final = 0o700
PRIVATE_SOCKET_UMASK: Final = 0o177
GET: Final = b"get"
STOP: Final = b"stop"
STOPPED: Final = b"stopped"
MAX_MESSAGE_BYTES: Final = 64 * 1024
ASK_TIMEOUT_S: Final = 2.0
START_WAIT_S: Final = 5.0
START_POLL_S: Final = 0.05
SERVE: Final = "serve"


class HoldError(RuntimeError):
    pass


def private_base(platform: str, environ: Mapping[str, str], shm: Path) -> Optional[Path]:
    if platform == "darwin":
        tmpdir = environ.get("TMPDIR")
        return Path(tmpdir) if tmpdir else None
    return shm if shm.is_dir() else None


def socket_in(base: Optional[Path], uid: int) -> Optional[Path]:
    return None if base is None else base / f"{FOLDER_PREFIX}{uid}" / SOCKET_NAME


def fetch(path: Path) -> Optional[str]:
    answer = ask(path, GET)
    return answer.decode() if answer else None


def stop(path: Path) -> bool:
    return ask(path, STOP) == STOPPED


def start(path: Path, value: str) -> None:
    private_folder(path.parent)
    if fetch(path) is not None:
        raise HoldError(f"a holder already answers on {path}")
    path.unlink(missing_ok=True)
    holder = launch(path, value)
    deadline = time.monotonic() + START_WAIT_S
    while fetch(path) is None:
        if holder.poll() is not None:
            raise HoldError(f"the holder exited with {holder.returncode}")
        if time.monotonic() > deadline:
            holder.kill()
            raise HoldError(f"the holder did not answer within {START_WAIT_S:g} s")
        time.sleep(START_POLL_S)


def launch(path: Path, value: str) -> subprocess.Popen:
    environ = {name: each for name, each in os.environ.items() if value not in each}
    holder = subprocess.Popen([sys.executable, "-I", str(Path(__file__).resolve()), SERVE, str(path)],
                              stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              env=environ, cwd="/", start_new_session=True)
    holder.stdin.write(value.encode())
    holder.stdin.close()
    return holder


def private_folder(folder: Path) -> None:
    folder.mkdir(mode=PRIVATE_FOLDER_MODE, exist_ok=True)
    if not is_private(folder.lstat()):
        raise HoldError(f"{folder} must be a folder only this user opens (mode 700)")


def is_private(info: os.stat_result) -> bool:
    return stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == PRIVATE_FOLDER_MODE


def ask(path: Path, request: bytes) -> Optional[bytes]:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(ASK_TIMEOUT_S)
            client.connect(str(path))
            client.sendall(request)
            client.shutdown(socket.SHUT_WR)
            return received(client)
    except OSError:
        return None


def received(connection: socket.socket) -> bytes:
    data = b""
    while len(data) <= MAX_MESSAGE_BYTES:
        chunk = connection.recv(MAX_MESSAGE_BYTES)
        if not chunk:
            break
        data += chunk
    return data


def serve(path: Path, value: bytes) -> None:
    with listening(path) as server:
        while answer(server, path, value):
            pass


def answer(server: socket.socket, path: Path, value: bytes) -> bool:
    connection, _ = server.accept()
    with connection:
        connection.settimeout(ASK_TIMEOUT_S)
        try:
            request = received(connection)
        except OSError:
            return True
        if request == STOP:
            path.unlink(missing_ok=True)
            send_or_drop(connection, STOPPED)
            return False
        if request == GET:
            send_or_drop(connection, value)
    return True


def send_or_drop(connection: socket.socket, message: bytes) -> None:
    try:
        connection.sendall(message)
    except OSError:
        pass


def listening(path: Path) -> socket.socket:
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    umask = os.umask(PRIVATE_SOCKET_UMASK)
    try:
        server.bind(str(path))
    finally:
        os.umask(umask)
    server.listen()
    return server


if __name__ == "__main__":
    if sys.argv[1:2] != [SERVE] or len(sys.argv) != 3:
        sys.exit(f"usage: {Path(__file__).name} {SERVE} <socket>, with the value on stdin")
    held = sys.stdin.buffer.read(MAX_MESSAGE_BYTES + 1)
    if not held or len(held) > MAX_MESSAGE_BYTES:
        sys.exit(f"give one value of at most {MAX_MESSAGE_BYTES} bytes on stdin")
    serve(Path(sys.argv[2]), held)
