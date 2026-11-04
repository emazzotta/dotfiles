from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

SESSION = "ba40747f-3772-4931-b0e5-fc421983d509"
TRANSCRIPT = Path(".claude", "projects", "-workspace", f"{SESSION}.jsonl")
STAMP = "2026-07-16T02-42-00Z"
PUBLISHED_CHAT = f"claude-chat-{STAMP}-{SESSION}.html"
PUBLISHED_INSIGHT = f"claude-transcript-{STAMP}-{SESSION}.html"
MESSAGE = "0b6f8f9e-1d2c-4b7a-9e3f-5a6b7c8d9e0f:1"
PUBLISHED_MESSAGE = f"claude-message-{STAMP}-0b6f8f9e-1d2c-4b7a-9e3f-5a6b7c8d9e0f-1.html"
TITLE = "Fixing case-save corruption"
RENDERED = "<html>rendered page</html>"
SECRETS_FOUND = "2 potential secret(s) found"
CHAT_FINDING = "possible GitHub token in the tool Bash 2026-07-16T02:42:00Z: ghp_a1…"
INSTALL_FAILED = "claude-transcript: could not install the web-terminal's dependencies in"
RENDER_FAILED = f"claude-transcript: the web-terminal rendered nothing for {SESSION}.jsonl"
UNRESOLVED = 'Could not resolve: "markdown-it". Maybe you need to "bun install"?'
# How bun reports an uncaught error: a source excerpt, the error, its stack, then its version.
BUN_CRASH = f"""16 |   loading ??= import('markdown-it')
                          ^
error: {UNRESOLVED}
    at /web-terminal/src/client/chat/render.ts:16:22

Bun v1.4.4 (Linux arm64)"""
WEB_TERMINAL_CHECKOUTS = (
    os.environ.get("WEB_TERMINAL_DIR", ""),
    str(Path.home() / "Projects" / "private" / "web-terminal"),
    "/workspace/code/private/web-terminal",
)


@pytest.fixture
def projects(tmp_path):
    """A fake ~/.claude/projects holding one session JSONL."""
    home = tmp_path / "home"
    (home / TRANSCRIPT).parent.mkdir(parents=True)
    (home / TRANSCRIPT).write_text("{}\n")
    return home


def write_transcript(home: Path, prompt: str, reply: str) -> None:
    """Replace the session's JSONL with one prompt and its reply, as Claude Code records them."""
    records = [
        {"type": "user", "uuid": "u-1", "timestamp": "2026-07-16T02:42:00Z",
         "message": {"role": "user", "content": prompt}},
        {"type": "assistant", "uuid": "a-1", "timestamp": "2026-07-16T02:42:05Z",
         "message": {"role": "assistant", "content": [{"type": "text", "text": reply}]}},
    ]
    (home / TRANSCRIPT).write_text("".join(json.dumps(record) + "\n" for record in records))


def scripted_bun(log: Path, chat_status: int, renders: bool, installs: bool, complaint: str) -> str:
    """A bun mock: `bun install` succeeds or fails, the share script prints `complaint` to stderr and exits with `chat_status`."""
    install = "exit 0" if installs else "echo 'error: lockfile had changes, but lockfile is frozen' >&2\nexit 1"
    chat = f'if [ "$1" = install ]; then\necho "bun $* in $PWD" >> {log}\n{install}\nfi\n'
    chat += f'echo "bun $*" >> {log}\n'
    if complaint:
        chat += f"printf '%s\\n' {shlex.quote(complaint)} >&2\n"
    if chat_status == 3:
        chat += f'echo "{CHAT_FINDING}" >&2\n'
    elif renders:
        chat += f"for last; do :; done\nprintf '%s' '{RENDERED}' > \"$last\"\n"
    return chat + f"exit {chat_status}"


@pytest.fixture
def web_terminal(tmp_path):
    """A web-terminal checkout as far as the wrapper looks: its share script."""
    checkout = tmp_path / "web-terminal"
    (checkout / "scripts").mkdir(parents=True)
    (checkout / "scripts" / "share.ts").write_text("")
    return checkout


@pytest.fixture
def fresh_web_terminal(tmp_path):
    """The web-terminal at a local checkout's HEAD without node_modules, as a fresh clone has it."""
    source = next((Path(c) for c in WEB_TERMINAL_CHECKOUTS if c and (Path(c) / ".git").exists()), None)
    if source is None:
        pytest.skip("no web-terminal checkout to export")
    archive = tmp_path / "web-terminal.tar"
    checkout = tmp_path / "fresh-web-terminal"
    checkout.mkdir()
    subprocess.run(["git", "-C", str(source), "archive", "-o", str(archive), "HEAD"], check=True)
    subprocess.run(["tar", "-xf", str(archive), "-C", str(checkout)], check=True)
    return checkout


@pytest.fixture
def real_bun(monkeypatch):
    """A bun mock body that runs the real bun, installing from the owner's package cache."""
    bun = shutil.which("bun")
    if bun is None:
        pytest.skip("bun is not installed")
    cache = os.environ.get("BUN_INSTALL_CACHE_DIR", str(Path.home() / ".bun" / "install" / "cache"))
    monkeypatch.setenv("BUN_INSTALL_CACHE_DIR", cache)
    return f'exec "{bun}" "$@"'


@pytest.fixture
def publish(run_bash, tmp_path, projects, web_terminal):
    """Run claude-transcript against mocked bun, vibe-replay and fileserver.

    `listing` seeds what `fileserver list` reports. `chat_status` is the exit
    status of the web-terminal's share script (3 = possible secrets) and
    `complaint` what it prints to stderr, `installs` whether its dependencies
    install, and `scan` vibe-replay's secret verdict.
    `bun` replaces the bun mock's body. The mocks log every call to calls.log,
    and the fileserver mock keeps each uploaded file in `server`. Every run is
    titled unless `title=None`.
    """
    server = tmp_path / "server"
    server.mkdir()
    log = tmp_path / "calls.log"
    replay = tmp_path / "vibe" / "ba40747f" / "index.html"

    def _publish(args, listing="", chat_status=0, scan="No secrets detected", renders=True, title=TITLE,
                 checkout=web_terminal, installs=True, bun=None, complaint=""):
        replayer = f'echo "vibe-replay $*" >> {log}\n'
        if renders:
            replayer += (
                f"mkdir -p {replay.parent}\n"
                f"printf '%s' '{RENDERED}' > {replay}\n"
                f'echo "  OK {replay} (1.2 MB)"\n'
            )
        replayer += f'echo "  {scan}"\n'
        mocks = {
            "bun": bun or scripted_bun(log, chat_status, renders, installs, complaint),
            "vibe-replay": replayer,
            "fileserver": (
                f'echo "fileserver $*" >> {log}\n'
                f'[ "$1" = "list" ] && printf "%s\\n" {listing!r}\n'
                f'[ "$1" = "upload" ] && cp "$2" {server}/\n'
                "exit 0"
            ),
        }
        result = run_bash(
            "claude-transcript",
            (["--title", title] if title is not None else []) + args,
            mock_bins=mocks, isolate_path=True,
            env_extra={
                "HOME": str(projects),
                "WEB_TERMINAL_DIR": str(checkout),
                "FILESERVER_PUBLIC_BASE": "https://example.test/share",
            },
        )
        result.calls = log.read_text() if log.is_file() else ""
        result.server = server
        result.published = result.stdout.strip().rsplit("/", 1)[-1]
        result.jsonl = projects / ".claude" / "projects" / "-workspace" / f"{SESSION}.jsonl"
        return result

    return _publish


class TestNameReuse:
    def should_reuse_published_name_when_session_is_already_online(self, publish):
        result = publish([SESSION], listing=f"-rw-r--r-- 1 root root 900 Jul 16 02:42 {PUBLISHED_CHAT}")

        assert result.returncode == 0
        assert result.stdout.strip() == f"https://example.test/share/{PUBLISHED_CHAT}"
        assert (result.server / PUBLISHED_CHAT).is_file()

    def should_keep_the_original_date_in_the_reused_name(self, publish):
        result = publish([SESSION], listing=PUBLISHED_CHAT)

        assert STAMP in result.stdout

    def should_say_it_is_republishing_when_reusing(self, publish):
        result = publish([SESSION], listing=PUBLISHED_CHAT)

        assert "re-publishing over" in result.stderr

    def should_mint_a_fresh_name_when_session_is_not_online(self, publish):
        result = publish([SESSION], listing="claude-chat-2026-07-01T00-00-00Z-other.html")

        assert result.returncode == 0
        assert result.published.startswith("claude-chat-")
        assert result.published.endswith(f"-{SESSION}.html")
        assert result.published != PUBLISHED_CHAT

    def should_mint_a_fresh_name_when_server_lists_nothing(self, publish):
        result = publish([SESSION], listing="")

        assert result.returncode == 0
        assert result.published.endswith(f"-{SESSION}.html")

    def should_not_match_a_different_session_with_a_shared_prefix(self, publish):
        other = f"claude-chat-{STAMP}-{SESSION}-extra.html"

        result = publish([SESSION], listing=other)

        assert other not in result.stdout

    def should_reuse_the_insight_name_for_an_insight_republish(self, publish):
        result = publish([SESSION, "--insight"], listing=f"{PUBLISHED_CHAT}\n{PUBLISHED_INSIGHT}")

        assert result.published == PUBLISHED_INSIGHT

    def should_not_overwrite_the_insight_page_with_the_chat_view(self, publish):
        result = publish([SESSION], listing=PUBLISHED_INSIGHT)

        assert result.returncode == 0
        assert result.published.startswith("claude-chat-")


class TestChatView:
    def should_render_the_session_with_the_web_terminals_share_script(self, publish, web_terminal):
        result = publish([SESSION])

        assert f"bun {web_terminal}/scripts/share.ts --title {TITLE}" in result.calls
        assert f"{SESSION}.jsonl" in result.calls
        assert "vibe-replay" not in result.calls

    def should_upload_the_page_the_web_terminal_wrote(self, publish):
        result = publish([SESSION])

        assert (result.server / result.published).read_text() == RENDERED

    def should_not_publish_when_the_web_terminal_flags_secrets(self, publish):
        result = publish([SESSION], chat_status=3)

        assert result.returncode == 1
        assert CHAT_FINDING in result.stderr
        assert "not publishing" in result.stderr
        assert "fileserver" not in result.calls

    def should_pass_allow_secrets_on_to_the_web_terminal(self, publish):
        result = publish([SESSION, "--allow-secrets"])

        assert "--allow-secrets" in result.calls

    def should_fail_when_the_web_terminal_writes_no_page(self, publish):
        result = publish([SESSION], renders=False)

        assert result.returncode == 1
        assert result.stderr.strip().splitlines()[-1] == RENDER_FAILED
        assert "fileserver" not in result.calls

    # The share sheet shows only the last line of stderr, so that line has to say why.
    def should_end_with_bun_s_error_when_the_share_script_crashes(self, publish):
        result = publish([SESSION], chat_status=1, renders=False, complaint=BUN_CRASH)

        assert result.returncode == 1
        assert BUN_CRASH in result.stderr
        assert result.stderr.strip().splitlines()[-1] == f"{RENDER_FAILED}: {UNRESOLVED}"
        assert "fileserver" not in result.calls

    def should_end_with_the_share_script_s_own_error_when_it_gives_up(self, publish):
        result = publish([SESSION, "--message", MESSAGE], chat_status=1, renders=False,
                         complaint=f"no message {MESSAGE} in {SESSION}.jsonl")

        assert result.returncode == 1
        assert result.stderr.strip().splitlines()[-1] == f"{RENDER_FAILED}: no message {MESSAGE} in {SESSION}.jsonl"

    def should_fail_when_the_web_terminal_checkout_is_missing(self, publish, tmp_path):
        result = publish([SESSION], checkout=tmp_path / "nowhere")

        assert result.returncode == 1
        assert "no web-terminal checkout" in result.stderr
        assert "bun" not in result.calls

    def should_install_the_checkouts_dependencies_before_rendering(self, publish, web_terminal):
        result = publish([SESSION])

        install, render = result.calls.splitlines()[:2]
        assert install == f"bun install --frozen-lockfile in {web_terminal}"
        assert render.startswith(f"bun {web_terminal}/scripts/share.ts ")

    def should_end_with_why_and_publish_nothing_when_the_dependencies_do_not_install(self, publish, web_terminal):
        result = publish([SESSION], installs=False)

        assert result.returncode == 1
        assert result.stderr.strip().splitlines()[-1] == (
            f"{INSTALL_FAILED} {web_terminal}: lockfile had changes, but lockfile is frozen"
        )
        assert "scripts/share.ts" not in result.calls
        assert "fileserver" not in result.calls


@pytest.mark.slow
class TestWithTheRealWebTerminal:
    """The real bun and share script, from a web-terminal checkout whose dependencies were never installed."""

    def should_publish_the_conversation(self, publish, projects, fresh_web_terminal, real_bun):
        write_transcript(projects, "Share this conversation again", "The page renders.")

        result = publish([SESSION], checkout=fresh_web_terminal, bun=real_bun)

        assert result.returncode == 0, result.stderr
        assert "Share this conversation again" in (result.server / result.published).read_text()

    def should_refuse_a_conversation_that_shows_a_credential(self, publish, projects, fresh_web_terminal, real_bun):
        write_transcript(projects, "Deploy it", "export DEPLOY_TOKEN=" + "4f9c2a7e" * 2)

        result = publish([SESSION], checkout=fresh_web_terminal, bun=real_bun)

        assert result.returncode == 1
        assert "possible secret assignment in the reply" in result.stderr
        assert "not publishing" in result.stderr
        assert not list(result.server.iterdir())

    def should_end_with_bun_s_error_when_a_dependency_is_missing(self, publish, projects, fresh_web_terminal,
                                                                real_bun):
        write_transcript(projects, "Share this", "It renders markdown.")
        skip_install = 'if [ "$1" = install ]; then exit 0; fi\n'

        result = publish([SESSION], checkout=fresh_web_terminal, bun=skip_install + real_bun)

        assert result.returncode == 1
        last = result.stderr.strip().splitlines()[-1]
        assert last.startswith(f"{RENDER_FAILED}: Could not resolve: ")
        assert "Bun v" not in last


class TestMessageView:
    def should_render_only_the_message_with_the_web_terminal(self, publish):
        result = publish([SESSION, "--message", MESSAGE])

        assert f"--item {MESSAGE}" in result.calls
        assert result.published.startswith("claude-message-")
        assert result.published.endswith("-0b6f8f9e-1d2c-4b7a-9e3f-5a6b7c8d9e0f-1.html")

    def should_reuse_the_name_of_an_earlier_share_of_the_message(self, publish):
        result = publish([SESSION, "--message", MESSAGE], listing=f"{PUBLISHED_CHAT}\n{PUBLISHED_MESSAGE}")

        assert result.published == PUBLISHED_MESSAGE

    @pytest.mark.parametrize("item", ["", "a b", "x;rm -rf /", "../up"])
    def should_reject_a_message_id_that_is_not_one(self, publish, item):
        result = publish([SESSION, "--message", item])

        assert result.returncode == 2
        assert "bun" not in result.calls

    def should_refuse_to_mix_a_message_with_the_insight_view(self, publish):
        result = publish([SESSION, "--message", MESSAGE, "--insight"])

        assert result.returncode == 2
        assert "do not mix" in result.stderr


class TestTextView:
    def should_render_the_conversation_without_tool_steps_under_its_own_name(self, publish):
        result = publish([SESSION, "--text-only"])

        assert "--text-only" in result.calls
        assert result.published.startswith("claude-text-")
        assert (result.server / result.published).read_text() == RENDERED

    def should_reuse_the_name_of_an_earlier_text_only_share(self, publish):
        published = f"claude-text-{STAMP}-{SESSION}.html"

        result = publish([SESSION, "--text-only"], listing=f"{PUBLISHED_CHAT}\n{published}")

        assert result.published == published

    def should_not_overwrite_the_text_only_page_with_the_full_chat(self, publish):
        result = publish([SESSION], listing=f"claude-text-{STAMP}-{SESSION}.html")

        assert result.published.startswith("claude-chat-")

    @pytest.mark.parametrize("other", [["--insight"], ["--message", MESSAGE]])
    def should_refuse_to_mix_with_another_view(self, publish, other):
        result = publish([SESSION, "--text-only", *other])

        assert result.returncode == 2
        assert "do not mix" in result.stderr


class TestInsightView:
    def should_upload_the_replay_the_renderer_generated(self, publish):
        result = publish([SESSION, "--insight"])

        assert (result.server / result.published).read_text() == RENDERED
        assert result.published.startswith("claude-transcript-")

    def should_render_the_session_jsonl_the_id_points_at(self, publish):
        result = publish([SESSION, "--insight"])

        assert "vibe-replay --session" in result.calls
        assert f"{SESSION}.jsonl" in result.calls
        assert "bun " not in result.calls

    def should_pass_the_title_through_to_the_renderer(self, publish):
        result = publish([SESSION, "--insight"])

        assert f"--title {TITLE}" in result.calls

    def should_fail_when_the_renderer_writes_no_replay(self, publish):
        result = publish([SESSION, "--insight"], renders=False)

        assert result.returncode == 1
        assert "rendered nothing" in result.stderr
        assert "fileserver upload" not in result.calls

    def should_not_publish_when_the_render_flags_secrets(self, publish):
        result = publish([SESSION, "--insight"], scan=SECRETS_FOUND)

        assert result.returncode == 1
        assert "not publishing" in result.stderr
        assert "fileserver" not in result.calls

    def should_publish_flagged_secrets_when_explicitly_allowed(self, publish):
        result = publish([SESSION, "--insight", "--allow-secrets"], scan=SECRETS_FOUND)

        assert result.returncode == 0
        assert "fileserver upload" in result.calls


class TestArguments:
    def should_leave_the_title_to_the_session_when_none_is_given(self, publish, web_terminal):
        result = publish([SESSION], title=None)

        assert result.returncode == 0
        assert f"bun {web_terminal}/scripts/share.ts {result.jsonl}" in result.calls
        assert "--title" not in result.calls

    def should_require_a_title_for_the_insight_view(self, publish):
        result = publish([SESSION, "--insight"], title=None)

        assert result.returncode == 2
        assert "--insight needs --title" in result.stderr
        assert "vibe-replay" not in result.calls

    def should_reject_a_title_without_a_value(self, publish):
        result = publish(["--title"], title=None)

        assert result.returncode == 2
        assert "--title needs a value" in result.stderr

    def should_print_usage_and_exit_zero_for_help(self, publish):
        result = publish(["--help"], title=None)

        assert result.returncode == 0
        assert "Usage: claude-transcript" in result.stdout

    def should_exit_two_when_no_session_given(self, publish):
        result = publish([])

        assert result.returncode == 2

    def should_reject_an_unknown_option(self, publish):
        result = publish(["--nope"])

        assert result.returncode == 2
        assert "unknown option" in result.stderr

    def should_fail_when_session_has_no_jsonl(self, publish):
        result = publish(["deadbeef-0000-0000-0000-000000000000"])

        assert result.returncode == 1
        assert "no transcript for session" in result.stderr
