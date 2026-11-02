import pytest

GITLAB_HOST = "gitlab.example.com"


@pytest.fixture
def forge_token(run_bash, tmp_path):
    envify_calls = tmp_path / "envify.calls"

    def _run(host, gh_logged_in=False, glab_token="", tokens_file=None, env=None, envify_loads=True):
        if tokens_file is not None:
            config = tmp_path / ".config" / "repos" / "tokens"
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(tokens_file)
        mocks = {
            "gh": f'[ "$1 $2" = "auth token" ] && exit {0 if gh_logged_in else 1}',
            "glab": f'[ "$1 $2 $3" = "config get token" ] && printf "%s" "{glab_token}"',
            "envify": (f'printf "%s\\n" "$*" >> "{envify_calls}"\n'
                       + ('for name in "$@"; do export "$name=token-of-$name"; done' if envify_loads
                          else 'echo "Approve on your phone: https://unlock.example/approve" >&2')),
        }
        environment = {"HOME": str(tmp_path), "GH_TOKEN": "", "GITHUB_TOKEN": "", "GITLAB_TOKEN": "", **(env or {})}
        result = run_bash("keyguard-forge-token", [host], env_extra=environment, mock_bins=mocks, isolate_path=True)
        asked = envify_calls.read_text().splitlines() if envify_calls.exists() else []
        return result, asked
    return _run


def should_load_github_token_for_gh_when_gh_has_no_login(forge_token):
    result, asked = forge_token("github.com")

    assert (result.returncode, result.stdout, asked) == (0, "GH_TOKEN=token-of-GITHUB_TOKEN\n", ["GITHUB_TOKEN"])


def should_load_the_secret_the_tokens_file_names_for_a_gitlab_host_for_glab(forge_token):
    result, asked = forge_token(GITLAB_HOST, tokens_file=f"# host secret\n{GITLAB_HOST} EXAMPLE_GITLAB_TOKEN\n")

    assert result.stdout == "GITLAB_TOKEN=token-of-EXAMPLE_GITLAB_TOKEN\n"
    assert asked == ["EXAMPLE_GITLAB_TOKEN"]


@pytest.mark.parametrize("host, login", [
    ("github.com", {"gh_logged_in": True}),
    ("github.com", {"env": {"GH_TOKEN": "set"}}),
    ("github.com", {"env": {"GITHUB_TOKEN": "set"}}),
    (GITLAB_HOST, {"glab_token": "glpat-from-config"}),
    (GITLAB_HOST, {"env": {"GITLAB_TOKEN": "set"}}),
])
def should_print_nothing_and_ask_nothing_when_the_cli_already_has_a_token(forge_token, host, login):
    result, asked = forge_token(host, tokens_file=f"{GITLAB_HOST} EXAMPLE_GITLAB_TOKEN\n", **login)

    assert (result.returncode, result.stdout, asked) == (0, "", [])


def should_print_nothing_and_ask_nothing_for_a_host_without_a_known_secret(forge_token):
    result, asked = forge_token("gitlab.other.example", tokens_file=f"{GITLAB_HOST} EXAMPLE_GITLAB_TOKEN\n")

    assert (result.returncode, result.stdout, asked) == (0, "", [])


def should_fail_with_what_envify_said_when_the_approval_brings_no_token(forge_token):
    result, _ = forge_token("github.com", envify_loads=False)

    assert (result.returncode, result.stdout) == (1, "")
    assert "Approve on your phone" in result.stderr
    assert "GITHUB_TOKEN came back empty" in result.stderr


def should_refuse_a_secret_name_that_is_no_shell_variable_before_asking(forge_token):
    result, asked = forge_token(GITLAB_HOST, tokens_file=f"{GITLAB_HOST} not-a-name\n")

    assert (result.returncode, asked) == (2, [])
    assert "not-a-name" in result.stderr


@pytest.mark.parametrize("args, code", [("--help", 0), ("", 2)])
def should_answer_help_and_a_missing_host_without_asking(forge_token, args, code):
    result, asked = forge_token(args)

    assert (result.returncode, asked) == (code, [])
