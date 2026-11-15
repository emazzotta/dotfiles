import os
import re
import tempfile
from pathlib import Path

import pytest

SCRIPT = "ops/scripts/gitlab/build_variables.sh"
ANSI_COLOUR = re.compile(r"\x1b\[[0-9;]*m")
LOG_PREFIX = re.compile(r"\[[^\]]+\] (?:(WARN|ERROR): )?(.*)")
LEVELS = {"WARN": "warn", "ERROR": "error", None: "log"}
COPY_FAILING_FOR_BETA = 'case "$2" in *beta*) exit 1 ;; esac\nexec /bin/cp "$@"'


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "ws"
    for project in ("alpha", "beta", "gamma"):
        target = root / project / SCRIPT
        target.parent.mkdir(parents=True)
        target.write_text(f"old {project}\n")
    (root / "alpha" / SCRIPT).write_text("new content\n")
    return root


class TestSyncFile:
    def test_should_update_every_matching_file_and_print_the_summary(self, run_cli, workspace):
        result = run_cli("sync_file", [f"alpha/{SCRIPT}"], cwd=workspace)

        assert result.returncode == 0, result.stderr
        assert (workspace / "beta" / SCRIPT).read_text() == "new content\n"
        assert (workspace / "gamma" / SCRIPT).read_text() == "new content\n"
        assert "2 file(s) updated, 0 file(s) failed" in result.stdout

    def test_should_report_no_match_when_no_other_file_has_the_path(self, run_cli, workspace):
        lonely = workspace / "lonely"
        (lonely / "tools").mkdir(parents=True)
        (lonely / "tools" / "only.sh").write_text("x\n")

        result = run_cli("sync_file", ["lonely/tools/only.sh"], cwd=workspace)

        assert result.returncode == 0, result.stderr
        assert "No matching files found" in result.stdout
        assert "Found 1 matching" not in result.stdout


def messages(stream):
    """Each line as (level, text), without the timestamp."""
    lines = []
    for line in ANSI_COLOUR.sub("", stream).splitlines():
        logged = LOG_PREFIX.fullmatch(line)
        lines.append((LEVELS[logged[1]], logged[2]) if logged else ("plain", line))
    return lines


def updates_first(lines):
    updated = sorted(line for line in lines if line[1].startswith("Updated: "))
    return updated, [line for line in lines if line not in updated]


class TestMessages:
    def should_report_no_match_as_a_warning_on_stdout(self, run_cli, workspace):
        lonely = workspace / "lonely"
        (lonely / "tools").mkdir(parents=True)
        (lonely / "tools" / "only.sh").write_text("x\n")

        result = run_cli("sync_file", ["lonely/tools/only.sh"], cwd=workspace)

        assert result.returncode == 0
        assert messages(result.stdout) == [
            ("log", "Searching for files matching: */tools/only.sh"), ("log", "Source: lonely/tools/only.sh"),
            ("plain", ""), ("warn", "No matching files found")]
        assert result.stderr == ""

    def should_log_each_update_and_the_summary_on_stdout(self, run_cli, workspace):
        result = run_cli("sync_file", [f"alpha/{SCRIPT}"], cwd=workspace)

        updated, others = updates_first(messages(result.stdout))
        assert result.returncode == 0
        assert updated == [("log", f"Updated: ./{project}/{SCRIPT}") for project in ("beta", "gamma")]
        assert others == [
            ("log", f"Searching for files matching: */{SCRIPT}"), ("log", f"Source: alpha/{SCRIPT}"), ("plain", ""),
            ("log", "Found 2 matching file(s)"), ("plain", ""), ("plain", ""),
            ("log", "Summary: 2 file(s) updated, 0 file(s) failed")]
        assert result.stderr == ""

    @pytest.mark.parametrize("failing_cp, failed", [(COPY_FAILING_FOR_BETA, ["beta"]), ("exit 1", ["beta", "gamma"])])
    def should_report_each_failed_copy_as_an_error_on_stderr_and_exit_with_their_count(
            self, run_cli, workspace, failing_cp, failed):
        result = run_cli("sync_file", [f"alpha/{SCRIPT}"], cwd=workspace, mock_bins={"cp": failing_cp})

        assert result.returncode == len(failed)
        assert sorted(messages(result.stderr)) == [("error", f"Failed to update: ./{project}/{SCRIPT}")
                                                   for project in failed]
        assert messages(result.stdout)[-1] == (
            "log", f"Summary: {2 - len(failed)} file(s) updated, {len(failed)} file(s) failed")

    def should_ask_for_a_source_file_with_the_usage_on_stdout_and_the_error_on_stderr(self, run_cli, workspace):
        result = run_cli("sync_file", [""], cwd=workspace)

        assert result.returncode == 1
        assert messages(result.stderr) == [("error", "No source file provided")]
        assert result.stdout.startswith("Usage: sync_file <source_file>\n")
        assert {level for level, _ in messages(result.stdout)} == {"plain"}

    def should_reject_a_source_file_that_does_not_exist(self, run_cli, workspace):
        result = run_cli("sync_file", ["alpha/missing.sh"], cwd=workspace)

        assert result.returncode == 1
        assert messages(result.stderr) == [("error", "Source file does not exist: alpha/missing.sh")]
        assert result.stdout == ""

    def should_reject_a_source_file_that_is_not_readable(self, run_cli):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "alpha" / SCRIPT
            source.parent.mkdir(parents=True)
            source.write_text("x\n")
            source.chmod(0)
            if os.access(source, os.R_OK):
                pytest.skip("root and some mounts read a file whatever its mode")

            result = run_cli("sync_file", [f"alpha/{SCRIPT}"], cwd=directory)

        assert result.returncode == 1
        assert messages(result.stderr) == [("error", f"Source file is not readable: alpha/{SCRIPT}")]
        assert result.stdout == ""

    def should_reject_a_source_file_without_a_directory(self, run_cli, workspace):
        (workspace / "flat.sh").write_text("x\n")

        result = run_cli("sync_file", ["flat.sh"], cwd=workspace)

        assert result.returncode == 1
        assert messages(result.stderr) == [("error", "Source file must contain at least one directory separator"),
                                           ("error", "Expected format: project/path/to/file.sh")]
        assert result.stdout == ""

    @pytest.mark.parametrize("arguments", [[], ["-h"], ["--help"]])
    def should_print_the_usage_on_stdout_without_a_log_line_for_help(self, run_cli, workspace, arguments):
        result = run_cli("sync_file", arguments, cwd=workspace)

        assert result.returncode == 0
        assert result.stdout.startswith("Usage: sync_file <source_file>\n")
        assert {level for level, _ in messages(result.stdout)} == {"plain"}
        assert result.stderr == ""
