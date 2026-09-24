import json

import pytest

GITLAB_SLUG = "gitlab.example.com/group/project"
PIPELINE_URL = "https://gitlab.example.com/group/project/-/pipelines/{}"
SUREFIRE_FAILURE = "[ERROR] Failed to execute goal maven-surefire-plugin:test: There are test failures.\n"
COMPILE_FAILURE = ("[ERROR] Failed to execute goal maven-compiler-plugin:compile: Compilation failure\n"
                   "[ERROR] Main.java:[163,35] Symbol nicht gefunden\n")

GLAB_MOCK = r'''
case "$*" in
    *"pipelines?ref=main&"*) echo '[{"id": 1, "status": "success", "updated_at": "t", "web_url": "https://gitlab.example.com/p/1"}]' ;;
    *"pipelines?ref=broken&"*) echo "401 Unauthorized" >&2; exit 1 ;;
    *) echo '[]' ;;
esac
'''


class FakeCli:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, args):
        command = " ".join(args)
        self.calls.append(command)
        for fragment, output in self.responses.items():
            if fragment in command:
                return output
        raise AssertionError(f"unexpected call: {command}")


def gitlab_pipelines(pipeline_id, status, updated_at="2026-09-24T07:22:46Z"):
    return json.dumps([{"id": pipeline_id, "status": status, "updated_at": updated_at,
                        "web_url": PIPELINE_URL.format(pipeline_id)}])


def gitlab_jobs(*jobs):
    return json.dumps([{"id": job_id, "name": name, "failure_reason": reason, "allow_failure": allowed}
                       for job_id, name, reason, allowed in jobs])


def github_run(run_id, sha, status="completed", conclusion="success"):
    return {"databaseId": run_id, "headSha": sha, "status": status, "conclusion": conclusion,
            "url": f"https://github.com/owner/repo/actions/runs/{run_id}",
            "updatedAt": "2026-09-24T07:00:00Z"}


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


def should_query_the_latest_gitlab_pipeline_of_a_branch_by_its_encoded_name(gitlab):
    provider, cli = gitlab({"pipelines?ref=": gitlab_pipelines(1, "success")})

    pipeline = provider.latest_pipeline("refactor/double-api")

    assert (pipeline.state, pipeline.url) == ("success", PIPELINE_URL.format(1))
    assert cli.calls == ["glab api --hostname gitlab.example.com "
                         "projects/group%2Fproject/pipelines?ref=refactor%2Fdouble-api&per_page=1"]


def should_report_no_pipeline_for_a_branch_gitlab_never_built(gitlab):
    provider, _ = gitlab({"pipelines?ref=": "[]"})

    assert provider.latest_pipeline("local-only") is None


def should_categorize_failed_gitlab_jobs_by_log_or_else_by_failure_reason(gitlab):
    provider, cli = gitlab({
        "pipelines?ref=": gitlab_pipelines(2, "failed"),
        "pipelines/2/jobs?scope=failed": gitlab_jobs((1, "Build", "script_failure", False),
                                                     (2, "Deploy", "runner_system_failure", False)),
        "jobs/1/trace": COMPILE_FAILURE,
    })

    categories = provider.failure_categories(provider.latest_pipeline("feature"))

    assert categories == ["compile", "runner system failure"]
    assert not any("jobs/2/trace" in call for call in cli.calls)


def should_ignore_gitlab_jobs_that_are_allowed_to_fail(gitlab):
    provider, _ = gitlab({
        "pipelines?ref=": gitlab_pipelines(3, "failed"),
        "pipelines/3/jobs?scope=failed": gitlab_jobs((1, "Lint", "script_failure", True),
                                                     (2, "Test", "script_failure", False)),
        "jobs/2/trace": SUREFIRE_FAILURE,
    })

    assert provider.failure_categories(provider.latest_pipeline("feature")) == ["tests"]


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
        "pipelines?ref=": gitlab_pipelines(4, "failed"),
        "jobs?scope=failed": gitlab_jobs((1, "Build & Deploy", "script_failure", False)),
        "jobs/1/trace": SUREFIRE_FAILURE,
    })

    first = branch_ci.lookup(provider, "feature")
    second = branch_ci.lookup(provider, "feature")

    assert first == second == branch_ci.BranchState("feature", "failed", "tests", PIPELINE_URL.format(4))
    assert sum("trace" in call for call in cli.calls) == 1


def should_recategorize_a_failed_pipeline_once_it_was_updated(branch_ci, gitlab):
    provider, cli = gitlab({
        "pipelines?ref=": gitlab_pipelines(4, "failed"),
        "jobs?scope=failed": gitlab_jobs((1, "Build & Deploy", "script_failure", False)),
        "jobs/1/trace": SUREFIRE_FAILURE,
    })
    branch_ci.lookup(provider, "feature")
    cli.responses["pipelines?ref="] = gitlab_pipelines(4, "failed", updated_at="2026-09-24T08:00:00Z")
    cli.responses["jobs/1/trace"] = COMPILE_FAILURE

    assert branch_ci.lookup(provider, "feature").category == "compile"


def should_print_a_tab_separated_line_per_looked_up_branch_and_warn_about_failed_lookups(run_cli, tmp_path):
    result = run_cli("branch_ci.py", [GITLAB_SLUG], stdin="main\nbroken\nnever-built\n",
                     mock_bins={"glab": GLAB_MOCK}, env_extra={"HOME": str(tmp_path)})

    assert result.returncode == 0
    assert result.stdout == "main\tsuccess\t\thttps://gitlab.example.com/p/1\nnever-built\tnone\t\t\n"
    assert result.stderr == "401 Unauthorized\n"


def should_warn_once_when_the_ci_client_is_not_installed(run_cli, tmp_path):
    result = run_cli("branch_ci.py", [GITLAB_SLUG], stdin="main\nfeature\n", isolate_path=True,
                     env_extra={"HOME": str(tmp_path)})

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "glab is not installed\n")
