import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = "ref-pin"
GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
}


def _git(*args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), env={**os.environ, **GIT_IDENTITY},
                          check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo, path, text):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    _git("add", "-A", cwd=repo)
    _git("commit", "-qm", f"{path}: {text}", cwd=repo)
    return _git("rev-parse", "HEAD", cwd=repo)


def _make_upstream(path):
    path.mkdir(parents=True)
    _git("init", "-q", "-b", "main", ".", cwd=path)
    _git("config", "uploadpack.allowFilter", "true", cwd=path)
    _commit(path, "skills/x/SKILL.md", "one")
    return path


@pytest.fixture
def workspace(tmp_path):
    upstream = _make_upstream(tmp_path / "upstream")
    ws = tmp_path / "workspace"
    (ws / ".claude" / "skills").mkdir(parents=True)
    (ws / ".claude" / "agents").mkdir()
    (ws / ".claude" / "pinned-references").write_text(
        "# comment\n\n"
        f"sparse|file://{upstream}|skills/x\n"
        f"full|file://{upstream}|\n"
    )
    return ws


@pytest.fixture
def ref_pin(run_bash, workspace):
    def _run(*args, stdin=None):
        return run_bash(SCRIPT, list(args), env_extra={"REF_PIN_WORKSPACE": str(workspace),
                                                       **GIT_IDENTITY}, stdin=stdin)
    return _run


def _upstream(workspace):
    return workspace.parent / "upstream"


def _pin(workspace, name):
    return (workspace / ".claude" / f"{name}-reference.pin").read_text().strip()


def _head(workspace, name):
    return _git("rev-parse", "HEAD", cwd=workspace / ".claude" / f"{name}-reference")


class TestUsage:
    @pytest.mark.parametrize("args", [[], ["help"], ["-h"], ["--help"]])
    def should_show_usage_for_help_and_no_args(self, ref_pin, args):
        result = ref_pin(*args)

        assert result.returncode == 0
        assert "Usage: ref-pin list" in result.stdout

    def should_fail_for_an_unknown_reference(self, ref_pin):
        result = ref_pin("nope", "status")

        assert result.returncode == 1
        assert "unknown reference: nope" in result.stderr

    def should_show_usage_without_any_workspace(self, run_bash, tmp_path):
        result = run_bash(SCRIPT, ["--help"], env_extra={"REF_PIN_WORKSPACE": str(tmp_path / "missing"),
                                                         "HOME": str(tmp_path)})

        assert result.returncode == 0
        assert "Usage: ref-pin list" in result.stdout

    def should_fail_when_no_workspace_is_found(self, run_bash, tmp_path):
        result = run_bash(SCRIPT, ["list"], env_extra={"REF_PIN_WORKSPACE": str(tmp_path / "missing"),
                                                       "HOME": str(tmp_path)})

        assert result.returncode == 1
        assert "no workspace" in result.stderr


class TestInit:
    def should_pin_the_upstream_head_when_no_pin_exists(self, ref_pin, workspace):
        head = _git("rev-parse", "HEAD", cwd=_upstream(workspace))

        result = ref_pin("sparse", "init")

        assert result.returncode == 0, result.stderr
        assert _pin(workspace, "sparse") == head
        assert _head(workspace, "sparse") == head

    def should_check_out_an_existing_pin(self, ref_pin, workspace):
        old = _git("rev-parse", "HEAD", cwd=_upstream(workspace))
        _commit(_upstream(workspace), "skills/x/SKILL.md", "two")
        (workspace / ".claude" / "full-reference.pin").write_text(old + "\n")

        result = ref_pin("full", "init")

        assert result.returncode == 0, result.stderr
        assert _head(workspace, "full") == old

    def should_limit_a_sparse_clone_to_the_registered_paths(self, ref_pin, workspace):
        _commit(_upstream(workspace), "docs/big.md", "not wanted")

        ref_pin("sparse", "init")

        clone = workspace / ".claude" / "sparse-reference"
        assert (clone / "skills" / "x" / "SKILL.md").exists()
        assert not (clone / "docs").exists()

    def should_not_reclone_an_existing_reference(self, ref_pin, workspace):
        ref_pin("sparse", "init")

        result = ref_pin("sparse", "init")

        assert result.returncode == 0
        assert "already cloned" in result.stdout


class TestStatusAndList:
    def should_list_every_reference_with_its_state(self, ref_pin):
        ref_pin("sparse", "init")

        result = ref_pin("list")

        lines = result.stdout.splitlines()
        assert lines[0].startswith("sparse       OK")
        assert lines[1].startswith("full         not cloned (no pin)")

    def should_report_drift_when_the_checkout_leaves_the_pin(self, ref_pin, workspace):
        ref_pin("full", "init")
        _git("checkout", "-q", "--detach", "HEAD~0", cwd=workspace / ".claude" / "full-reference")
        _commit(_upstream(workspace), "skills/x/SKILL.md", "two")
        _git("fetch", "-q", "origin", cwd=workspace / ".claude" / "full-reference")
        _git("checkout", "-q", "--detach", "origin/main", cwd=workspace / ".claude" / "full-reference")

        result = ref_pin("full", "status")

        assert "State:       DRIFT" in result.stdout
        assert "1 commits ahead on origin/main" in result.stdout

    def should_show_symlinks_that_point_into_the_reference(self, ref_pin, workspace):
        ref_pin("sparse", "init")
        (workspace / ".claude" / "skills" / "x").symlink_to("../sparse-reference/skills/x")
        (workspace / ".claude" / "skills" / "gone").symlink_to("../sparse-reference/skills/gone")

        result = ref_pin("sparse", "status")

        assert "OK     x -> skills/x" in result.stdout
        assert "BROKEN gone -> skills/gone" in result.stdout


class TestDiffAndBump:
    def should_list_only_upstream_commits_touching_watched_paths(self, ref_pin, workspace):
        ref_pin("sparse", "init")
        _commit(_upstream(workspace), "skills/x/SKILL.md", "two")
        _commit(_upstream(workspace), "README.md", "unrelated")
        ref_pin("sparse", "fetch")

        result = ref_pin("sparse", "diff")

        assert "### skills/x" in result.stdout
        assert "skills/x/SKILL.md: two" in result.stdout
        assert "unrelated" not in result.stdout

    def should_advance_the_pin_and_checkout_when_confirmed(self, ref_pin, workspace):
        ref_pin("sparse", "init")
        new = _commit(_upstream(workspace), "skills/x/SKILL.md", "two")

        result = ref_pin("sparse", "bump", stdin="y\n")

        assert result.returncode == 0, result.stderr
        assert "skills/x (1 commits)" in result.stdout
        assert _pin(workspace, "sparse") == new
        assert _head(workspace, "sparse") == new

    def should_leave_the_pin_alone_when_the_bump_is_declined(self, ref_pin, workspace):
        ref_pin("sparse", "init")
        old = _pin(workspace, "sparse")
        _commit(_upstream(workspace), "skills/x/SKILL.md", "two")

        result = ref_pin("sparse", "bump", stdin="n\n")

        assert result.returncode == 1
        assert "aborted" in result.stderr
        assert _pin(workspace, "sparse") == old
        assert _head(workspace, "sparse") == old

    def should_report_when_already_at_the_upstream_head(self, ref_pin):
        ref_pin("sparse", "init")

        result = ref_pin("sparse", "bump", stdin="y\n")

        assert result.returncode == 0
        assert "Already at origin/main" in result.stdout


class TestRestore:
    def should_recheckout_the_pinned_sha(self, ref_pin, workspace):
        ref_pin("full", "init")
        pinned = _pin(workspace, "full")
        _commit(_upstream(workspace), "skills/x/SKILL.md", "two")
        clone = workspace / ".claude" / "full-reference"
        _git("fetch", "-q", "origin", cwd=clone)
        _git("checkout", "-q", "--detach", "origin/main", cwd=clone)

        result = ref_pin("full", "restore")

        assert result.returncode == 0
        assert _head(workspace, "full") == pinned

    def should_refuse_commands_on_an_uncloned_reference(self, ref_pin):
        result = ref_pin("full", "restore")

        assert result.returncode == 1
        assert "not cloned - run 'ref-pin full init'" in result.stderr
