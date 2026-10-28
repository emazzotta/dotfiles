import os
import subprocess

import pytest

from bin.tests.conftest import BIN_DIR, requires_tool

FUNCTIONS = BIN_DIR.parent / "bash" / ".bashrc.d" / "20-functions.sh"
SHELLS = {"bash": ["bash"], "zsh": ["zsh", "-f"]}
REPOS = ("private/dotfiles", "private/docker-openssl", "work/api", "work/playground/infra-ops")
ALIASES = "# <name> <path relative to $WDIR>\nio work/playground/infra-ops\n"


@pytest.fixture
def wdir(tmp_path):
    root = tmp_path / "zz" / "Projects"
    for repo in REPOS:
        (root / repo).mkdir(parents=True)
    return root


@pytest.fixture
def env(tmp_path, wdir):
    aliases_dir = tmp_path / "aliases"
    aliases_dir.mkdir()
    (aliases_dir / "repo-aliases").write_text(ALIASES)
    return {"WDIR": str(wdir), "CUSTOM_BIN_DIR": str(aliases_dir)}


class TestRepo:
    def should_print_the_target_of_an_exact_alias_name(self, run_cli, env, wdir):
        result = run_cli("repo", ["io"], env_extra=env)

        assert result.returncode == 0, result.stderr
        assert result.stdout == f"{wdir / 'work/playground/infra-ops'}\n"

    @requires_tool("fzf")
    @pytest.mark.parametrize("query, expected", [
        ("infra-o", "work/playground/infra-ops"),
        ("docker-o", "private/docker-openssl"),
        ("work api", "work/api"),
    ])
    def should_print_the_best_fuzzy_match_among_repos_and_alias_targets(
            self, run_cli, env, wdir, query, expected):
        result = run_cli("repo", query.split(), env_extra=env)

        assert result.stdout == f"{wdir / expected}\n"

    @requires_tool("fzf")
    def should_not_match_the_path_above_wdir(self, run_cli, env, wdir):
        result = run_cli("repo", ["zz"], env_extra=env)

        assert result.stdout == f"{wdir}\n"

    def should_print_wdir_without_a_query(self, run_cli, env, wdir):
        result = run_cli("repo", env_extra=env)

        assert result.stdout == f"{wdir}\n"

    @requires_tool("fzf")
    def should_fuzzy_match_repos_without_an_alias_file(self, run_cli, env, wdir, tmp_path):
        result = run_cli("repo", ["docker-o"],
                         env_extra={**env, "CUSTOM_BIN_DIR": str(tmp_path / "missing")})

        assert result.stdout == f"{wdir / 'private/docker-openssl'}\n"

    def should_print_usage_for_help(self, run_cli, env):
        result = run_cli("repo", ["--help"], env_extra=env)

        assert result.returncode == 0
        assert result.stdout.startswith("usage: repo")


@pytest.fixture(params=["bash", pytest.param("zsh", marks=requires_tool("zsh"))])
def g(request, tmp_path):
    def _g(env, *args):
        script = f'source "{FUNCTIONS}"; g {" ".join(args)}; pwd'
        inherited = {key: value for key, value in os.environ.items() if key != "WDIR"}
        full_env = {**inherited, **env, "PATH": f"{BIN_DIR}:{os.environ['PATH']}"}
        return subprocess.run([*SHELLS[request.param], "-c", script],
                              capture_output=True, text=True, cwd=tmp_path, env=full_env)
    return _g


class TestG:
    def should_change_into_the_repo_that_repo_prints(self, g, env, wdir):
        result = g(env, "io")

        assert result.stdout.splitlines()[-1] == str(wdir / "work/playground/infra-ops")

    def should_stay_in_the_current_directory_when_repo_fails(self, g, env, tmp_path):
        without_wdir = {key: value for key, value in env.items() if key != "WDIR"}

        result = g(without_wdir, "io")

        assert result.stdout.splitlines()[-1] == str(tmp_path)
