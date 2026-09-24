import json

import pytest

GITLAB_SLUG = "gitlab.example.com/group/project"
PIPELINE_URL = "https://gitlab.example.com/group/project/-/pipelines/{}"
SUREFIRE_FAILURE = "[ERROR] Failed to execute goal maven-surefire-plugin:test: There are test failures.\n"
COMPILE_FAILURE = ("[ERROR] Failed to execute goal maven-compiler-plugin:compile: Compilation failure\n"
                   "[ERROR] Main.java:[163,35] Symbol nicht gefunden\n")
LOOKUP_TIMEOUT_BANNER = ("          \n   ERROR  \n          \n"
                         '  Get "https://gitlab.example.com/api/v4/x": dial tcp: lookup gitlab.example.com: '
                         "i/o timeout.   \n\n")

LOG_GLAB_CALL = 'printf \'%s\\n\' "$*" >> "$HOME/glab-calls"\n'
ANSWER_BRANCH_PIPELINES = r'''
case "$*" in
    *"pipelines?scope=branches&"*) echo '[{"id": 1, "ref": "main", "status": "success", "updated_at": "t", "web_url": "https://gitlab.example.com/p/1"}]' ;;
    *) echo '[]' ;;
esac
'''
GLAB_ANSWERING = LOG_GLAB_CALL + ANSWER_BRANCH_PIPELINES
GLAB_TIMING_OUT = LOG_GLAB_CALL + f"printf '%s' '{LOOKUP_TIMEOUT_BANNER}' >&2\nexit 1\n"
GLAB_UNAUTHORIZED = LOG_GLAB_CALL + 'echo "glab: 401 Unauthorized (HTTP 401)" >&2\nexit 1\n'


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


def gitlab_pipeline(pipeline_id, status, ref="feature", updated_at="2026-09-24T07:22:46Z"):
    return {"id": pipeline_id, "ref": ref, "status": status, "updated_at": updated_at,
            "web_url": PIPELINE_URL.format(pipeline_id)}


def gitlab_pipelines(*pipelines):
    return json.dumps(list(pipelines))


def gitlab_jobs(*jobs):
    return json.dumps([{"id": job_id, "name": name, "failure_reason": reason, "allow_failure": allowed}
                       for job_id, name, reason, allowed in jobs])


def github_run(run_id, sha, status="completed", conclusion="success", branch="feature"):
    return {"databaseId": run_id, "headBranch": branch, "headSha": sha, "status": status, "conclusion": conclusion,
            "url": f"https://github.com/owner/repo/actions/runs/{run_id}", "updatedAt": "2026-09-24T07:00:00Z"}


def branch_states(states):
    return [(state.branch, state.state) for state in states]


@pytest.fixture
def branch_ci(load_script, tmp_path, monkeypatch):
    module = load_script("branch_ci.py")
    monkeypatch.setattr(module, "CACHE_DIR", tmp_path / "cache")
    return module


@pytest.fixture
def gitlab(branch_ci):
    def _gitlab(responses):
        cli = FakeCli(responses)
        return branch_ci.GitLab(cli, "gitlab.example.com", "group/project"), cli
    return _gitlab


@pytest.fixture
def github(branch_ci):
    def _github(responses):
        cli = FakeCli(responses)
        return branch_ci.GitHub(cli, "owner/repo"), cli
    return _github


@pytest.fixture
def glab_calls(tmp_path):
    return lambda: (tmp_path / "glab-calls").read_text().splitlines()


@pytest.mark.parametrize("log, category", [
    ("error: RPC failed; curl 56 Recv failure: Operation timed out\nfatal: early EOF\n", "infra"),
    ("[exec] bash: ../commons/verify.sh: No such file or directory\n"
     "[ERROR] An Ant BuildException has occurred: exec returned: 127\n", "missing file"),
    (COMPILE_FAILURE, "compile"),
    (SUREFIRE_FAILURE, "tests"),
    ("> There were failing tests. See the report at: build/reports/tests/test/index.html\n", "tests"),
    ("npm error The `npm ci` command can only install with an existing package-lock.json or\n", "deps"),
])
def should_classify_a_failed_job_by_its_log(branch_ci, log, category):
    assert branch_ci.classify_log(log, "Build") == category


def should_fall_back_to_the_job_name_when_the_log_matches_no_category(branch_ci):
    assert branch_ci.classify_log("ERROR: Job failed: exit status 1\n", "Build & Deploy") == "Build & Deploy"


@pytest.mark.parametrize("stderr, reason", [
    ("glab: 404 Project Not Found (HTTP 404)\n", "glab: 404 Project Not Found (HTTP 404)"),
    (LOOKUP_TIMEOUT_BANNER, "dial tcp: lookup gitlab.example.com: i/o timeout."),
    ("          \n   ERROR  \n          \n"
     '  Get "https://gitlab.example.com/api/v4/projects/group%2Fproject/pipelines?ref=LEO-1234-a-long-branch- \n'
     '  name&per_page=1": dial tcp: lookup gitlab.example.com: no such host.                                  \n\n',
     "dial tcp: lookup gitlab.example.com: no such host."),
    ("", "glab exited with status 1"),
])
def should_report_the_cause_of_a_failed_command_without_glab_banner_url_or_line_wrapping(branch_ci, stderr, reason):
    assert branch_ci.failure_reason(stderr, "glab exited with status 1") == reason


def should_read_every_branch_from_one_gitlab_request_when_the_page_is_not_full(branch_ci, gitlab):
    provider, cli = gitlab({"pipelines?scope=branches": gitlab_pipelines(
        gitlab_pipeline(3, "running"), gitlab_pipeline(1, "success", ref="main"))})

    states, warnings = branch_ci.lookup_all(provider, ["main", "feature", "never-built"])

    assert branch_states(states) == [("main", "success"), ("feature", "running"), ("never-built", "none")]
    assert warnings == []
    assert cli.calls == ["glab api --hostname gitlab.example.com "
                         "projects/group%2Fproject/pipelines?scope=branches&per_page=100"]


def should_look_up_branches_missing_from_a_full_page_one_by_one(branch_ci, gitlab, monkeypatch):
    monkeypatch.setattr(branch_ci, "GITLAB_PAGE_SIZE", 1)
    provider, cli = gitlab({
        "pipelines?scope=branches": gitlab_pipelines(gitlab_pipeline(2, "success", ref="main")),
        "pipelines?ref=old-branch": gitlab_pipelines(gitlab_pipeline(1, "failed", ref="old-branch")),
        "pipelines/1/jobs": gitlab_jobs(),
    })

    states, _ = branch_ci.lookup_all(provider, ["main", "old-branch"])

    assert branch_states(states) == [("main", "success"), ("old-branch", "failed")]
    assert sum("pipelines?ref=" in call for call in cli.calls) == 1


def should_keep_a_failed_pipeline_failed_and_retry_its_category_next_run_when_the_jobs_cannot_be_fetched(
        branch_ci, gitlab):
    timeout = branch_ci.CommandFailed("dial tcp: lookup gitlab.example.com: i/o timeout.")
    provider, cli = gitlab({
        "pipelines?scope=branches": gitlab_pipelines(gitlab_pipeline(2, "failed")),
        "pipelines/2/jobs": timeout,
        "jobs/1/trace": SUREFIRE_FAILURE,
    })

    first = branch_ci.lookup_all(provider, ["feature"])
    cli.responses["pipelines/2/jobs"] = gitlab_jobs((1, "Test", "script_failure", False))
    second = branch_ci.lookup_all(provider, ["feature"])

    assert first == ([branch_ci.BranchState("feature", "failed", "", PIPELINE_URL.format(2))], [str(timeout)])
    assert second == ([branch_ci.BranchState("feature", "failed", "tests", PIPELINE_URL.format(2))], [])


def should_query_the_latest_gitlab_pipeline_of_a_branch_by_its_encoded_name(gitlab):
    provider, cli = gitlab({"pipelines?ref=": gitlab_pipelines(gitlab_pipeline(1, "success"))})

    pipeline = provider.latest_pipeline("refactor/double-api")

    assert (pipeline.state, pipeline.url) == ("success", PIPELINE_URL.format(1))
    assert cli.calls == ["glab api --hostname gitlab.example.com "
                         "projects/group%2Fproject/pipelines?ref=refactor%2Fdouble-api&per_page=1"]


def should_report_no_pipeline_for_a_branch_gitlab_never_built(gitlab):
    provider, _ = gitlab({"pipelines?ref=": "[]"})

    assert provider.latest_pipeline("local-only") is None


def should_categorize_failed_gitlab_jobs_by_log_or_else_by_failure_reason(gitlab):
    provider, cli = gitlab({
        "pipelines?ref=": gitlab_pipelines(gitlab_pipeline(2, "failed")),
        "pipelines/2/jobs?scope=failed": gitlab_jobs((1, "Build", "script_failure", False),
                                                     (2, "Deploy", "runner_system_failure", False)),
        "jobs/1/trace": COMPILE_FAILURE,
    })

    categories = provider.failure_categories(provider.latest_pipeline("feature"))

    assert categories == ["compile", "runner system failure"]
    assert not any("jobs/2/trace" in call for call in cli.calls)


def should_ignore_gitlab_jobs_that_are_allowed_to_fail(gitlab):
    provider, _ = gitlab({
        "pipelines?ref=": gitlab_pipelines(gitlab_pipeline(3, "failed")),
        "pipelines/3/jobs?scope=failed": gitlab_jobs((1, "Lint", "script_failure", True),
                                                     (2, "Test", "script_failure", False)),
        "jobs/2/trace": SUREFIRE_FAILURE,
    })

    assert provider.failure_categories(provider.latest_pipeline("feature")) == ["tests"]


def should_group_recent_github_runs_by_branch_and_judge_each_by_its_head_commit(github):
    runs = [github_run(4, "b1", branch="docs"), github_run(3, "a2", conclusion="failure"),
            github_run(2, "a2"), github_run(1, "a1")]
    provider, cli = github({"run list": json.dumps(runs)})

    pipelines, complete = provider.recent_pipelines()

    assert {branch: pipeline.state for branch, pipeline in pipelines.items()} == {"docs": "success", "feature": "failed"}
    assert complete
    assert "--branch" not in cli.calls[0]


def should_report_github_runs_of_the_head_commit_as_failed_when_any_workflow_failed(github):
    runs = [github_run(3, "new"), github_run(2, "new", conclusion="failure"), github_run(1, "old")]
    provider, _ = github({"run list": json.dumps(runs)})

    pipeline = provider.latest_pipeline("feature")

    assert (pipeline.state, pipeline.url) == ("failed", "https://github.com/owner/repo/actions/runs/2")


def should_report_github_runs_as_running_while_a_workflow_of_the_head_commit_is_unfinished(github):
    runs = [github_run(3, "new", status="in_progress", conclusion=""), github_run(2, "new", conclusion="failure")]
    provider, _ = github({"run list": json.dumps(runs)})

    assert provider.latest_pipeline("feature").state == "running"


def should_name_the_failed_github_jobs_when_their_log_matches_no_category(github):
    jobs = {"jobs": [{"name": "pytest", "conclusion": "failure"}, {"name": "lint", "conclusion": "success"}]}
    provider, _ = github({
        "run list": json.dumps([github_run(2, "new", conclusion="failure")]),
        "--json jobs": json.dumps(jobs),
        "--log-failed": "pytest\tRun tests\tProcess completed with exit code 1.\n",
    })

    assert provider.failure_categories(provider.latest_pipeline("feature")) == ["pytest"]


def should_reuse_the_cached_category_while_the_failed_pipeline_is_unchanged(branch_ci, gitlab):
    provider, cli = gitlab({
        "pipelines?scope=branches": gitlab_pipelines(gitlab_pipeline(4, "failed")),
        "jobs?scope=failed": gitlab_jobs((1, "Build & Deploy", "script_failure", False)),
        "jobs/1/trace": SUREFIRE_FAILURE,
    })

    first = branch_ci.lookup_all(provider, ["feature"])
    second = branch_ci.lookup_all(provider, ["feature"])

    assert first == second == ([branch_ci.BranchState("feature", "failed", "tests", PIPELINE_URL.format(4))], [])
    assert sum("trace" in call for call in cli.calls) == 1


def should_recategorize_a_failed_pipeline_once_it_was_updated(branch_ci, gitlab):
    provider, cli = gitlab({
        "pipelines?scope=branches": gitlab_pipelines(gitlab_pipeline(4, "failed")),
        "jobs?scope=failed": gitlab_jobs((1, "Build & Deploy", "script_failure", False)),
        "jobs/1/trace": SUREFIRE_FAILURE,
    })
    branch_ci.lookup_all(provider, ["feature"])
    cli.responses["pipelines?scope=branches"] = gitlab_pipelines(
        gitlab_pipeline(4, "failed", updated_at="2026-09-24T08:00:00Z"))
    cli.responses["jobs/1/trace"] = COMPILE_FAILURE

    states, _ = branch_ci.lookup_all(provider, ["feature"])

    assert states[0].category == "compile"


def should_print_a_tab_separated_line_per_branch_from_a_single_request(run_cli, tmp_path, glab_calls):
    result = run_cli("branch_ci.py", [GITLAB_SLUG], stdin="main\nnever-built\n",
                     mock_bins={"glab": GLAB_ANSWERING}, env_extra={"HOME": str(tmp_path)})

    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout == "main\tsuccess\t\thttps://gitlab.example.com/p/1\nnever-built\tnone\t\t\n"
    assert len(glab_calls()) == 1


@pytest.mark.parametrize("glab, warning", [
    (GLAB_TIMING_OUT, "dial tcp: lookup gitlab.example.com: i/o timeout.\n"),
    (GLAB_UNAUTHORIZED, "glab: 401 Unauthorized (HTTP 401)\n"),
])
def should_warn_once_and_ask_only_once_when_the_repository_lookup_fails(run_cli, tmp_path, glab_calls, glab,
                                                                        warning):
    result = run_cli("branch_ci.py", [GITLAB_SLUG], stdin="main\nfeature\n",
                     mock_bins={"glab": glab}, env_extra={"HOME": str(tmp_path)})

    assert (result.returncode, result.stdout, result.stderr) == (0, "", warning)
    assert len(glab_calls()) == 1


def should_warn_once_when_the_ci_client_is_not_installed(run_cli, tmp_path):
    result = run_cli("branch_ci.py", [GITLAB_SLUG], stdin="main\nfeature\n", isolate_path=True,
                     env_extra={"HOME": str(tmp_path)})

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "glab is not installed\n")
