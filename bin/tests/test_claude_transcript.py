import pytest

SESSION = "ba40747f-3772-4931-b0e5-fc421983d509"
PUBLISHED = f"claude-transcript-2026-07-16T02-42-00Z-{SESSION}.html"
TITLE = "Fixing case-save corruption"
RENDERED = "<html>rendered replay</html>"
SECRETS_FOUND = "2 potential secret(s) found"


@pytest.fixture
def projects(tmp_path):
    """A fake ~/.claude/projects holding one session JSONL."""
    project = tmp_path / "home" / ".claude" / "projects" / "-workspace"
    project.mkdir(parents=True)
    (project / f"{SESSION}.jsonl").write_text("{}\n")
    return tmp_path / "home"


@pytest.fixture
def publish(run_bash, tmp_path, projects):
    """Run claude-transcript against mocked vibe-replay/fileserver tools.

    `listing` seeds what `fileserver list` reports and `scan` the renderer's
    secret verdict; the mocks log every call to calls.log so tests can assert on
    the name that was uploaded. Every run is titled unless `title=None`, because
    the renderer turns interactive without one.
    """
    staging = tmp_path / "staging"
    log = tmp_path / "calls.log"
    replay = tmp_path / "vibe" / "ba40747f" / "index.html"

    def _publish(args, listing="", scan="No secrets detected", renders=True, title=TITLE):
        renderer = f'echo "vibe-replay $*" >> {log}\n'
        if renders:
            renderer += (
                f"mkdir -p {replay.parent}\n"
                f"printf '%s' '{RENDERED}' > {replay}\n"
                f'echo "  OK {replay} (1.2 MB)"\n'
            )
        renderer += f'echo "  {scan}"\n'
        mocks = {
            "vibe-replay": renderer,
            "fileserver": (
                f'echo "fileserver $*" >> {log}\n'
                f'[ "$1" = "list" ] && printf "%s\\n" {listing!r}\n'
                "exit 0"
            ),
            "envify": "true",
        }
        result = run_bash(
            "claude-transcript",
            (["--title", title] if title is not None else []) + args,
            mock_bins=mocks, isolate_path=True,
            env_extra={
                "HOME": str(projects),
                "FILESERVER_BRIDGE_STAGING": str(staging),
                "FILESERVER_PUBLIC_BASE": "https://example.test/downloads",
                "MAC_BRIDGE_TOKEN": "test-token",
            },
        )
        result.calls = log.read_text() if log.is_file() else ""
        result.staging = staging
        return result

    return _publish


class TestNameReuse:
    def should_reuse_published_name_when_session_is_already_online(self, publish):
        result = publish([SESSION], listing=f"-rw-r--r-- 1 root root 900 Jul 16 02:42 {PUBLISHED}")

        assert result.returncode == 0
        assert result.stdout.strip() == f"https://example.test/downloads/{PUBLISHED}"
        assert "fileserver upload" in result.calls
        assert PUBLISHED in result.calls

    def should_keep_the_original_date_in_the_reused_name(self, publish):
        result = publish([SESSION], listing=PUBLISHED)

        assert "2026-07-16T02-42-00Z" in result.stdout

    def should_say_it_is_republishing_when_reusing(self, publish):
        result = publish([SESSION], listing=PUBLISHED)

        assert "re-publishing over" in result.stderr

    def should_mint_a_fresh_name_when_session_is_not_online(self, publish):
        result = publish([SESSION], listing="claude-transcript-2026-07-01T00-00-00Z-other.html")

        assert result.returncode == 0
        assert result.stdout.strip().endswith(f"-{SESSION}.html")
        assert PUBLISHED not in result.stdout

    def should_mint_a_fresh_name_when_server_lists_nothing(self, publish):
        result = publish([SESSION], listing="")

        assert result.returncode == 0
        assert result.stdout.strip().endswith(f"-{SESSION}.html")

    def should_not_match_a_different_session_with_a_shared_prefix(self, publish):
        other = f"claude-transcript-2026-07-16T02-42-00Z-{SESSION}-extra.html"

        result = publish([SESSION], listing=other)

        assert other not in result.stdout


class TestRendering:
    def should_stage_the_replay_the_renderer_generated(self, publish):
        result = publish([SESSION])

        staged = result.staging / result.stdout.strip().rsplit("/", 1)[-1]
        assert staged.read_text() == RENDERED

    def should_render_the_session_jsonl_the_id_points_at(self, publish):
        result = publish([SESSION])

        assert f"{SESSION}.jsonl" in result.calls

    def should_fail_when_the_renderer_writes_no_replay(self, publish):
        result = publish([SESSION], renders=False)

        assert result.returncode == 1
        assert "rendered nothing" in result.stderr
        assert "fileserver upload" not in result.calls


class TestSecrets:
    def should_not_publish_when_the_render_flags_secrets(self, publish):
        result = publish([SESSION], scan=SECRETS_FOUND)

        assert result.returncode == 1
        assert "not publishing" in result.stderr
        assert "fileserver upload" not in result.calls

    def should_publish_flagged_secrets_when_explicitly_allowed(self, publish):
        result = publish([SESSION, "--allow-secrets"], scan=SECRETS_FOUND)

        assert result.returncode == 0
        assert "fileserver upload" in result.calls


class TestTitle:
    def should_pass_the_title_through_to_the_renderer(self, publish):
        result = publish([SESSION])

        assert f"--title {TITLE}" in result.calls

    def should_require_a_title(self, publish):
        result = publish([SESSION], title=None)

        assert result.returncode == 2
        assert "--title is required" in result.stderr

    def should_reject_a_title_without_a_value(self, publish):
        result = publish(["--title"], title=None)

        assert result.returncode == 2
        assert "--title needs a value" in result.stderr


class TestArguments:
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
