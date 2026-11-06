import fcntl
import io
import json
import os
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest

from bin.tests.conftest import BIN_DIR

SESSION = UUID("3f1c2b9a-5d6e-4f70-8a91-b2c3d4e5f601")
OTHER_SESSION = UUID("0a0b0c0d-1e2f-4a5b-8c6d-7e8f9a0b1c2d")
MOVED_AT = datetime(2026, 11, 6, 14, 2, tzinfo=timezone.utc)
CONTAINER = "/workspace/code/foo"
TRANSCRIPT = b'{"type":"user"}\n'


@pytest.fixture(autouse=True)
def isolated_git(git_env, monkeypatch):
    for name, value in git_env.items():
        monkeypatch.setenv(name, value)


@pytest.fixture
def sm(load_module):
    return load_module("session_move")


@pytest.fixture
def registry(load_module):
    return load_module("session_registry")


@pytest.fixture
def cli(load_script):
    return load_script("claude-move")


@pytest.fixture
def world(tmp_path, git):
    origin = tmp_path / "origin" / "foo.git"
    origin.parent.mkdir()
    git(tmp_path, "init", "-q", "--bare", str(origin))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", "-q", str(origin), str(seed))
    for name, content in (("kept.txt", "kept\n"), ("gone.txt", "gone\n"), ("edited.txt", "v1\n")):
        (seed / name).write_text(content)
    git(seed, "add", ".")
    git(seed, "commit", "-q", "-m", "Seed")
    git(seed, "push", "-q", "origin", "main")
    mac = tmp_path / "mac" / "Projects" / "private" / "foo"
    box = tmp_path / "box" / "Projects" / "leo-projects" / "foo"
    for checkout in (mac, box):
        checkout.parent.mkdir(parents=True)
        git(tmp_path, "clone", "-q", str(origin), str(checkout))
    return SimpleNamespace(origin=origin, mac=mac, box=box, projects=tmp_path / "box" / "Projects", tmp=tmp_path)


@pytest.fixture
def box_paths(sm, world, tmp_path):
    claude_home = tmp_path / "box-claude"
    (claude_home / "projects" / "-workspace").mkdir(parents=True)
    return sm.BoxPaths(projects=world.projects, links=tmp_path / "links", claude_home=claude_home,
                       scratch=tmp_path / "scratch" / "-workspace", git_wt=BIN_DIR / "git-wt")


def dirty(git, checkout):
    (checkout / "edited.txt").write_text("v2\n")
    git(checkout, "add", "edited.txt")
    (checkout / "gone.txt").unlink()
    (checkout / "new.txt").write_text("new\n")


def carried(sm, git, world, index=0):
    state = sm.MountedRepo.find(world.mac, CONTAINER).state()
    if state.snapshot:
        git(world.mac, "push", "-q", str(world.box), f"{state.snapshot}:{sm.move_ref(SESSION, index)}")
    return state


def plan_for(sm, box_paths, *states, missing=(), sent=TRANSCRIPT, arrived=TRANSCRIPT):
    box_paths.transcript(SESSION).write_bytes(arrived)
    return sm.MovePlan(SESSION, MOVED_AT, tuple(states), tuple(missing), len(sent), False)


def porcelain(checkout):
    """Unstripped, so the column that tells staged from unstaged survives."""
    return subprocess.run(["git", "-C", str(checkout), "status", "--porcelain"], capture_output=True, text=True,
                          check=True).stdout.splitlines()


def worktree_of(world, branch):
    return world.box / ".claude" / "worktrees" / branch


def should_snapshot_modified_deleted_and_untracked_files_without_touching_the_index(sm, git, world):
    dirty(git, world.mac)
    status_before = git(world.mac, "status", "--porcelain")

    state = sm.MountedRepo.find(world.mac, CONTAINER).state()

    assert git(world.mac, "status", "--porcelain") == status_before
    carried_files = git(world.mac, "ls-tree", "-r", "--name-only", state.snapshot).split()
    assert carried_files == ["edited.txt", "kept.txt", "new.txt"]
    assert git(world.mac, "show", f"{state.snapshot}:edited.txt") == "v2"
    assert git(world.mac, "rev-parse", f"{state.snapshot}^") == state.head


def should_carry_nothing_when_the_work_tree_is_clean_and_pushed(sm, world):
    assert sm.MountedRepo.find(world.mac, CONTAINER).state().snapshot == ""


def should_carry_unpushed_commits_of_a_clean_work_tree(sm, git, world):
    (world.mac / "kept.txt").write_text("committed, not pushed\n")
    git(world.mac, "commit", "-q", "-am", "Local only")

    state = sm.MountedRepo.find(world.mac, CONTAINER).state()

    assert state.snapshot
    assert git(world.mac, "rev-parse", f"{state.snapshot}^{{tree}}") == git(world.mac, "rev-parse", "HEAD^{tree}")


def should_describe_a_mount_outside_any_repo_as_none(sm, tmp_path):
    (tmp_path / "Desktop").mkdir()

    assert sm.MountedRepo.find(tmp_path / "Desktop", "/workspace/code/Desktop") is None


def should_join_two_mounts_of_one_work_tree(sm, world):
    (world.mac / "sub").mkdir()
    mounts = [sm.MountedRepo.find(world.mac, CONTAINER), sm.MountedRepo.find(world.mac / "sub", "/workspace/code/sub")]

    grouped = sm.group_by_repo(mounts)

    assert [repo.links for repo in grouped] == [((CONTAINER, ""), ("/workspace/code/sub", "sub"))]


@pytest.mark.parametrize("url,expected", [
    ("git@github.com:emazzotta/dotfiles.git", "github.com/emazzotta/dotfiles"),
    ("ssh://git@github.com:22/emazzotta/dotfiles", "github.com/emazzotta/dotfiles"),
    ("https://github.com/Emazzotta/Dotfiles.git/", "github.com/emazzotta/dotfiles"),
    ("/srv/git/foo.git", "srv/git/foo"),
    ("", ""),
])
def should_normalize_origins_that_name_the_same_repo(sm, url, expected):
    assert sm.normalize_origin(url) == expected


def should_find_the_checkout_by_origin_when_the_folder_layout_differs(sm, git, world):
    copy = world.projects / "private" / "a-copy-of-foo"
    copy.parent.mkdir(parents=True)
    git(world.tmp, "clone", "-q", str(world.origin), str(copy))

    assert sm.find_checkout(world.projects, "foo", str(world.origin)) == world.box
    assert sm.find_checkout(world.projects, "foo", "git@github.com:someone/else.git") is None


def should_restore_uncommitted_work_in_a_worktree_of_the_same_branch(sm, git, world, box_paths):
    git(world.mac, "checkout", "-q", "-b", "feature")
    dirty(git, world.mac)
    state = carried(sm, git, world)

    prompt = sm.receive(plan_for(sm, box_paths, state), box_paths)

    worktree = worktree_of(world, "feature")
    assert git(worktree, "rev-parse", "HEAD") == state.head
    assert porcelain(worktree) == [" M edited.txt", " D gone.txt", "?? new.txt"]
    assert (box_paths.links / "foo").resolve() == worktree.resolve()
    assert git(world.box, "for-each-ref", "refs/claude-move") == ""
    assert f"{CONTAINER} now link to {worktree}" in prompt
    assert "branch feature at the Mac's commit" in prompt


def should_restore_on_a_new_branch_when_the_box_has_that_branch_checked_out(sm, git, world, box_paths):
    dirty(git, world.mac)
    state = carried(sm, git, world)

    sm.receive(plan_for(sm, box_paths, state), box_paths)

    assert git(worktree_of(world, "main-moved-3f1c2b9a"), "rev-parse", "--abbrev-ref", "HEAD") == "main-moved-3f1c2b9a"


def should_restore_on_a_new_branch_when_the_box_branch_has_diverged(sm, git, world, box_paths):
    git(world.box, "branch", "feature")
    git(world.box, "commit", "-q", "--allow-empty", "-m", "Box only")
    git(world.box, "branch", "-f", "feature", "HEAD")
    git(world.box, "reset", "-q", "--hard", "origin/main")
    git(world.mac, "checkout", "-q", "-b", "feature")
    dirty(git, world.mac)
    state = carried(sm, git, world)

    sm.receive(plan_for(sm, box_paths, state), box_paths)

    assert worktree_of(world, "feature-moved-3f1c2b9a").is_dir()
    assert git(world.box, "log", "-1", "--format=%s", "feature") == "Box only"


def should_move_a_box_branch_forward_when_it_is_behind_the_mac(sm, git, world, box_paths):
    git(world.box, "branch", "feature")
    git(world.mac, "checkout", "-q", "-b", "feature")
    (world.mac / "kept.txt").write_text("ahead\n")
    git(world.mac, "commit", "-q", "-am", "Mac only")
    state = carried(sm, git, world)

    sm.receive(plan_for(sm, box_paths, state), box_paths)

    assert git(world.box, "rev-parse", "feature") == state.head
    assert git(worktree_of(world, "feature"), "status", "--porcelain") == ""


def should_touch_nothing_before_the_whole_transcript_has_arrived(sm, git, world, box_paths):
    dirty(git, world.mac)
    state = carried(sm, git, world)
    plan = plan_for(sm, box_paths, state, arrived=TRANSCRIPT[:-3])

    with pytest.raises(sm.TranscriptPending):
        sm.receive(plan, box_paths)

    assert not (world.box / ".claude" / "worktrees").exists()


def should_link_a_clean_pushed_repo_to_the_box_checkout(sm, git, world, box_paths):
    state = carried(sm, git, world)

    prompt = sm.receive(plan_for(sm, box_paths, state), box_paths)

    assert (box_paths.links / "foo").resolve() == world.box.resolve()
    assert f"now link to {world.box} (the devbox checkout, main at" in prompt


def should_say_which_repos_have_no_checkout_on_the_box(sm, git, world, box_paths):
    git(world.mac, "remote", "set-url", "origin", "git@github.com:someone/elsewhere.git")
    dirty(git, world.mac)
    state = sm.MountedRepo.find(world.mac, CONTAINER).state()

    prompt = sm.receive(plan_for(sm, box_paths, state, missing=("/workspace/code/Desktop",)), box_paths)

    assert "no checkout of git@github.com:someone/elsewhere.git on the devbox" in prompt
    assert "its uncommitted work stayed on the Mac" in prompt
    assert "Not on the devbox: /workspace/code/Desktop." in prompt


def should_write_a_one_line_prompt(sm, box_paths):
    plan = plan_for(sm, box_paths, missing=("/workspace/code/Desktop",))

    prompt = sm.receive(plan, box_paths)

    assert "\n" not in prompt
    assert prompt.startswith("This session just moved from the Mac to the devbox (claude-move, 14:02).")


def should_never_replace_a_real_folder_with_a_link(sm, tmp_path):
    (tmp_path / "links" / "foo").mkdir(parents=True)

    assert sm.link(CONTAINER, tmp_path / "target", tmp_path / "links") is False
    assert not (tmp_path / "links" / "foo").is_symlink()


def should_replace_an_older_link(sm, tmp_path):
    (tmp_path / "links").mkdir()
    (tmp_path / "links" / "foo").symlink_to(tmp_path / "old")

    assert sm.link(CONTAINER, tmp_path / "new", tmp_path / "links") is True
    assert os.readlink(tmp_path / "links" / "foo") == str(tmp_path / "new")


@pytest.mark.parametrize("container", ["/home/opencode/devbox-mac-inbox", "/workspace/code", "/workspace/other"])
def should_link_nothing_outside_workspace_code(sm, tmp_path, container):
    assert sm.link(container, tmp_path / "target", tmp_path / "links") is False
    assert not (tmp_path / "links").exists()


def archive_of(*members):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for name, kind in members:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.mode = 0o755 if kind == tarfile.DIRTYPE else 0o644
            if kind == tarfile.SYMTYPE:
                info.linkname = "/etc/passwd"
            data = b"draft\n" if kind == tarfile.REGTYPE else b""
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def should_unpack_the_scratchpad_under_the_session(sm, tmp_path):
    prefix = f"claude-501/-workspace/{SESSION}/scratchpad"
    archive = archive_of((prefix, tarfile.DIRTYPE), (f"{prefix}/notes.md", tarfile.REGTYPE))

    sm.unpack_scratchpad(archive, SESSION, tmp_path / "claude-1001" / "-workspace")

    assert (tmp_path / "claude-1001" / "-workspace" / str(SESSION) / "scratchpad" / "notes.md").read_text() == "draft\n"
    assert (tmp_path / "claude-1001").stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("member", [
    (f"claude-501/-workspace/{OTHER_SESSION}/scratchpad/notes.md", tarfile.REGTYPE),
    (f"claude-501/-workspace/{SESSION}/scratchpad/../../escape.md", tarfile.REGTYPE),
    (f"claude-501/-workspace/{SESSION}/scratchpad/link", tarfile.SYMTYPE),
])
def should_refuse_a_scratchpad_archive_holding_anything_else(sm, tmp_path, member):
    with pytest.raises(sm.MoveError):
        sm.unpack_scratchpad(archive_of(member), SESSION, tmp_path / "scratch")

    assert not (tmp_path / "scratch").exists()


def should_keep_the_plan_intact_across_json(sm, world):
    state = sm.RepoState(links=((CONTAINER, ""), ("/workspace/code/sub", "sub")), name="foo", origin="o",
                         worktree="", branch="main", head="a" * 40, snapshot="b" * 40)
    plan = sm.MovePlan(SESSION, MOVED_AT, (state,), ("/workspace/code/Desktop",), 42, True)

    assert sm.MovePlan.from_json(plan.to_json()) == plan


def should_remember_where_a_session_moved_until_cleared(sm, tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "LEASE_DIR", tmp_path / "moved")
    sm.write_lease(sm.Lease(SESSION, MOVED_AT, "devbox"))

    assert sm.read_lease(SESSION) == sm.Lease(SESSION, MOVED_AT, "devbox")
    sm.clear_lease(SESSION)
    assert sm.read_lease(SESSION) is None


@pytest.fixture
def moved_away(sm, tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "LEASE_DIR", tmp_path / "moved")
    sm.write_lease(sm.Lease(SESSION, MOVED_AT, "devbox"))


def should_warn_and_clear_the_lease_when_cl_resumes_a_moved_session_unattended(load_script, sm, moved_away, capsys):
    cl = load_script("cl")

    cl.confirm_resume_after_move(str(SESSION))

    assert "moved to the devbox on 06 Nov at 14:02" in capsys.readouterr().err
    assert sm.read_lease(SESSION) is None


def should_stop_cl_when_the_user_declines_to_fork_a_moved_session(load_script, sm, moved_away, monkeypatch):
    cl = load_script("cl")
    monkeypatch.setattr(cl.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")

    with pytest.raises(SystemExit):
        cl.confirm_resume_after_move(str(SESSION))

    assert sm.read_lease(SESSION) is not None


def should_list_only_the_records_a_live_cl_holds(registry, tmp_path):
    def record(session):
        return registry.SessionRecord(session, tmp_path, (), "work", MOVED_AT, tmux_pane="%7")
    (tmp_path / "live.json").write_text(record(SESSION).to_json())
    (tmp_path / "interrupted.json").write_text(record(OTHER_SESSION).to_json())

    with (tmp_path / "live.json").open("r") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        running = registry.running(tmp_path)

    assert [record.session_id for _path, record in running] == [SESSION]


class FakeSession:
    def __init__(self, statuses, record=None, ended=lambda: False):
        self.statuses = iter(statuses)
        self.record = record
        self.id = SESSION
        self.ended = ended

    def running(self):
        return not self.ended()

    def status(self):
        return next(self.statuses)


class FakePane:
    def __init__(self):
        self.keys = []

    def press(self, key):
        self.keys.append(key)

    def type(self, text):
        self.keys.append(f"type {text}")


def should_wait_for_three_idle_polls_in_a_row(cli):
    session = FakeSession(["busy", "idle", "busy", "idle", "idle", "idle"])
    naps = []

    assert cli.Checkpoint(session, FakePane(), naps.append).wait_until_idle(interrupt=False) is True
    assert len(naps) == 5


def should_press_escape_once_when_asked_to_interrupt(cli):
    pane = FakePane()

    cli.Checkpoint(FakeSession(["busy", "busy", "idle", "idle", "idle"]), pane, lambda _s: None).wait_until_idle(True)

    assert pane.keys == ["Escape"]


def should_report_a_session_that_ended_on_its_own(cli):
    session = FakeSession([], ended=lambda: True)

    assert cli.Checkpoint(session, FakePane(), lambda _s: None).wait_until_idle(interrupt=False) is False


def should_clear_a_draft_before_typing_exit(cli):
    pane = FakePane()
    session = FakeSession([], ended=lambda: pane.keys[-1:] == ["Enter"])

    cli.Checkpoint(session, pane, lambda _s: None).end()

    assert pane.keys == ["C-c", "type /exit", "Enter"]


def should_retry_the_hand_over_while_the_transcript_is_still_on_its_way(cli, sm):
    answers = iter([
        subprocess.CompletedProcess([], cli.TRANSCRIPT_PENDING_EXIT, b"", b"short"),
        subprocess.CompletedProcess([], 0, json.dumps({"prompt": "hello"}).encode(), b""),
    ])
    box = SimpleNamespace(call=lambda _args, _stdin: next(answers))
    synced, naps = [], []
    plan = sm.MovePlan(SESSION, MOVED_AT, (), (), 1, False)

    assert cli.hand_over(box, plan, synced.append, naps.append) == "hello"
    assert synced == [SESSION, SESSION]
    assert len(naps) == 1


def should_find_the_container_by_its_own_run_folder(cli, create_mock_bin, tmp_path):
    run_dir = tmp_path / "claude-sessions" / "c0ffee"
    inspected = [
        {"Id": "first", "Mounts": [{"Source": "/Users/me/.local/state/cl/claude-sessions/other"}]},
        {"Id": "second", "Mounts": [{"Source": "/Users/me/.local/state/cl/claude-sessions/c0ffee"}]},
    ]
    docker = create_mock_bin("docker", f"""
case "$1" in
    ps) echo first; echo second ;;
    inspect) echo '{json.dumps(inspected)}' ;;
esac""")

    assert cli.container_of(run_dir, str(docker)) == "second"


@pytest.fixture
def local_box(cli, sm, box_paths, tmp_path):
    env = {**os.environ, "CLAUDE_MOVE_PROJECTS": str(box_paths.projects), "CLAUDE_MOVE_LINKS": str(box_paths.links),
           "CLAUDE_HOME": str(box_paths.claude_home), "CLAUDE_MOVE_SCRATCH": str(box_paths.scratch)}

    class LocalBox(cli.Box):
        def call(self, args, stdin=b""):
            launch = ["--no-launch"] if args[0] == "receive" else []
            return subprocess.run([sys.executable, str(BIN_DIR / "claude-move"), "box", *args, *launch],
                                  input=stdin, capture_output=True, env=env)

        def push(self, top, sha, checkout, ref):
            sm.git(top, "push", "-q", checkout, f"{sha}:{ref}")

    return LocalBox("local")


def should_move_a_session_end_to_end(cli, sm, registry, git, world, box_paths, local_box, create_mock_bin,
                                     tmp_path, monkeypatch):
    git(world.mac, "checkout", "-q", "-b", "feature")
    dirty(git, world.mac)
    (tmp_path / "Desktop").mkdir()
    keys = tmp_path / "tmux-keys"
    tmux = create_mock_bin("tmux", f'echo "$*" >> "{keys}"')
    transcripts = tmp_path / "mac-transcripts"
    transcripts.mkdir()
    (transcripts / f"{SESSION}.jsonl").write_bytes(TRANSCRIPT)
    monkeypatch.setattr(cli, "TRANSCRIPTS", transcripts)
    monkeypatch.setattr(sm, "LEASE_DIR", tmp_path / "moved")
    mounts = (registry.Mount(world.mac, CONTAINER), registry.Mount(tmp_path / "Desktop", "/workspace/code/Desktop"))
    record = registry.SessionRecord(SESSION, world.mac, (), "work", MOVED_AT, tmux_pane="%7", mounts=mounts)
    session = FakeSession(["idle"] * 3, record, ended=lambda: keys.is_file() and "Enter" in keys.read_text())

    def sync(_session):
        box_paths.transcript(SESSION).write_bytes((transcripts / f"{SESSION}.jsonl").read_bytes())

    preparation = cli.prepare(session, local_box)
    prompt = cli.move(preparation, local_box, (str(tmux), None), now=False, sync=sync, sleep=lambda _s: None)

    assert keys.read_text().splitlines() == ["send-keys -t %7 C-c", "send-keys -t %7 -l /exit", "send-keys -t %7 Enter"]
    worktree = worktree_of(world, "feature")
    assert (worktree / "new.txt").read_text() == "new\n"
    assert (box_paths.links / "foo").resolve() == worktree.resolve()
    assert "Not on the devbox: /workspace/code/Desktop." in prompt
    assert sm.read_lease(SESSION).to == "devbox"


def should_refuse_a_session_outside_tmux_before_touching_anything(cli, registry, world, local_box):
    mounts = (registry.Mount(world.mac, CONTAINER),)
    record = registry.SessionRecord(SESSION, world.mac, (), None, MOVED_AT, mounts=mounts)

    with pytest.raises(cli.MoveError, match="outside tmux"):
        cli.prepare(FakeSession([], record), local_box)


def should_locate_checkouts_for_the_mac(run_cli, world):
    request = json.dumps([{"name": "foo", "origin": str(world.origin)}, {"name": "bar", "origin": "git@x:y/bar.git"}])

    result = run_cli("claude-move", ["box", "locate"], stdin=request,
                     env_extra={"CLAUDE_MOVE_PROJECTS": str(world.projects)})

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [str(world.box), None]


def should_exit_75_from_receive_while_the_transcript_is_missing(run_cli, sm, tmp_path):
    plan = sm.MovePlan(SESSION, MOVED_AT, (), (), 10, False)

    result = run_cli("claude-move", ["box", "receive", "--no-launch"], stdin=plan.to_json(),
                     env_extra={"CLAUDE_HOME": str(tmp_path / "empty-claude")})

    assert result.returncode == 75


def should_refuse_the_mac_half_anywhere_but_on_a_mac(run_cli):
    if sys.platform == "darwin":
        pytest.skip("the guard only shows off the Mac")

    result = run_cli("claude-move", [])

    assert result.returncode == 2
    assert "runs on the Mac" in result.stderr
