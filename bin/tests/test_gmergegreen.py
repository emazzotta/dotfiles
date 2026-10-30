import json

import pytest

GITHUB_REMOTE = "git@github.com:owner/repo.git"
GITLAB_REMOTE = "git@gitlab.example.com:group/project.git"
GITLAB_PROJECT_PATH = "projects/group%2Fproject"


class FakeCli:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, args):
        command = " ".join(args)
        self.calls.append(command)
        for fragment, output in self.responses.items():
            if fragment in command:
                if isinstance(output, Exception):
                    raise output
                return output
        raise AssertionError(f"unexpected call: {command}")


def check_run(conclusion="SUCCESS", status="COMPLETED"):
    return {"__typename": "CheckRun", "status": status, "conclusion": conclusion}


def status_context(state):
    return {"__typename": "StatusContext", "state": state}


def pull_request(number, checks, merge_state="CLEAN", branch=None):
    return {"number": number, "title": f"Change {number}", "url": f"https://github.com/owner/repo/pull/{number}",
            "headRefName": branch or f"branch-{number}", "headRefOid": f"sha{number}",
            "mergeStateStatus": merge_state, "statusCheckRollup": checks}


def gitlab_merge_request(iid, pipeline_status="success", merge_status="mergeable"):
    pipeline = {"status": pipeline_status} if pipeline_status else None
    return {"iid": iid, "title": f"Change {iid}", "web_url": f"https://gitlab.example.com/group/project/-/merge_requests/{iid}",
            "source_branch": f"branch-{iid}", "sha": f"sha{iid}", "head_pipeline": pipeline,
            "detailed_merge_status": merge_status}


@pytest.fixture
def gmergegreen(load_script):
    return load_script("gmergegreen")


@pytest.fixture
def repo(tmp_path, git):
    def _repo(relative_path, remote=GITHUB_REMOTE):
        path = tmp_path / "scan" / relative_path
        path.mkdir(parents=True)
        git(path, "init", "--quiet")
        git(path, "remote", "add", "origin", remote)
        return path
    return _repo


@pytest.fixture
def run(run_cli, tmp_path, git_env):
    def _run(pull_requests, gum_answer=0, gh_merge_exit=0):
        (tmp_path / "prs.json").write_text(json.dumps(pull_requests))
        gh = (f'printf \'%s\\n\' "$*" >> "{tmp_path}/gh-calls"\n'
              f'case "$1 $2" in\n'
              f'    "pr list") cat "{tmp_path}/prs.json" ;;\n'
              f'    "pr merge") echo "merge refused" >&2; exit {gh_merge_exit} ;;\n'
              f'esac\n')
        gum = f'printf \'%s\\n\' "$*" >> "{tmp_path}/gum-calls"\nexit {gum_answer}\n'
        return run_cli("gmergegreen", [str(tmp_path / "scan")], mock_bins={"gh": gh, "gum": gum},
                       env_extra=git_env)
    return _run


@pytest.fixture
def calls(tmp_path):
    def _calls(client):
        path = tmp_path / f"{client}-calls"
        return path.read_text().splitlines() if path.exists() else []
    return _calls


@pytest.mark.parametrize("url, slug", [
    ("git@github.com:owner/repo.git", "github.com/owner/repo"),
    ("https://github.com/owner/repo.git\n", "github.com/owner/repo"),
    ("https://user@gitlab.example.com/group/sub/project", "gitlab.example.com/group/sub/project"),
    ("ssh://git@gitlab.example.com/group/project.git", "gitlab.example.com/group/project"),
    ("/srv/git/project.git", ""),
])
def should_derive_the_host_and_project_from_the_origin_url(gmergegreen, url, slug):
    assert gmergegreen.remote_slug(url) == slug


@pytest.mark.parametrize("checks, merge_state, blocker", [
    ([check_run(), check_run("SKIPPED"), status_context("SUCCESS")], "CLEAN", ""),
    ([check_run()], "HAS_HOOKS", ""),
    ([], "CLEAN", "no pipeline"),
    ([check_run(), check_run(None, "IN_PROGRESS")], "CLEAN", "pipeline running"),
    ([check_run(), status_context("PENDING")], "CLEAN", "pipeline running"),
    ([check_run(None, "QUEUED"), check_run("FAILURE")], "UNSTABLE", "pipeline failed"),
    ([status_context("ERROR")], "CLEAN", "pipeline failed"),
    ([check_run()], "BLOCKED", "blocked"),
    ([check_run()], "DRAFT", "draft"),
])
def should_block_a_pull_request_unless_its_checks_passed_and_github_reports_it_mergeable(
        gmergegreen, checks, merge_state, blocker):
    assert gmergegreen.github_blocker(pull_request(1, checks, merge_state)) == blocker


@pytest.mark.parametrize("pipeline_status, merge_status, blocker", [
    ("success", "mergeable", ""),
    (None, "mergeable", "no pipeline"),
    ("running", "ci_still_running", "pipeline running"),
    ("failed", "ci_must_pass", "pipeline failed"),
    ("success", "not_approved", "not approved"),
    ("success", "conflict", "conflict"),
])
def should_block_a_merge_request_unless_its_pipeline_passed_and_gitlab_reports_it_mergeable(
        gmergegreen, pipeline_status, merge_status, blocker):
    assert gmergegreen.gitlab_blocker(gitlab_merge_request(1, pipeline_status, merge_status)) == blocker


def should_read_each_open_gitlab_merge_request_with_its_head_pipeline(gmergegreen):
    cli = FakeCli({"merge_requests?state=opened": json.dumps([{"iid": 7}, {"iid": 9}]),
                   "merge_requests/7": json.dumps(gitlab_merge_request(7)),
                   "merge_requests/9": json.dumps(gitlab_merge_request(9, "failed", "ci_must_pass"))})
    gitlab = gmergegreen.GitLab(cli, "gitlab.example.com", "group/project")

    merge_requests = gitlab.open_merge_requests()

    assert [(request.ref, request.blocker) for request in merge_requests] == [("!7", ""), ("!9", "pipeline failed")]


def should_squash_merge_a_gitlab_merge_request_at_its_listed_head_and_remove_its_branch(gmergegreen):
    cli = FakeCli({"/merge": "{}"})
    gitlab = gmergegreen.GitLab(cli, "gitlab.example.com", "group/project")

    gitlab.merge(gmergegreen.GitLab._merge_request(gitlab_merge_request(7)))

    assert cli.calls == [(f"glab api --hostname gitlab.example.com --method PUT --field squash=true "
                          f"--field should_remove_source_branch=true --raw-field sha=sha7 "
                          f"{GITLAB_PROJECT_PATH}/merge_requests/7/merge")]


def should_squash_merge_a_pull_request_at_its_listed_head_and_delete_its_branch(gmergegreen):
    cli = FakeCli({"pr merge": ""})
    github = gmergegreen.GitHub(cli, "owner/repo")

    github.merge(gmergegreen.GitHub._merge_request(pull_request(3, [check_run()])))

    assert cli.calls == ["gh pr merge 3 --squash --delete-branch --match-head-commit sha3 --repo owner/repo"]


def should_find_repositories_up_to_three_levels_deep_without_entering_symlinks(gmergegreen, tmp_path):
    scan = tmp_path / "scan"
    for relative_path in ("a/.git", "a/b/c/.git", "a/b/c/d/.git", "worktree", "elsewhere/x/.git"):
        (scan / relative_path).mkdir(parents=True)
    (scan / "worktree" / ".git").write_text("gitdir: /somewhere\n")
    (scan / "linked").symlink_to(scan / "elsewhere")

    repos = list(gmergegreen.find_repos(scan))

    assert repos == [scan / "a", scan / "a" / "b" / "c", scan / "elsewhere" / "x"]


def should_merge_only_the_passing_pull_requests_after_the_user_confirms(run, repo, calls):
    repo("personal/repo")

    result = run([pull_request(1, [check_run()]), pull_request(2, [check_run("FAILURE")])])

    assert result.returncode == 0, result.stderr
    assert [call for call in calls("gh") if call.startswith("pr merge")] == [
        "pr merge 1 --squash --delete-branch --match-head-commit sha1 --repo owner/repo"]
    assert calls("gum") == ["confirm --default=false Squash merge 1 merge request and delete their branches?"]
    assert "pipeline failed" in result.stdout


def should_merge_nothing_when_the_user_declines(run, repo, calls):
    repo("repo")

    result = run([pull_request(1, [check_run()])], gum_answer=1)

    assert result.returncode == 0
    assert calls("gh") == [("pr list --state open --limit 100 --json "
                            "number,title,url,headRefName,headRefOid,mergeStateStatus,statusCheckRollup --repo owner/repo")]


def should_pass_on_the_exit_status_when_the_prompt_is_interrupted(run, repo):
    repo("repo")

    result = run([pull_request(1, [check_run()])], gum_answer=130)

    assert result.returncode == 130


def should_not_ask_when_nothing_can_be_merged(run, repo, calls):
    repo("repo")

    result = run([pull_request(1, [])])

    assert result.returncode == 0
    assert calls("gum") == []
    assert "Nothing to merge." in result.stdout


def should_read_a_remote_once_when_two_checkouts_share_it(run, repo, calls):
    repo("one")
    repo("two")

    run([])

    assert len(calls("gh")) == 1


def should_fail_with_the_server_reason_when_a_merge_is_refused(run, repo):
    repo("repo")

    result = run([pull_request(1, [check_run()])], gh_merge_exit=1)

    assert result.returncode == 1
    assert "repo #1 branch-1: merge refused" in result.stderr


def should_reject_a_path_that_is_not_a_directory(run_cli, tmp_path):
    result = run_cli("gmergegreen", [str(tmp_path / "missing")])

    assert result.returncode == 2
    assert "is not a directory" in result.stderr
