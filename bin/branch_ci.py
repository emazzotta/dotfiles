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
from typing import Callable, Final, Optional, Union
from urllib.parse import quote

CACHE_DIR: Final = Path.home() / ".cache" / "gck" / "ci"
COMMAND_TIMEOUT_SECONDS: Final = 30
PARALLEL_LOOKUPS: Final = 8
GITLAB_PAGE_SIZE: Final = 100
GITHUB_RUNS_PER_BRANCH: Final = 20
SUCCESS: Final = "success"
FAILED: Final = "failed"
RUNNING: Final = "running"
NO_PIPELINE: Final = "none"
SCRIPT_FAILURE: Final = "script_failure"
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


class CommandFailed(Exception):
    pass


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

    def latest_pipeline(self, branch: str) -> Optional[Pipeline]:
        pipelines = json.loads(self._api(f"pipelines?ref={quote(branch, safe='')}&per_page=1"))
        if not pipelines:
            return None
        latest = pipelines[0]
        failed_ids = (str(latest["id"]),) if latest["status"] == FAILED else ()
        cache_key = f"{self.host}/{self.project} {latest['id']} {latest['updated_at']}"
        return Pipeline(latest["status"], latest["web_url"], failed_ids, cache_key)

    def failure_categories(self, pipeline: Pipeline) -> list[str]:
        categories = []
        for pipeline_id in pipeline.failed_ids:
            jobs = json.loads(self._api(f"pipelines/{pipeline_id}/jobs?scope=failed&per_page={GITLAB_PAGE_SIZE}"))
            categories.extend(self._job_category(job) for job in jobs if not job.get("allow_failure"))
        return categories

    def _job_category(self, job: dict) -> str:
        return classify_job(job.get("failure_reason") or "", job["name"],
                            lambda: self._api(f"jobs/{job['id']}/trace"))


class GitHub:
    CLIENT = "gh"

    def __init__(self, run: Run, repo: str):
        self.run = run
        self.repo = repo

    def _gh(self, *args: str) -> str:
        return self.run([self.CLIENT, *args, "--repo", self.repo])

    def latest_pipeline(self, branch: str) -> Optional[Pipeline]:
        runs = json.loads(self._gh("run", "list", "--branch", branch, "--limit", str(GITHUB_RUNS_PER_BRANCH),
                                   "--json", "databaseId,headSha,status,conclusion,url,updatedAt"))
        if not runs:
            return None
        head_runs = [run for run in runs if run["headSha"] == runs[0]["headSha"]]
        failed_runs = [run for run in head_runs if run["conclusion"] in GITHUB_FAILED_CONCLUSIONS]
        shown = failed_runs[0] if failed_runs else head_runs[0]
        cache_key = f"github.com/{self.repo} " + " ".join(f"{run['databaseId']}@{run['updatedAt']}"
                                                          for run in head_runs)
        return Pipeline(github_state(head_runs), shown["url"],
                        tuple(str(run["databaseId"]) for run in failed_runs), cache_key)

    def failure_categories(self, pipeline: Pipeline) -> list[str]:
        return [self._run_category(run_id) for run_id in pipeline.failed_ids]

    def _run_category(self, run_id: str) -> str:
        jobs = json.loads(self._gh("run", "view", run_id, "--json", "jobs"))["jobs"]
        failed_jobs = ", ".join(job["name"] for job in jobs if job["conclusion"] in GITHUB_FAILED_CONCLUSIONS)
        return classify_log(self._gh("run", "view", run_id, "--log-failed"), failed_jobs)


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


def lookup(provider: Provider, branch: str) -> BranchState:
    pipeline = provider.latest_pipeline(branch)
    if pipeline is None:
        return BranchState(branch, NO_PIPELINE, "", "")
    category = ""
    if pipeline.state == FAILED:
        category = cached(pipeline.cache_key,
                          lambda: ", ".join(dict.fromkeys(provider.failure_categories(pipeline))))
    return BranchState(branch, pipeline.state, category, pipeline.url)


def lookup_or_warn(provider: Provider, branch: str) -> tuple[Optional[BranchState], str]:
    try:
        return lookup(provider, branch), ""
    except CommandFailed as error:
        return None, str(error)
    except (ValueError, LookupError, TypeError):
        return None, f"unexpected {provider.CLIENT} response for {branch}"


def run_command(args: list[str]) -> str:
    try:
        completed = subprocess.run(args, capture_output=True, text=True, errors="replace",
                                   timeout=COMMAND_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        raise CommandFailed(f"{args[0]} timed out after {COMMAND_TIMEOUT_SECONDS}s") from None
    if completed.returncode != 0:
        lines = completed.stderr.strip().splitlines()
        raise CommandFailed(lines[0] if lines else f"{args[0]} exited with status {completed.returncode}")
    return completed.stdout


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
    branches = [line.strip() for line in sys.stdin if line.strip()]
    with ThreadPoolExecutor(PARALLEL_LOOKUPS) as pool:
        results = list(pool.map(lambda branch: lookup_or_warn(provider, branch), branches))
    for state, _ in results:
        if state:
            print(state.as_line())
    for warning in dict.fromkeys(warning for _, warning in results if warning):
        print(warning, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
