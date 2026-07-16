import pytest

SESSION = "ba40747f-3772-4931-b0e5-fc421983d509"
PUBLISHED = f"claude-transcript-2026-07-16T02-42-00Z-{SESSION}.html"


@pytest.fixture
def projects(tmp_path):
    """A fake ~/.claude/projects holding one session JSONL."""
    project = tmp_path / "home" / ".claude" / "projects" / "-workspace"
    project.mkdir(parents=True)
    (project / f"{SESSION}.jsonl").write_text("{}\n")
    return tmp_path / "home"


@pytest.fixture
def publish(run_bash, tmp_path, projects):
    """Run claude-transcript against mocked uvx/fileserver/theme/title tools.

    `listing` seeds what `fileserver list` reports; the mocks log every call to
    calls.log so tests can assert on the name that was uploaded.
    """
    staging = tmp_path / "staging"
    log = tmp_path / "calls.log"

    def _publish(args, listing=""):
        mocks = {
            "uvx": 'printf "<head><title>gen</title></head>" > "${@: -1}"',
            "librechat-transcript-theme": f'echo "theme $*" >> {log}',
            "transcript-title": f'echo "title $*" >> {log}',
            "fileserver": (
                f'echo "fileserver $*" >> {log}\n'
                f'[ "$1" = "list" ] && printf "%s\\n" {listing!r}\n'
                "exit 0"
            ),
            "envify": "true",
        }
        result = run_bash(
            "claude-transcript", args, mock_bins=mocks, isolate_path=True,
            env_extra={
                "HOME": str(projects),
                "FILESERVER_BRIDGE_STAGING": str(staging),
                "FILESERVER_PUBLIC_BASE": "https://example.test/downloads",
                "MAC_BRIDGE_TOKEN": "test-token",
            },
        )
        result.calls = log.read_text() if log.is_file() else ""
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


class TestTitle:
    def should_pass_the_title_through_to_transcript_title(self, publish):
        result = publish(["--title", "Fixing case-save corruption", SESSION])

        assert "title " in result.calls
        assert "Fixing case-save corruption" in result.calls

    def should_skip_retitling_when_no_title_given(self, publish):
        result = publish([SESSION])

        assert "title " not in result.calls

    def should_reject_a_title_without_a_value(self, publish):
        result = publish(["--title"])

        assert result.returncode == 2
        assert "--title needs a value" in result.stderr


class TestArguments:
    def should_print_usage_and_exit_zero_for_help(self, publish):
        result = publish(["--help"])

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
