"""What the Mac and the dev box share when a live Claude session moves between them.

The Mac describes each repo the session had mounted and snapshots its uncommitted work into a
commit only the two machines ever see. The box finds its own checkout of the same repo by origin,
restores the snapshot into a worktree, and links the container path the session knew to it.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Final
from urllib.parse import urlparse
from uuid import UUID

from session_registry import STATE_DIR

CONTAINER_CODE: Final = PurePosixPath("/workspace/code")
WORKTREE_DIR: Final = Path(".claude") / "worktrees"
MOVE_REF_PREFIX: Final = "refs/claude-move"
LEASE_DIR: Final = STATE_DIR / "moved"
SNAPSHOT_MESSAGE: Final = "claude-move snapshot"
SNAPSHOT_IDENTITY: Final = {
    "GIT_AUTHOR_NAME": "claude-move", "GIT_AUTHOR_EMAIL": "claude-move@localhost",
    "GIT_COMMITTER_NAME": "claude-move", "GIT_COMMITTER_EMAIL": "claude-move@localhost",
}
SHORT_SHA: Final = 7
SHORT_SESSION: Final = 8
BRANCH_ATTEMPTS: Final = 10
SCRATCH_PREFIX_DEPTH: Final = 2
SCRATCHPAD_DEPTH: Final = 4
PRIVATE_DIR: Final = 0o700
SCP_LIKE_URL: Final = re.compile(r"^(?:[^@/]+@)?([^:/]+):(?!//)(.+)$")


class MoveError(Exception):
    pass


def git(directory: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", str(directory), *args], capture_output=True, text=True,
        env={**os.environ, **env} if env else None,
    )
    if result.returncode != 0:
        raise MoveError(f"git {' '.join(args)} in {directory}: {result.stderr.strip()}")
    return result.stdout.strip()


def probe(directory: Path, *args: str) -> str | None:
    try:
        return git(directory, *args)
    except MoveError:
        return None


def relative(path: Path, base: Path) -> str:
    try:
        rest = path.relative_to(base)
    except ValueError:
        return ""
    return "" if rest == Path(".") else rest.as_posix()


def short(session: UUID) -> str:
    return str(session)[:SHORT_SESSION]


@dataclass(frozen=True)
class RepoState:
    """One work tree the session had mounted, as it stood when the session ended."""

    links: tuple[tuple[str, str], ...]
    name: str
    origin: str
    worktree: str
    branch: str
    head: str
    snapshot: str

    @property
    def containers(self) -> tuple[str, ...]:
        return tuple(container for container, _subdir in self.links)


@dataclass(frozen=True)
class MountedRepo:
    """A Mac work tree and every container path the session reached it by."""

    top: Path
    main: Path
    origin: str
    links: tuple[tuple[str, str], ...]

    @classmethod
    def find(cls, host: Path, container: str) -> MountedRepo | None:
        directory = host if host.is_dir() else host.parent
        top = probe(directory, "rev-parse", "--show-toplevel")
        if top is None or probe(directory, "rev-parse", "--verify", "-q", "HEAD") is None:
            return None
        root = Path(top).resolve()
        common = Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        origin = probe(root, "config", "--get", "remote.origin.url") or ""
        return cls(root, common.resolve().parent, origin, ((container, relative(host.resolve(), root)),))

    def joined(self, other: MountedRepo) -> MountedRepo:
        return replace(self, links=self.links + other.links)

    def state(self) -> RepoState:
        head = git(self.top, "rev-parse", "HEAD")
        return RepoState(
            links=self.links, name=self.main.name, origin=self.origin,
            worktree=relative(self.top, self.main),
            branch=probe(self.top, "symbolic-ref", "--short", "-q", "HEAD") or "",
            head=head, snapshot=snapshot(self.top, head),
        )


def snapshot(top: Path, head: str) -> str:
    """A commit of the whole work tree, untracked files included, made without touching the real index.

    Empty when there is nothing to carry: no uncommitted change, and HEAD is on some remote branch.
    """
    tree = work_tree(top)
    if tree == git(top, "rev-parse", f"{head}^{{tree}}") and pushed(top, head):
        return ""
    return git(top, "commit-tree", "--no-gpg-sign", tree, "-p", head, "-m", SNAPSHOT_MESSAGE, env=SNAPSHOT_IDENTITY)


def work_tree(top: Path) -> str:
    index = Path(git(top, "rev-parse", "--path-format=absolute", "--git-path", "index"))
    with tempfile.TemporaryDirectory() as staging:
        scratch = Path(staging) / "index"
        if index.is_file():
            shutil.copy2(index, scratch)
        env = {"GIT_INDEX_FILE": str(scratch)}
        git(top, "add", "-A", env=env)
        return git(top, "write-tree", env=env)


def pushed(top: Path, head: str) -> bool:
    return bool(git(top, "for-each-ref", "--count=1", "--contains", head, "--format=%(refname)", "refs/remotes"))


def group_by_repo(repos: Sequence[MountedRepo]) -> list[MountedRepo]:
    """Two mounts into one work tree share a single snapshot and worktree."""
    grouped: dict[Path, MountedRepo] = {}
    for repo in repos:
        grouped[repo.top] = grouped[repo.top].joined(repo) if repo.top in grouped else repo
    return list(grouped.values())


def move_ref(session: UUID, index: int) -> str:
    return f"{MOVE_REF_PREFIX}/{session}/{index}"


def normalize_origin(url: str) -> str:
    """`git@host:a/b.git`, `ssh://git@host:22/a/b` and `https://host/a/b` all name host/a/b."""
    text = url.strip()
    match = SCP_LIKE_URL.match(text)
    if match:
        host, path = match.group(1), match.group(2)
    else:
        parsed = urlparse(text)
        host, path = parsed.hostname or "", parsed.path
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    return f"{host}/{path}".strip("/").lower()


def find_checkout(projects: Path, name: str, origin: str) -> Path | None:
    """This machine's main checkout of the repo with that origin, trying folders of the same name first."""
    wanted = normalize_origin(origin)
    if not wanted:
        return None
    candidates = sorted((path.parent for path in projects.glob("*/*/.git") if path.is_dir()),
                        key=lambda checkout: checkout.name != name)
    for checkout in candidates:
        url = probe(checkout, "config", "--get", "remote.origin.url")
        if url and normalize_origin(url) == wanted:
            return checkout
    return None


def checked_out_branches(checkout: Path) -> set[str]:
    prefix = "branch refs/heads/"
    lines = git(checkout, "worktree", "list", "--porcelain").splitlines()
    return {line[len(prefix):] for line in lines if line.startswith(prefix)}


def branch_free(checkout: Path, branch: str, head: str) -> bool:
    """Free to point at head: not checked out anywhere, and absent or behind head."""
    if (checkout / WORKTREE_DIR / branch).exists() or branch in checked_out_branches(checkout):
        return False
    if probe(checkout, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}") is None:
        return True
    return probe(checkout, "merge-base", "--is-ancestor", branch, head) is not None


def free_branch(checkout: Path, wanted: str, head: str, tag: str) -> str:
    candidates = [wanted, f"{wanted}-moved-{tag}"]
    candidates += [f"{wanted}-moved-{tag}-{attempt}" for attempt in range(2, BRANCH_ATTEMPTS)]
    for candidate in candidates:
        if branch_free(checkout, candidate, head):
            return candidate
    raise MoveError(f"no free branch name for {wanted} in {checkout}")


def restore(state: RepoState, checkout: Path, ref: str, git_wt: Path, session: UUID) -> tuple[Path, str]:
    """Check the snapshot out in a worktree, then reset to its parent so the changes are uncommitted again."""
    tag = short(session)
    branch = free_branch(checkout, state.branch or f"moved-{tag}", state.head, tag)
    git(checkout, "branch", "-f", branch, state.snapshot)
    added = subprocess.run([str(git_wt), "add", branch], cwd=checkout, capture_output=True, text=True)
    if added.returncode != 0:
        raise MoveError(f"git wt add {branch} in {checkout}: {added.stderr.strip()}")
    worktree = Path(added.stdout.strip().splitlines()[-1])
    git(worktree, "reset", "-q", "--mixed", state.head)
    git(checkout, "update-ref", "-d", ref)
    return worktree, branch


def link(container: str, target: Path, links_root: Path) -> bool:
    """Point a container path the session knew at target; never replaces a real folder or leaves links_root."""
    try:
        rest = PurePosixPath(container).relative_to(CONTAINER_CODE)
    except ValueError:
        return False
    if rest == PurePosixPath("."):
        return False
    path = links_root / rest
    if path.exists() and not path.is_symlink():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.claude-move")
    if staging.is_symlink() or staging.exists():
        staging.unlink()
    staging.symlink_to(target)
    os.replace(staging, path)
    return True


@dataclass(frozen=True)
class MovePlan:
    session: UUID
    moved_at: datetime
    repos: tuple[RepoState, ...]
    missing: tuple[str, ...]
    transcript_bytes: int
    scratchpad: bool

    def to_json(self) -> str:
        return json.dumps({
            "session": str(self.session),
            "movedAt": self.moved_at.isoformat(),
            "repos": [asdict(repo) for repo in self.repos],
            "missing": list(self.missing),
            "transcriptBytes": self.transcript_bytes,
            "scratchpad": self.scratchpad,
        })

    @classmethod
    def from_json(cls, text: str) -> MovePlan:
        data = json.loads(text)
        repos = tuple(
            RepoState(**{**repo, "links": tuple(tuple(pair) for pair in repo["links"])}) for repo in data["repos"]
        )
        return cls(
            session=UUID(data["session"]),
            moved_at=datetime.fromisoformat(data["movedAt"]),
            repos=repos,
            missing=tuple(data["missing"]),
            transcript_bytes=int(data["transcriptBytes"]),
            scratchpad=bool(data["scratchpad"]),
        )


def resume_prompt(plan: MovePlan, arrivals: Sequence[str]) -> str:
    """The session's first message on the box. One line: it is typed into a shell."""
    parts = [f"This session just moved from the Mac to the devbox (claude-move, {plan.moved_at:%H:%M})."]
    parts += arrivals
    if plan.missing:
        parts.append(f"Not on the devbox: {', '.join(plan.missing)}.")
    if plan.scratchpad:
        parts.append("Your scratchpad files came along.")
    parts.append("Background tasks and monitors from before the move were stopped; restart the ones still needed.")
    parts.append("Continue the task where you left off; if you were waiting for my answer, ask again.")
    return " ".join(part.replace("\n", " ") for part in parts)


class TranscriptPending(MoveError):
    pass


@dataclass(frozen=True)
class BoxPaths:
    projects: Path
    links: Path
    claude_home: Path
    scratch: Path
    git_wt: Path

    def transcript(self, session: UUID) -> Path:
        return self.claude_home / "projects" / "-workspace" / f"{session}.jsonl"


def receive(plan: MovePlan, paths: BoxPaths) -> str:
    """Restore and link every repo, and return the resumed session's first message.

    Raises TranscriptPending before touching anything while the transcript is still short of
    what the Mac sent, so the Mac can sync again and retry.
    """
    transcript = paths.transcript(plan.session)
    if not transcript.is_file() or transcript.stat().st_size != plan.transcript_bytes:
        raise TranscriptPending(f"{transcript} does not hold the {plan.transcript_bytes} bytes the Mac has")
    arrivals = [arrive(repo, move_ref(plan.session, index), plan.session, paths)
                for index, repo in enumerate(plan.repos)]
    return resume_prompt(plan, arrivals)


def arrive(state: RepoState, ref: str, session: UUID, paths: BoxPaths) -> str:
    checkout = find_checkout(paths.projects, state.name, state.origin)
    if checkout is None:
        stayed = "; its uncommitted work stayed on the Mac" if state.snapshot else ""
        return f"{', '.join(state.containers)}: no checkout of {state.origin or state.name} on the devbox{stayed}."
    if state.snapshot:
        worktree, branch = restore(state, checkout, ref, paths.git_wt, session)
        detail = (f"branch {branch} at the Mac's commit {state.head[:SHORT_SHA]},"
                  " with its uncommitted changes restored unstaged")
        return linked_sentence(state, worktree, detail, paths.links)
    box_branch = probe(checkout, "symbolic-ref", "--short", "-q", "HEAD") or "a detached HEAD"
    box_head = git(checkout, "rev-parse", "HEAD")
    detail = f"the devbox checkout, {box_branch} at {box_head[:SHORT_SHA]}"
    if box_head != state.head:
        detail += f"; the Mac was on {state.branch or 'a detached HEAD'} at {state.head[:SHORT_SHA]}, all pushed"
    return linked_sentence(state, checkout, detail, paths.links)


def linked_sentence(state: RepoState, root: Path, detail: str, links_root: Path) -> str:
    linked: list[str] = []
    blocked: list[str] = []
    for container, subdir in state.links:
        (linked if link(container, root / subdir if subdir else root, links_root) else blocked).append(container)
    sentences = [f"{', '.join(linked)} now link to {root} ({detail})."] if linked else []
    if blocked:
        sentences.append(f"{', '.join(blocked)} could not be linked (a real folder is in the way): "
                         f"the work is in {root} ({detail}).")
    return " ".join(sentences)


def scratchpad_member(name: str, session: UUID) -> bool:
    parts = PurePosixPath(name).parts
    return (len(parts) >= SCRATCHPAD_DEPTH and parts[0].startswith("claude-") and parts[1] == "-workspace"
            and parts[2] == str(session) and parts[3] == "scratchpad" and ".." not in parts)


def unpack_scratchpad(archive: bytes, session: UUID, scratch: Path) -> None:
    """Unpack the Mac container's /tmp/claude-<uid>/-workspace/<session>/scratchpad under scratch."""
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        members = tar.getmembers()
    if not all(scratchpad_member(member.name, session) and (member.isfile() or member.isdir()) for member in members):
        raise MoveError("the scratchpad archive holds something other than plain files of that scratchpad")
    scratch.parent.mkdir(mode=PRIVATE_DIR, parents=True, exist_ok=True)
    scratch.mkdir(mode=PRIVATE_DIR, exist_ok=True)
    result = subprocess.run(["tar", "-xf", "-", f"--strip-components={SCRATCH_PREFIX_DEPTH}", "-C", str(scratch)],
                            input=archive, capture_output=True)
    if result.returncode != 0:
        raise MoveError(f"unpacking the scratchpad: {result.stderr.decode(errors='replace').strip()}")


@dataclass(frozen=True)
class Lease:
    """A session that moved away, so resuming it on the old machine is a deliberate fork, not an accident."""

    session: UUID
    moved_at: datetime
    to: str


def lease_path(session: UUID) -> Path:
    return LEASE_DIR / f"{session}.json"


def write_lease(lease: Lease) -> None:
    path = lease_path(lease.session)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"session": str(lease.session), "movedAt": lease.moved_at.isoformat(), "to": lease.to}))


def read_lease(session: UUID) -> Lease | None:
    try:
        data = json.loads(lease_path(session).read_text())
        return Lease(UUID(data["session"]), datetime.fromisoformat(data["movedAt"]), data["to"])
    except (OSError, ValueError, KeyError):
        return None


def clear_lease(session: UUID) -> None:
    lease_path(session).unlink(missing_ok=True)
