import json
import re

import pytest

GITHUB_REMOTE = "git@github.com:owner/repo.git"
GITLAB_REMOTE = "git@gitlab.example.com:group/project.git"
GITLAB_PROJECT_PATH = "projects/group%2Fproject"
RENOVATE_BODY = ("Updates boto3.\n\n---\n\n - [ ] <!-- rebase-check -->If you want to rebase/retry this PR, "
                 "check this box\n")
TERMINAL_ESCAPES = re.compile(r"\x1b\[[0-9;]*m|\x1b\]8;;[^\x1b]*\x1b\\")


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


CHECKS = {"PASSED": [check_run()], "NONE": [], "RUNNING": [check_run(None, "IN_PROGRESS")],
          "FAILED": [check_run("FAILURE")]}


def pull_request(number, checks, merge_state="CLEAN", branch=None, body=RENOVATE_BODY):
    return {"number": number, "title": f"Change {number}", "url": f"https://github.com/owner/repo/pull/{number}",
            "headRefName": branch or f"renovate/dependency-{number}", "headRefOid": f"sha{number}", "body": body,
            "mergeStateStatus": merge_state, "statusCheckRollup": checks}


def gitlab_merge_request(iid, pipeline_status="success", merge_status="mergeable", can_merge=True):
    pipeline = {"status": pipeline_status} if pipeline_status else None
    return {"iid": iid, "title": f"Change {iid}", "web_url": f"https://gitlab.example.com/group/project/-/merge_requests/{iid}",
            "source_branch": f"renovate/dependency-{iid}", "sha": f"sha{iid}", "description": RENOVATE_BODY,
            "head_pipeline": pipeline, "detailed_merge_status": merge_status, "user": {"can_merge": can_merge}}


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
    def _run(pull_requests, gum_answers=(), gum_exit=0, gh_list_exit=0, gh_merge_exit=0, permission="WRITE"):
        (tmp_path / "prs.json").write_text(json.dumps(pull_requests))
        for number, answer in enumerate(gum_answers, 1):
            (tmp_path / f"gum-answer-{number}").write_text(f"{answer}\n" if answer else "")
        gh = (f'printf \'%s\\n\' "$*" >> "{tmp_path}/gh-calls"\n'
              f'case "$1 $2" in\n'
              f'    "pr list") [ {gh_list_exit} -eq 0 ] || {{ echo "HTTP 502: Bad Gateway" >&2; exit {gh_list_exit}; }}\n'
              f'               cat "{tmp_path}/prs.json" ;;\n'
              f'    "pr merge") echo "merge refused" >&2; exit {gh_merge_exit} ;;\n'
              f'    "repo view") echo \'{{"viewerPermission": "{permission}"}}\' ;;\n'
              f'esac\n')
        gum = (f'printf \'%s\\n\' "$*" >> "{tmp_path}/gum-calls"\n'
               f'cat "{tmp_path}/gum-answer-$(wc -l < "{tmp_path}/gum-calls" | tr -d " ")" 2>/dev/null\n'
               f'exit {gum_exit}\n')
        opener = f'printf \'%s\\n\' "$*" >> "{tmp_path}/open-calls"\n'
        return run_cli("gmergegreen", [str(tmp_path / "scan")], mock_bins={"gh": gh, "gum": gum, "open": opener},
                       env_extra=git_env)
    return _run


@pytest.fixture
def calls(tmp_path):
    def _calls(client):
        path = tmp_path / f"{client}-calls"
        return path.read_text().splitlines() if path.exists() else []
    return _calls


def merges(calls):
    return [call for call in calls("gh") if call.startswith("pr merge")]


def merge_call(number):
    return f"pr merge {number} --squash --delete-branch --match-head-commit sha{number} --repo owner/repo"


def rebase_requests(calls):
    return [call for call in calls("gh") if call.startswith(("pr edit", "pr comment"))]


def github_repo(gmergegreen, cli):
    return gmergegreen.Repo("repo", "github.com/owner/repo", gmergegreen.GitHub(cli, "owner/repo"))


def offered(gmergegreen, *pipelines):
    repo = gmergegreen.Repo("repo", "github.com/owner/repo", None)
    return [(repo, gmergegreen.GitHub._merge_request(pull_request(number, CHECKS[pipeline])))
            for number, pipeline in enumerate(pipelines, 1)]


def listing(result):
    return [line for line in TERMINAL_ESCAPES.sub("", result.stdout).splitlines() if line.startswith("  ")]


def checkbox_call(header, *entries):
    return " ".join(["choose --no-limit --cursor-prefix [ ]  --selected-prefix [x]  --unselected-prefix [ ] ",
                     "--header", header, *entries])


@pytest.mark.parametrize("url, slug", [
    ("git@github.com:owner/repo.git", "github.com/owner/repo"),
    ("https://github.com/owner/repo.git\n", "github.com/owner/repo"),
    ("https://user@gitlab.example.com/group/sub/project", "gitlab.example.com/group/sub/project"),
    ("ssh://git@gitlab.example.com/group/project.git", "gitlab.example.com/group/project"),
    ("/srv/git/project.git", ""),
])
def should_derive_the_host_and_project_from_the_origin_url(gmergegreen, url, slug):
    assert gmergegreen.remote_slug(url) == slug


@pytest.mark.parametrize("checks, merge_state, pipeline, blocker", [
    ([check_run(), check_run("SKIPPED"), status_context("SUCCESS")], "CLEAN", "PASSED", ""),
    ([check_run()], "HAS_HOOKS", "PASSED", ""),
    ([], "CLEAN", "NONE", ""),
    ([check_run(), check_run(None, "IN_PROGRESS")], "BLOCKED", "RUNNING", ""),
    ([check_run(), status_context("PENDING")], "UNSTABLE", "RUNNING", ""),
    ([check_run(None, "QUEUED"), check_run("FAILURE")], "UNSTABLE", "FAILED", ""),
    ([status_context("ERROR")], "BLOCKED", "FAILED", ""),
    ([check_run()], "BLOCKED", "PASSED", "blocked"),
    ([check_run()], "UNSTABLE", "PASSED", "unstable"),
    ([check_run()], "DRAFT", "PASSED", "draft"),
    ([check_run("FAILURE")], "DIRTY", "FAILED", "dirty"),
])
def should_read_the_pipeline_of_a_pull_request_and_whatever_else_keeps_github_from_merging_it(
        gmergegreen, checks, merge_state, pipeline, blocker):
    merge_request = gmergegreen.GitHub._merge_request(pull_request(1, checks, merge_state))

    assert (merge_request.pipeline, merge_request.blocker) == (gmergegreen.Pipeline[pipeline], blocker)


@pytest.mark.parametrize("pipeline_status, merge_status, pipeline, blocker", [
    ("success", "mergeable", "PASSED", ""),
    (None, "mergeable", "NONE", ""),
    (None, "ci_must_pass", "NONE", ""),
    ("skipped", "mergeable", "NONE", ""),
    ("running", "ci_still_running", "RUNNING", ""),
    ("manual", "ci_still_running", "RUNNING", ""),
    ("failed", "ci_must_pass", "FAILED", ""),
    ("canceled", "ci_must_pass", "FAILED", ""),
    ("success", "not_approved", "PASSED", "not approved"),
    ("failed", "conflict", "FAILED", "conflict"),
])
def should_read_the_pipeline_of_a_merge_request_and_whatever_else_keeps_gitlab_from_merging_it(
        gmergegreen, pipeline_status, merge_status, pipeline, blocker):
    merge_request = gmergegreen.GitLab._merge_request(gitlab_merge_request(1, pipeline_status, merge_status))

    assert (merge_request.pipeline, merge_request.blocker) == (gmergegreen.Pipeline[pipeline], blocker)


@pytest.mark.parametrize("branch, dependency_update", [
    ("renovate/python-3.x", True),
    ("dependabot/npm_and_yarn/lodash-4.17.21", True),
    ("feat/parking-layer", False),
])
def should_offer_only_renovate_and_dependabot_updates(gmergegreen, branch, dependency_update):
    merge_request = gmergegreen.GitHub._merge_request(pull_request(1, [check_run("FAILURE")], branch=branch))

    assert merge_request.dependency_update is dependency_update


def should_read_each_open_gitlab_merge_request_with_its_head_pipeline(gmergegreen):
    cli = FakeCli({"merge_requests?state=opened": json.dumps([{"iid": 7}, {"iid": 9}]),
                   "merge_requests/7": json.dumps(gitlab_merge_request(7)),
                   "merge_requests/9": json.dumps(gitlab_merge_request(9, "failed", "ci_must_pass"))})
    gitlab = gmergegreen.GitLab(cli, "gitlab.example.com", "group/project")

    merge_requests = gitlab.open_merge_requests()

    assert [(request.ref, request.pipeline.name) for request in merge_requests] == [("!7", "PASSED"), ("!9", "FAILED")]


@pytest.mark.parametrize("pipelines, tiers", [
    (("PASSED", "NONE", "RUNNING", "FAILED"), {"Merge all passing (1)": ["#1"],
                                               "Merge all not failing (3)": ["#1", "#2", "#3"],
                                               "Merge all incl. failing (4)": ["#1", "#2", "#3", "#4"]}),
    (("PASSED", "PASSED"), {"Merge all passing (2)": ["#1", "#2"]}),
    (("PASSED", "FAILED"), {"Merge all passing (1)": ["#1"], "Merge all incl. failing (2)": ["#1", "#2"]}),
    (("NONE", "FAILED"), {"Merge all not failing (1)": ["#1"], "Merge all incl. failing (2)": ["#1", "#2"]}),
])
def should_offer_each_merge_tier_only_when_it_adds_merge_requests_to_the_one_before(gmergegreen, pipelines, tiers):
    offered_tiers = gmergegreen.merge_tiers(offered(gmergegreen, *pipelines))

    assert {label: [request.ref for _, request in action.targets]
            for label, action in offered_tiers.items()} == tiers


def should_align_the_checklist_and_name_the_pipeline_unless_it_passed(gmergegreen):
    entries = gmergegreen.checklist_entries(offered(gmergegreen, "PASSED", "NONE", "FAILED"))

    assert list(entries) == ["✓  repo  renovate/dependency-1  #1",
                             "○  repo  renovate/dependency-2  #2  no pipeline",
                             "✗  repo  renovate/dependency-3  #3  pipeline failed"]


def should_hide_the_merge_requests_gitlab_would_not_let_the_viewer_merge(gmergegreen):
    cli = FakeCli({"merge_requests?state=opened": json.dumps([{"iid": 7}, {"iid": 9}]),
                   "merge_requests/7": json.dumps(gitlab_merge_request(7, can_merge=False)),
                   "merge_requests/9": json.dumps(gitlab_merge_request(9))})
    gitlab = gmergegreen.GitLab(cli, "gitlab.example.com", "group/project")

    merge_requests = gitlab.open_merge_requests()

    assert [request.ref for request in merge_requests] == ["!9"]


@pytest.mark.parametrize("merge_status, outdated", [("need_rebase", True), ("conflict", True), ("not_approved", False)])
def should_offer_a_rebase_when_gitlab_reports_a_merge_request_behind_or_conflicted(gmergegreen, merge_status, outdated):
    merge_request = gmergegreen.GitLab._merge_request(gitlab_merge_request(1, "success", merge_status))

    assert merge_request.outdated is outdated


@pytest.mark.parametrize("merge_state, outdated", [("BEHIND", True), ("DIRTY", True), ("DRAFT", False)])
def should_offer_a_rebase_when_github_reports_a_pull_request_behind_or_conflicted(gmergegreen, merge_state, outdated):
    merge_request = gmergegreen.GitHub._merge_request(pull_request(1, [check_run()], merge_state))

    assert merge_request.outdated is outdated


def should_ask_renovate_to_rebase_a_pull_request_by_ticking_its_rebase_checkbox(gmergegreen):
    cli = FakeCli({"pr edit": ""})

    gmergegreen.request_rebase(github_repo(gmergegreen, cli),
                               gmergegreen.GitHub._merge_request(pull_request(1, [check_run()], "BEHIND")))

    assert cli.calls == [f"gh pr edit 1 --body {RENOVATE_BODY.replace('- [ ]', '- [x]')} --repo owner/repo"]


def should_ask_renovate_to_rebase_a_gitlab_merge_request_by_ticking_its_rebase_checkbox(gmergegreen):
    cli = FakeCli({"merge_requests/1": "{}"})
    gitlab = gmergegreen.GitLab(cli, "gitlab.example.com", "group/project")
    repo = gmergegreen.Repo("project", "gitlab.example.com/group/project", gitlab)

    gmergegreen.request_rebase(repo, gitlab._merge_request(gitlab_merge_request(1, "success", "need_rebase")))

    assert cli.calls == [(f"glab api --hostname gitlab.example.com --method PUT --raw-field "
                          f"description={RENOVATE_BODY.replace('- [ ]', '- [x]')} {GITLAB_PROJECT_PATH}/merge_requests/1")]


def should_ask_dependabot_to_rebase_by_commenting_its_rebase_command(gmergegreen):
    cli = FakeCli({"pr comment": ""})
    branch = "dependabot/npm_and_yarn/lodash-4.17.21"

    gmergegreen.request_rebase(github_repo(gmergegreen, cli),
                               gmergegreen.GitHub._merge_request(pull_request(1, [check_run()], "DIRTY", branch, "")))

    assert cli.calls == ["gh pr comment 1 --body @dependabot rebase --repo owner/repo"]


def should_leave_a_renovate_rebase_that_was_already_requested_alone(gmergegreen):
    cli = FakeCli({})
    body = RENOVATE_BODY.replace("- [ ]", "- [x]")

    gmergegreen.request_rebase(github_repo(gmergegreen, cli),
                               gmergegreen.GitHub._merge_request(pull_request(1, [check_run()], "BEHIND", body=body)))

    assert cli.calls == []


def should_refuse_a_renovate_rebase_when_the_description_has_no_rebase_checkbox(gmergegreen):
    merge_request = gmergegreen.GitHub._merge_request(pull_request(1, [check_run()], "BEHIND", body="Updates boto3."))

    with pytest.raises(gmergegreen.CommandFailed, match="no Renovate rebase checkbox"):
        gmergegreen.request_rebase(github_repo(gmergegreen, FakeCli({})), merge_request)


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


def should_list_every_dependency_update_with_what_keeps_it_from_passing_and_offer_the_mergeable_ones(
        run, repo, calls):
    repo("repo")

    result = run([pull_request(1, CHECKS["PASSED"]), pull_request(2, CHECKS["NONE"]),
                  pull_request(3, CHECKS["FAILED"], branch="dependabot/npm_and_yarn/lodash-4.17.21"),
                  pull_request(4, CHECKS["PASSED"], "DRAFT"),
                  pull_request(5, CHECKS["PASSED"], branch="feat/parking-layer")], gum_answers=["Skip"])

    assert listing(result) == ["  ✓  renovate/dependency-1",
                               "  ○  renovate/dependency-2                   no pipeline",
                               "  ✗  dependabot/npm_and_yarn/lodash-4.17.21  pipeline failed",
                               "  ⊘  renovate/dependency-4                   draft"]
    assert calls("gum") == [("choose --header 3 to squash merge Merge all passing (1) "
                             "Merge all not failing (2) Merge all incl. failing (3) "
                             "Merge individually Open all Open individually Skip")]


def should_not_show_a_repository_whose_merge_requests_could_not_be_read(run, repo):
    repo("repo")

    result = run([], gh_list_exit=1)

    assert result.returncode == 0
    assert "502" not in result.stdout + result.stderr


@pytest.mark.parametrize("answer, merged", [
    ("Merge all passing (1)", [1]),
    ("Merge all not failing (3)", [1, 2, 3]),
    ("Merge all incl. failing (4)", [1, 2, 3, 4]),
])
def should_merge_the_tier_the_user_chooses_but_never_an_update_the_server_holds_back(
        run, repo, calls, answer, merged):
    repo("personal/repo")

    result = run([pull_request(1, CHECKS["PASSED"]), pull_request(2, CHECKS["NONE"]),
                  pull_request(3, CHECKS["RUNNING"], "BLOCKED"), pull_request(4, CHECKS["FAILED"], "UNSTABLE"),
                  pull_request(5, CHECKS["FAILED"], "DIRTY")], gum_answers=[answer])

    assert result.returncode == 0, result.stderr
    assert merges(calls) == [merge_call(number) for number in merged]


def should_request_the_rebases_and_ask_again_for_what_is_left_to_merge(run, repo, calls):
    repo("repo")

    result = run([pull_request(1, CHECKS["PASSED"]), pull_request(2, CHECKS["PASSED"], "BEHIND"),
                  pull_request(3, CHECKS["FAILED"], "DIRTY", "dependabot/npm_and_yarn/lodash-4.17.21", "")],
                 gum_answers=["Request rebase (2)", "Skip"])

    assert result.returncode == 0, result.stderr
    assert listing(result)[:3] == ["  ✓  renovate/dependency-1",
                                   "  ↻  renovate/dependency-2                   behind",
                                   "  ↻  dependabot/npm_and_yarn/lodash-4.17.21  dirty"]
    assert "Requested 2 rebases." in result.stdout
    assert rebase_requests(calls) == ["pr edit 2 --body Updates boto3.",
                                      "pr comment 3 --body @dependabot rebase --repo owner/repo"]
    assert " - [x] <!-- rebase-check -->If you want to rebase/retry this PR, check this box" in calls("gh")
    assert calls("gum") == [("choose --header 1 to squash merge · 2 to rebase Merge all passing (1) "
                             "Merge individually Request rebase (2) Open all Open individually Skip"),
                            ("choose --header 1 to squash merge Merge all passing (1) "
                             "Merge individually Open all Open individually Skip")]
    assert merges(calls) == []


def should_stop_after_the_rebase_request_when_nothing_is_left_to_merge(run, repo, calls):
    repo("repo")

    result = run([pull_request(1, CHECKS["PASSED"], "BEHIND")], gum_answers=["Request rebase (1)"])

    assert result.returncode == 0, result.stderr
    assert calls("gum") == ["choose --header 1 to rebase Request rebase (1) Open all Open individually Skip"]


@pytest.mark.parametrize("permission", ["READ", "TRIAGE"])
def should_hide_the_pull_requests_of_a_repository_the_viewer_may_not_merge_in(run, repo, calls, permission):
    repo("repo")

    result = run([pull_request(1, CHECKS["PASSED"])], permission=permission)

    assert result.returncode == 0
    assert listing(result) == []
    assert calls("gum") == []
    assert "Nothing to merge." in result.stdout


def should_merge_the_ticked_updates_when_the_user_merges_individually(run, repo, calls):
    repo("repo")

    result = run([pull_request(1, CHECKS["PASSED"]), pull_request(2, CHECKS["FAILED"]),
                  pull_request(3, CHECKS["PASSED"])],
                 gum_answers=["Merge individually",
                              "✓  repo  renovate/dependency-1  #1\n✗  repo  renovate/dependency-2  #2  pipeline failed"])

    assert result.returncode == 0, result.stderr
    assert calls("gum")[1] == checkbox_call("Merge which?", "✓  repo  renovate/dependency-1  #1",
                                            "✗  repo  renovate/dependency-2  #2  pipeline failed",
                                            "✓  repo  renovate/dependency-3  #3")
    assert merges(calls) == [merge_call(1), merge_call(2)]


def should_merge_nothing_when_no_update_is_ticked(run, repo, calls):
    repo("repo")

    result = run([pull_request(1, [check_run()])], gum_answers=["Merge individually", ""])

    assert result.returncode == 0, result.stderr
    assert merges(calls) == []


def should_open_every_link_and_ask_again_when_the_user_opens_all(run, repo, calls):
    repo("repo")

    result = run([pull_request(1, [check_run()]), pull_request(2, [check_run()])],
                 gum_answers=["Open all", "Merge all passing (2)"])

    assert result.returncode == 0, result.stderr
    assert calls("open") == ["https://github.com/owner/repo/pull/1 https://github.com/owner/repo/pull/2"]
    assert merges(calls) == [merge_call(1), merge_call(2)]


def should_open_only_the_ticked_links_when_the_user_opens_individually(run, repo, calls):
    repo("repo")

    result = run([pull_request(1, [check_run()]), pull_request(2, [check_run()]), pull_request(3, [check_run()])],
                 gum_answers=["Open individually", "✓  repo  renovate/dependency-2  #2\n✓  repo  renovate/dependency-3  #3",
                              "Skip"])

    assert result.returncode == 0, result.stderr
    assert calls("gum")[1].startswith(checkbox_call("Open which?"))
    assert calls("open") == ["https://github.com/owner/repo/pull/2 https://github.com/owner/repo/pull/3"]
    assert merges(calls) == []


@pytest.mark.parametrize("gum_answer, gum_exit", [("Skip", 0), ("", 1)])
def should_merge_nothing_when_the_user_skips_or_dismisses_the_prompt(run, repo, calls, gum_answer, gum_exit):
    repo("repo")

    result = run([pull_request(1, [check_run()])], gum_answers=[gum_answer], gum_exit=gum_exit)

    assert result.returncode == 0
    assert calls("gh") == [("pr list --state open --limit 100 --json "
                            "number,title,url,headRefName,headRefOid,body,mergeStateStatus,statusCheckRollup "
                            "--repo owner/repo"),
                           "repo view owner/repo --json viewerPermission"]


def should_pass_on_the_exit_status_when_the_prompt_is_interrupted(run, repo):
    repo("repo")

    result = run([pull_request(1, [check_run()])], gum_answers=[""], gum_exit=130)

    assert result.returncode == 130


@pytest.mark.parametrize("open_pull_request", [
    pull_request(1, [check_run()], branch="feat/parking-layer"),
    pull_request(1, [check_run()], "DRAFT"),
])
def should_not_ask_when_no_dependency_update_can_be_merged(run, repo, calls, open_pull_request):
    repo("repo")

    result = run([open_pull_request])

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

    result = run([pull_request(1, [check_run()])], gum_answers=["Merge all passing (1)"], gh_merge_exit=1)

    assert result.returncode == 1
    assert "repo #1 renovate/dependency-1: merge refused" in result.stderr


def should_reject_a_path_that_is_not_a_directory(run_cli, tmp_path):
    result = run_cli("gmergegreen", [str(tmp_path / "missing")])

    assert result.returncode == 2
    assert "is not a directory" in result.stderr
