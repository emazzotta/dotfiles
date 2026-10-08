import os

import pytest

from bin.tests.conftest import WORKTREES, commit_file

JAVA = "25.0.1-tem"
INSTALL = "clean install -DskipTests"
BUILD = "-DskipTests clean install"
RUN = "exec:exec -Prun-leonardo -DskipTests -pl leonardo-leonardo"


def real(path):
    return os.path.realpath(path)


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home"
    (home / ".sdkman" / "candidates" / "java" / JAVA).mkdir(parents=True)
    return home


@pytest.fixture
def clone(tmp_path, git, home):
    def _clone(name, *files):
        origin = tmp_path / "origins" / f"{name}.git"
        git(tmp_path, "init", "--bare", str(origin))
        checkout = home / "Projects" / "leo-productions" / name
        git(tmp_path, "clone", str(origin), str(checkout))
        for file in files:
            (checkout / file).parent.mkdir(parents=True, exist_ok=True)
            (checkout / file).write_text("<project/>")
            git(checkout, "add", file)
        git(checkout, "commit", "--allow-empty", "-m", "Initial commit")
        git(checkout, "push", "origin", "main")
        git(checkout, "remote", "set-head", "origin", "main")
        return checkout
    return _clone


@pytest.fixture
def leonardo(clone):
    return clone("leonardo", "pom.xml", "leonardo-leonardo/pom.xml")


@pytest.fixture
def worktree(run_cli, git_env, leonardo):
    def _worktree(branch):
        result = run_cli("git-wt", ["add", branch], env_extra=git_env, cwd=leonardo)
        assert result.returncode == 0, result.stderr
        return leonardo / WORKTREES / branch
    return _worktree


@pytest.fixture
def push_from_elsewhere(tmp_path, git, leonardo):
    def _push(branch):
        elsewhere = tmp_path / "elsewhere"
        git(tmp_path, "clone", str(tmp_path / "origins" / "leonardo.git"), str(elsewhere))
        git(elsewhere, "switch", "-c", branch)
        commit_file(git, elsewhere, "work.txt", "work")
        git(elsewhere, "push", "origin", branch)
    return _push


@pytest.fixture
def mvn_log(tmp_path):
    return tmp_path / "mvn_calls"


@pytest.fixture
def mvn_calls(mvn_log):
    def _calls():
        if not mvn_log.exists():
            return []
        lines = mvn_log.read_text().splitlines()
        return [(real(cwd), args) for cwd, args in (line.split("\t") for line in lines)]
    return _calls


@pytest.fixture
def leorun(run_cli, git_env, home, tmp_path, mvn_log):
    def _leorun(*args, cwd=None):
        env = {**git_env, "HOME": str(home),
               "SDKMAN_CANDIDATES_DIR": str(home / ".sdkman" / "candidates")}
        mocks = {"mvn": f'printf "%s\\t%s\\n" "$PWD" "$*" >> "{mvn_log}"', "sdk": ":"}
        return run_cli("leorun", list(args), env_extra=env, mock_bins=mocks, cwd=cwd or tmp_path)
    return _leorun


def built_and_ran(checkout):
    return [(real(checkout), BUILD), (real(checkout), RUN)]


class TestModes:
    @pytest.mark.parametrize("flags, expected", [
        ([], [BUILD, RUN]),
        (["--fast"], [RUN]),
        (["--quick"], ["-DskipTests compile", RUN]),
    ])
    def should_build_as_the_mode_asks_before_running_the_main_checkout(
            self, leorun, mvn_calls, leonardo, flags, expected):
        result = leorun(*flags)

        assert result.returncode == 0, result.stderr
        assert mvn_calls() == [(real(leonardo), args) for args in expected]

    def should_install_dependencies_from_the_projects_directory_before_building(
            self, leorun, mvn_calls, clone, leonardo):
        dependency = clone("updater")

        result = leorun("-i", "updater")

        assert result.returncode == 0, result.stderr
        assert mvn_calls() == [(real(dependency), INSTALL)] + built_and_ran(leonardo)


class TestCheckout:
    def should_run_the_main_checkout_when_called_outside_a_leonardo_checkout(
            self, leorun, mvn_calls, leonardo, worktree):
        worktree("feature")

        result = leorun()

        assert result.returncode == 0, result.stderr
        assert mvn_calls() == built_and_ran(leonardo)

    def should_run_the_worktree_it_is_called_from(self, leorun, mvn_calls, worktree):
        checkout = worktree("feature")

        result = leorun(cwd=checkout / "leonardo-leonardo")

        assert result.returncode == 0, result.stderr
        assert mvn_calls() == built_and_ran(checkout)

    def should_run_the_worktree_holding_the_given_branch(self, leorun, mvn_calls, leonardo, worktree):
        checkout = worktree("feature")

        result = leorun("--fast", "feature", cwd=leonardo)

        assert result.returncode == 0, result.stderr
        assert mvn_calls() == [(real(checkout), RUN)]

    def should_run_the_worktree_given_by_its_directory_name(self, leorun, mvn_calls, git, leonardo):
        checkout = leonardo / WORKTREES / "focus"
        git(leonardo, "worktree", "add", "-b", "focus-branch", str(checkout))

        result = leorun("focus")

        assert result.returncode == 0, result.stderr
        assert mvn_calls() == built_and_ran(checkout)

    def should_create_the_worktree_for_a_local_branch_no_worktree_holds(
            self, leorun, mvn_calls, git, leonardo):
        git(leonardo, "branch", "feature")

        result = leorun("feature")

        checkout = leonardo / WORKTREES / "feature"
        assert result.returncode == 0, result.stderr
        assert git(checkout, "rev-parse", "--abbrev-ref", "HEAD") == "feature"
        assert mvn_calls() == built_and_ran(checkout)

    def should_fetch_and_track_a_branch_pushed_to_origin_since_the_last_fetch(
            self, leorun, mvn_calls, git, leonardo, push_from_elsewhere):
        push_from_elsewhere("colleague")

        result = leorun("colleague")

        checkout = leonardo / WORKTREES / "colleague"
        assert result.returncode == 0, result.stderr
        assert (checkout / "work.txt").exists()
        assert git(leonardo, "for-each-ref", "--format=%(upstream:short)",
                   "refs/heads/colleague") == "origin/colleague"
        assert mvn_calls() == built_and_ran(checkout)

    def should_refuse_a_branch_that_exists_nowhere_without_creating_it(
            self, leorun, mvn_calls, git, leonardo):
        result = leorun("typo")

        assert result.returncode == 1
        assert "typo" in result.stderr
        assert mvn_calls() == []
        assert git(leonardo, "branch", "--list", "typo") == ""
        assert not (leonardo / WORKTREES / "typo").exists()

    def should_install_dependencies_beside_the_main_checkout_when_running_a_worktree(
            self, leorun, mvn_calls, clone, worktree):
        checkout = worktree("feature")
        dependency = clone("updater")

        result = leorun("-i", "updater", "feature")

        assert result.returncode == 0, result.stderr
        assert mvn_calls() == [(real(dependency), INSTALL)] + built_and_ran(checkout)

    def should_pass_the_maven_settings_of_the_worktree_it_runs(self, leorun, mvn_calls, worktree):
        checkout = worktree("feature")
        settings = checkout / "commons" / "configs" / "maven_settings.xml"
        settings.parent.mkdir(parents=True)
        settings.write_text("<settings/>")

        result = leorun("--fast", "feature")

        assert result.returncode == 0, result.stderr
        assert mvn_calls() == [(real(checkout), f"{RUN} -s commons/configs/maven_settings.xml")]

    def should_reject_a_second_branch(self, leorun, mvn_calls, worktree):
        worktree("feature")

        result = leorun("feature", "main")

        assert result.returncode == 1
        assert mvn_calls() == []


class TestCompletion:
    def should_offer_local_and_origin_branches_and_worktree_directories(
            self, leorun, git, leonardo, worktree, push_from_elsewhere):
        worktree("feature")
        git(leonardo, "worktree", "add", "-b", "focus-branch", str(leonardo / WORKTREES / "focus"))
        push_from_elsewhere("colleague")
        git(leonardo, "fetch", "origin")

        result = leorun("--complete")

        assert result.returncode == 0, result.stderr
        assert sorted(result.stdout.split()) == ["colleague", "feature", "focus", "focus-branch", "main"]

    def should_offer_branches_after_the_install_argument(self, leorun, worktree):
        worktree("feature")

        result = leorun("--complete", "-i", "updater", "--quick")

        assert result.returncode == 0, result.stderr
        assert "feature" in result.stdout.split()

    @pytest.mark.parametrize("typed", [["-i"], ["--fast", "feature"]])
    def should_offer_nothing_where_no_branch_fits(self, leorun, worktree, typed):
        worktree("feature")

        result = leorun("--complete", *typed)

        assert result.returncode == 0, result.stderr
        assert result.stdout == ""
