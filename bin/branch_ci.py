#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Final, Iterable, Optional, TypeVar, Union
from urllib.parse import quote

CACHE_DIR: Final = Path.home() / ".cache" / "gck" / "ci"
COMMAND_TIMEOUT_SECONDS: Final = 30
TRANSPORT_ATTEMPTS: Final = 2
PARALLEL_LOOKUPS: Final = 8
GITLAB_PAGE_SIZE: Final = 100
GITHUB_RUNS_PAGE_SIZE: Final = 100
GITHUB_RUNS_PER_BRANCH: Final = 20
GITHUB_RUN_FIELDS: Final = "databaseId,headBranch,headSha,status,conclusion,url,updatedAt"
SUCCESS: Final = "success"
FAILED: Final = "failed"
RUNNING: Final = "running"
NO_PIPELINE: Final = "none"
SCRIPT_FAILURE: Final = "script_failure"
ERROR_BANNER: Final = "ERROR"
TRANSPORT_ERROR: Final = re.compile(r'^\w+ "[^"]*": (?P<cause>.+)$')
GITHUB_FAILED_CONCLUSIONS: Final = frozenset({"failure", "timed_out", "startup_failure"})
GITHUB_PASSING_CONCLUSIONS: Final = frozenset({SUCCESS, "skipped", "neutral"})
LOG_CATEGORIES: Final = (
    ("infra", re.compile(r"RPC failed|early EOF")),
    ("compile", re.compile(r"COMPILATION ERROR|Compilation fail")),
    ("tests", re.compile(r"There are test failures|There were failing tests")),
    ("deps", re.compile(r"can only install with an existing package-lock")),
    ("missing file", re.compile(r"exec returned: 127")),
)

Run = Callable[[list[str]], str]
T = TypeVar("T")


class CommandFailed(Exception):
    def __init__(self, reason: str, transient: bool = False):
        super().__init__(reason)
        self.transient = transient


@dataclass(frozen=True)
class Pipeline:
    state: str
    url: str
    failed_ids: tuple[str, ...]
    cache_key: str


@dataclass(frozen=True)
class BranchState:
    branch: str
    state: str
    category: str
    url: str

    def as_line(self) -> str:
        return "\t".join((self.branch, self.state, self.category, self.url))


def classify_log(log: str, job_name: str) -> str:
    for category, pattern in LOG_CATEGORIES:
        if pattern.search(log):
            return category
    return job_name


def classify_job(failure_reason: str, job_name: str, read_log: Callable[[], str]) -> str:
    if failure_reason and failure_reason != SCRIPT_FAILURE:
        return failure_reason.replace("_", " ")
    return classify_log(read_log(), job_name)


class GitLab:
    CLIENT = "glab"

    def __init__(self, run: Run, host: str, project: str):
        self.run = run
        self.host = host
        self.project = project

    def _api(self, endpoint: str) -> str:
        project_path = quote(self.project, safe="")
        return self.run([self.CLIENT, "api", "--hostname", self.host, f"projects/{project_path}/{endpoint}"])

    def recent_pipelines(self) -> tuple[dict[str, Pipeline], bool]:
        pipelines = json.loads(self._api(f"pipelines?scope=branches&per_page={GITLAB_PAGE_SIZE}"))
        oldest_first = sorted(pipelines, key=lambda pipeline: pipeline["id"])
        return ({pipeline["ref"]: self._pipeline(pipeline) for pipeline in oldest_first},
                len(pipelines) < GITLAB_PAGE_SIZE)

    def latest_pipeline(self, branch: str) -> Optional[Pipeline]:
        pipelines = json.loads(self._api(f"pipelines?ref={quote(branch, safe='')}&per_page=1"))
        return self._pipeline(pipelines[0]) if pipelines else None

    def failure_categories(self, pipeline: Pipeline) -> list[str]:
        categories = []
        for pipeline_id in pipeline.failed_ids:
            jobs = json.loads(self._api(f"pipelines/{pipeline_id}/jobs?scope=failed&per_page={GITLAB_PAGE_SIZE}"))
            categories.extend(self._job_category(job) for job in jobs if not job.get("allow_failure"))
        return categories

    def _job_category(self, job: dict) -> str:
        return classify_job(job.get("failure_reason") or "", job["name"],
                            lambda: self._api(f"jobs/{job['id']}/trace"))

    def _pipeline(self, pipeline: dict) -> Pipeline:
        failed_ids = (str(pipeline["id"]),) if pipeline["status"] == FAILED else ()
        cache_key = f"{self.host}/{self.project} {pipeline['id']} {pipeline['updated_at']}"
        return Pipeline(pipeline["status"], pipeline["web_url"], failed_ids, cache_key)


class GitHub:
    CLIENT = "gh"

    def __init__(self, run: Run, repo: str):
        self.run = run
        self.repo = repo

    def _gh(self, *args: str) -> str:
        return self.run([self.CLIENT, *args, "--repo", self.repo])

    def recent_pipelines(self) -> tuple[dict[str, Pipeline], bool]:
        runs = json.loads(self._gh("run", "list", "--limit", str(GITHUB_RUNS_PAGE_SIZE), "--json", GITHUB_RUN_FIELDS))
        runs_by_branch: dict[str, list[dict]] = {}
        for run in runs:
            runs_by_branch.setdefault(run["headBranch"], []).append(run)
        return ({branch: self._pipeline(branch_runs) for branch, branch_runs in runs_by_branch.items()},
                len(runs) < GITHUB_RUNS_PAGE_SIZE)

    def latest_pipeline(self, branch: str) -> Optional[Pipeline]:
        runs = json.loads(self._gh("run", "list", "--branch", branch, "--limit", str(GITHUB_RUNS_PER_BRANCH),
                                   "--json", GITHUB_RUN_FIELDS))
        return self._pipeline(runs) if runs else None

    def failure_categories(self, pipeline: Pipeline) -> list[str]:
        return [self._run_category(run_id) for run_id in pipeline.failed_ids]

    def _run_category(self, run_id: str) -> str:
        jobs = json.loads(self._gh("run", "view", run_id, "--json", "jobs"))["jobs"]
        failed_jobs = ", ".join(job["name"] for job in jobs if job["conclusion"] in GITHUB_FAILED_CONCLUSIONS)
        return classify_log(self._gh("run", "view", run_id, "--log-failed"), failed_jobs)

    def _pipeline(self, runs: list[dict]) -> Pipeline:
        head_runs = [run for run in runs if run["headSha"] == runs[0]["headSha"]]
        failed_runs = [run for run in head_runs if run["conclusion"] in GITHUB_FAILED_CONCLUSIONS]
        shown = failed_runs[0] if failed_runs else head_runs[0]
        cache_key = f"github.com/{self.repo} " + " ".join(f"{run['databaseId']}@{run['updatedAt']}"
                                                          for run in head_runs)
        return Pipeline(github_state(head_runs), shown["url"],
                        tuple(str(run["databaseId"]) for run in failed_runs), cache_key)


Provider = Union[GitLab, GitHub]


def github_state(runs: list[dict]) -> str:
    if any(run["status"] != "completed" for run in runs):
        return RUNNING
    conclusions = {run["conclusion"] for run in runs}
    if conclusions & GITHUB_FAILED_CONCLUSIONS:
        return FAILED
    unsettled = sorted(conclusions - GITHUB_PASSING_CONCLUSIONS)
    return unsettled[0] if unsettled else SUCCESS


def cached(key: str, compute: Callable[[], str]) -> str:
    path = CACHE_DIR / hashlib.sha256(key.encode()).hexdigest()
    if path.is_file():
        return path.read_text()
    value = compute()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    return value


def describe(provider: Provider, branch: str, pipeline: Optional[Pipeline],
             complete: bool) -> tuple[Optional[BranchState], str]:
    if pipeline is None and not complete:
        pipeline, warning = warn_on_failure(lambda: provider.latest_pipeline(branch), provider)
        if warning:
            return None, warning
    if pipeline is None:
        return BranchState(branch, NO_PIPELINE, "", ""), ""
    found = pipeline
    category, warning = warn_on_failure(lambda: failure_category(provider, found), provider)
    return BranchState(branch, found.state, category or "", found.url), warning


def failure_category(provider: Provider, pipeline: Pipeline) -> str:
    if pipeline.state != FAILED:
        return ""
    return cached(pipeline.cache_key, lambda: ", ".join(dict.fromkeys(provider.failure_categories(pipeline))))


def lookup_all(provider: Provider, branches: list[str]) -> tuple[list[BranchState], list[str]]:
    recent, warning = warn_on_failure(provider.recent_pipelines, provider)
    if recent is None:
        return [], [warning]
    pipelines, complete = recent
    with ThreadPoolExecutor(PARALLEL_LOOKUPS) as pool:
        results = list(pool.map(lambda branch: describe(provider, branch, pipelines.get(branch), complete), branches))
    return ([state for state, _ in results if state],
            list(dict.fromkeys(warning for _, warning in results if warning)))


def warn_on_failure(call: Callable[[], T], provider: Provider) -> tuple[Optional[T], str]:
    try:
        return call(), ""
    except CommandFailed as error:
        return None, str(error)
    except (ValueError, LookupError, TypeError):
        return None, f"unexpected {provider.CLIENT} response"


def run_command(args: list[str]) -> str:
    for _ in range(TRANSPORT_ATTEMPTS - 1):
        try:
            return run_once(args)
        except CommandFailed as failure:
            if not failure.transient:
                raise
    return run_once(args)


def run_once(args: list[str]) -> str:
    try:
        completed = subprocess.run(args, capture_output=True, text=True, errors="replace",
                                   timeout=COMMAND_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        raise CommandFailed(f"{args[0]} timed out after {COMMAND_TIMEOUT_SECONDS}s", transient=True) from None
    if completed.returncode != 0:
        raise failure_from(completed.stderr, f"{args[0]} exited with status {completed.returncode}")
    return completed.stdout


def failure_from(stderr: str, fallback: str) -> CommandFailed:
    message = unwrap(line.strip() for line in stderr.splitlines() if line.strip() not in ("", ERROR_BANNER))
    transport_error = TRANSPORT_ERROR.match(message)
    if transport_error:
        return CommandFailed(transport_error.group("cause"), transient=True)
    return CommandFailed(message or fallback)


def unwrap(lines: Iterable[str]) -> str:
    message = ""
    for line in lines:
        message += line if not message or message.endswith("-") else f" {line}"
    return message


def provider_for(slug: str, run: Run) -> Provider:
    host, _, path = slug.partition("/")
    if host == "github.com":
        return GitHub(run, path)
    return GitLab(run, host, path)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print the latest CI state of each branch read from stdin as tab separated "
                    "branch, state, failure category and pipeline url.")
    parser.add_argument("slug", help="remote host and project path, e.g. github.com/owner/repo")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    provider = provider_for(parse_args(argv).slug, run_command)
    if shutil.which(provider.CLIENT) is None:
        print(f"{provider.CLIENT} is not installed", file=sys.stderr)
        return 0
    states, warnings = lookup_all(provider, [line.strip() for line in sys.stdin if line.strip()])
    for state in states:
        print(state.as_line())
    for warning in warnings:
        print(warning, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
