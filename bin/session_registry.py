"""The claude sessions cl runs, kept on disk so a restart can reopen the ones it cut short.

Every running cl holds an exclusive lock on its record and deletes the record when the
session ends on purpose. The kernel drops the lock however cl dies, so a record nobody
holds belongs to a session that was interrupted.
"""
from __future__ import annotations

import fcntl
import json
import os
import shlex
import signal
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from subprocess import SubprocessError, run
from typing import IO, Final, Union
from uuid import UUID, uuid4

import scriptlog

LAUNCHER: Final = "cl"
FOLLOW_INTERVAL: Final = timedelta(seconds=2)
CLOCK_SKEW: Final = timedelta(seconds=30)
TMUX_TIMEOUT_SECONDS: Final = 5
FALLBACK_TMUX_SESSION: Final = "main"
SIGNAL_EXIT_BASE: Final = 128


@dataclass(frozen=True)
class SessionRecord:
    session_id: UUID | None
    cwd: Path
    cl_args: tuple[str, ...]
    tmux_session: str | None
    started_at: datetime

    def to_json(self) -> str:
        return json.dumps({
            "sessionId": str(self.session_id) if self.session_id else None,
            "cwd": str(self.cwd),
            "clArgs": list(self.cl_args),
            "tmuxSession": self.tmux_session,
            "startedAt": self.started_at.isoformat(),
        })

    @classmethod
    def from_json(cls, text: str) -> SessionRecord:
        data = json.loads(text)
        return cls(
            session_id=UUID(data["sessionId"]) if data["sessionId"] else None,
            cwd=Path(data["cwd"]),
            cl_args=tuple(data["clArgs"]),
            tmux_session=data["tmuxSession"],
            started_at=datetime.fromisoformat(data["startedAt"]),
        )

    def resume_command(self) -> str:
        return shlex.join([LAUNCHER, "-r", str(self.session_id), *self.cl_args])


def signal_of(returncode: int) -> int | None:
    """The signal that ended a child: Popen reports it negative, docker as 128 + n."""
    if returncode < 0:
        return -returncode
    signum = returncode - SIGNAL_EXIT_BASE
    return signum if signum > 0 and signum in signal.valid_signals() else None


def ended_by_user(signum: int | None, in_tmux: bool) -> bool:
    """A pod kill or a reboot arrives as SIGKILL and never reaches cl.

    In tmux a hangup means its window was closed (ctrl+q); outside tmux it is just as
    likely a dropped connection, and reopening a session costs less than losing it.
    """
    if signum is None or signum == signal.SIGINT:
        return True
    return signum == signal.SIGHUP and in_tmux


def current_tmux_session() -> str | None:
    pane = os.environ.get("TMUX_PANE")
    if not os.environ.get("TMUX") or not pane:
        return None
    try:
        return _tmux("display-message", "-p", "-t", pane, "#{session_name}") or None
    except (OSError, SubprocessError):
        return None


@dataclass(frozen=True)
class _ProcessState:
    session_id: UUID
    started_at: datetime
    pid_domain: str


def _read_process_state(path: Path) -> _ProcessState | None:
    try:
        data = json.loads(path.read_text())
        return _ProcessState(
            session_id=UUID(data["sessionId"]),
            started_at=datetime.fromtimestamp(data["startedAt"] / 1000, timezone.utc),
            pid_domain=str(data.get("pidDomain", "")),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


class ClaudeProcess:
    """Claude Code keeps <pid>.json per running process, naming the session it shows now.

    That name changes on /clear or /resume. Each docker container numbers its processes
    from 1, so containers sharing ~/.claude can write the same file: the pid domain tells
    this process apart from another that took the file over.
    """

    def __init__(self, directory: Path, since: datetime, pid: int | None, session_id: UUID | None) -> None:
        self._directory = directory
        self._since = since - CLOCK_SKEW
        self._file = directory / f"{pid}.json" if pid else None
        self._first_session_id = session_id
        self._pid_domain: str | None = None

    def session_id(self) -> UUID | None:
        if self._file is None:
            self._file = self._find_by_session()
        state = _read_process_state(self._file) if self._file else None
        return state.session_id if state and self._is_ours(state) else None

    def _is_ours(self, state: _ProcessState) -> bool:
        if state.started_at < self._since:
            return False
        if self._pid_domain is None:
            self._pid_domain = state.pid_domain
        return state.pid_domain == self._pid_domain

    def _find_by_session(self) -> Path | None:
        if self._first_session_id is None:
            return None
        for path in self._directory.glob("*.json"):
            state = _read_process_state(path)
            if state and state.session_id == self._first_session_id and state.started_at >= self._since:
                return path
        return None


def _write(handle: IO[str], record: SessionRecord) -> None:
    handle.seek(0)
    handle.truncate()
    handle.write(record.to_json())
    handle.flush()
    os.fsync(handle.fileno())


class TrackedSession:
    def __init__(self, handle: IO[str], path: Path, record: SessionRecord, processes: Path) -> None:
        self._handle = handle
        self._path = path
        self._record = record
        self._processes = processes
        self._lock = threading.RLock()
        self._finished = threading.Event()

    @classmethod
    def start(cls, directory: Path, record: SessionRecord, processes: Path) -> TrackedSession:
        """Lock before the record shows up under its name, so restore never claims a live one."""
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{uuid4()}.json"
        staging = path.with_suffix(".tmp")
        handle = staging.open("x")
        fcntl.flock(handle, fcntl.LOCK_EX)
        _write(handle, record)
        os.replace(staging, path)
        return cls(handle, path, record, processes)

    def __enter__(self) -> TrackedSession:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.finish(None)

    def follow(self, pid: int | None) -> None:
        process = ClaudeProcess(self._processes, self._record.started_at, pid, self._record.session_id)
        threading.Thread(target=self._follow, args=(process,), daemon=True).start()

    def finish(self, signum: int | None) -> None:
        with self._lock:
            if self._finished.is_set():
                return
            self._finished.set()
            if ended_by_user(signum, self._record.tmux_session is not None):
                self._path.unlink(missing_ok=True)
            self._handle.close()

    def _follow(self, process: ClaudeProcess) -> None:
        while not self._finished.wait(FOLLOW_INTERVAL.total_seconds()):
            session_id = process.session_id()
            if session_id is not None:
                self._update(session_id)

    def _update(self, session_id: UUID) -> None:
        with self._lock:
            if self._finished.is_set() or session_id == self._record.session_id:
                return
            self._record = replace(self._record, session_id=session_id)
            _write(self._handle, self._record)


class Untracked:
    def __enter__(self) -> Untracked:
        return self

    def __exit__(self, *_exc: object) -> None:
        pass

    def follow(self, pid: int | None) -> None:
        pass

    def finish(self, signum: int | None) -> None:
        pass


UNTRACKED: Final = Untracked()
Session = Union[TrackedSession, Untracked]


@dataclass
class _Claim:
    path: Path
    handle: IO[str]

    @classmethod
    def take(cls, path: Path) -> _Claim | None:
        try:
            handle = path.open("r+")
        except OSError:
            return None
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return None
        return cls(path, handle)

    def record(self) -> SessionRecord | None:
        try:
            return SessionRecord.from_json(self.handle.read())
        except (ValueError, KeyError, TypeError):
            return None

    def release(self, discard: bool) -> None:
        if discard:
            self.path.unlink(missing_ok=True)
        self.handle.close()


@dataclass(frozen=True)
class Registry:
    directory: Path
    claude_processes: Path
    transcripts: Path

    def track(self, record: SessionRecord | None) -> Session:
        if record is None:
            return UNTRACKED
        try:
            return TrackedSession.start(self.directory, record, self.claude_processes)
        except OSError as error:
            scriptlog.warn(f"This session will not be restorable: {error}")
            return UNTRACKED

    def count_interrupted(self) -> int:
        """How many sessions restore would reopen, leaving every record in place."""
        count = 0
        for claim in self._claims():
            record = claim.record()
            count += record is not None and self._resumable(record)
            claim.release(discard=False)
        return count

    def restore(self) -> int:
        """Reopen each interrupted session in a tmux window of the session it ran in."""
        claims = self._claims()
        if not claims:
            scriptlog.info("No interrupted sessions to restore")
            return 0
        fallback = current_tmux_session() or FALLBACK_TMUX_SESSION
        reopened = [self._reopen(claim, fallback) for claim in claims]
        return 0 if all(reopened) else 1

    def _reopen(self, claim: _Claim, fallback: str) -> bool:
        record = claim.record()
        if record is None or not self._resumable(record):
            claim.release(discard=True)
            return True
        target = record.tmux_session or fallback
        try:
            _open_window(target, record.cwd, record.resume_command())
        except (OSError, SubprocessError) as error:
            scriptlog.error(f"Could not reopen {record.session_id}: {error}")
            claim.release(discard=False)
            return False
        claim.release(discard=True)
        scriptlog.success(f"Reopened {record.session_id} in tmux session {target}")
        return True

    def _claims(self) -> list[_Claim]:
        return [claim for claim in map(_Claim.take, sorted(self.directory.glob("*.json"))) if claim]

    def _resumable(self, record: SessionRecord) -> bool:
        """A session killed before its first prompt left no transcript to resume."""
        return record.session_id is not None and (self.transcripts / f"{record.session_id}.jsonl").is_file()


def _tmux(*args: str) -> str:
    result = run(["tmux", *args], check=True, capture_output=True, text=True, timeout=TMUX_TIMEOUT_SECONDS)
    return result.stdout.strip()


def _has_tmux_session(name: str) -> bool:
    try:
        _tmux("has-session", "-t", f"={name}")
    except (OSError, SubprocessError):
        return False
    return True


def _open_window(tmux_session: str, cwd: Path, command: str) -> None:
    """Type the command into a fresh shell, so the window outlives the session as a normal one does."""
    directory = str(cwd if cwd.is_dir() else Path.home())
    if _has_tmux_session(tmux_session):
        placement = ["new-window", "-d", "-t", f"={tmux_session}:"]
    else:
        placement = ["new-session", "-d", "-s", tmux_session]
    pane = _tmux(*placement, "-c", directory, "-P", "-F", "#{pane_id}")
    _tmux("send-keys", "-t", pane, "-l", command)
    _tmux("send-keys", "-t", pane, "Enter")

