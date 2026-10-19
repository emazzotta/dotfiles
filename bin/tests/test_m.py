import json

import pytest

TOOLS = ("make", "mvn", "bun", "npm", "pnpm", "yarn")


@pytest.fixture
def m(run_bash, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    calls = tmp_path / "calls"

    def _run(*args, failing=None):
        check = f'\n[ "$*" != "{failing}" ]' if failing else ""
        mocks = {tool: f'echo "{tool} $*" >> "{calls}"{check}' for tool in TOOLS}
        return run_bash("m", list(args), mock_bins=mocks, isolate_path=True, cwd=work)

    _run.work = work
    _run.calls = lambda: calls.read_text().splitlines() if calls.exists() else []
    return _run


def write_scripts(directory, *names):
    scripts = {name: "true" for name in names}
    (directory / "package.json").write_text(json.dumps({"scripts": scripts}))


class TestBuildFile:
    @pytest.mark.parametrize("files, tool", [
        (["Makefile"], "make"),
        (["Makefile", "package.json"], "make"),
        (["pom.xml"], "mvn"),
        (["pom.xml", "package.json"], "mvn"),
    ])
    def should_hand_every_argument_to_the_tool_of_the_first_build_file(self, m, files, tool):
        for name in files:
            (m.work / name).touch()

        result = m("clean", "install")

        assert result.returncode == 0, result.stderr
        assert m.calls() == [f"{tool} clean install"]

    def should_fail_without_a_build_file(self, m):
        result = m("build")

        assert result.returncode == 1
        assert "package.json" in result.stderr
        assert m.calls() == []


class TestPackageJson:
    def should_list_the_scripts_without_a_goal(self, m):
        write_scripts(m.work, "build")

        m()

        assert m.calls() == ["bun run"]

    def should_run_the_scripts_in_the_order_given(self, m):
        write_scripts(m.work, "build", "test")

        result = m("test", "build")

        assert result.returncode == 0, result.stderr
        assert m.calls() == ["bun run test", "bun run build"]

    def should_install_the_dependencies_after_the_clean_script(self, m):
        write_scripts(m.work, "clean")

        m("clean", "install")

        assert m.calls() == ["bun run clean", "bun install"]

    def should_hand_a_command_and_its_arguments_to_the_package_manager(self, m):
        write_scripts(m.work, "build")

        m("add", "left-pad")

        assert m.calls() == ["bun add left-pad"]

    def should_pass_the_flags_after_a_script_and_what_follows_to_that_script(self, m):
        write_scripts(m.work, "build", "test")

        m("build", "test", "--watch", "src")

        assert m.calls() == ["bun run build", "bun run test --watch src"]

    def should_stop_at_the_first_failing_script(self, m):
        write_scripts(m.work, "lint", "test")

        result = m("lint", "test", failing="run lint")

        assert result.returncode == 1
        assert m.calls() == ["bun run lint"]

    def should_run_nothing_when_package_json_is_invalid(self, m):
        (m.work / "package.json").write_text("{")

        result = m("build")

        assert result.returncode != 0
        assert m.calls() == []

    @pytest.mark.parametrize("lockfile, manager", [
        ("bun.lock", "bun"),
        ("package-lock.json", "npm"),
        ("pnpm-lock.yaml", "pnpm"),
        ("yarn.lock", "yarn"),
    ])
    def should_use_the_package_manager_of_the_lockfile(self, m, lockfile, manager):
        write_scripts(m.work, "build")
        (m.work / lockfile).touch()

        m("build")

        assert m.calls() == [f"{manager} run build"]


class TestComplete:
    def should_list_the_scripts_of_package_json(self, m):
        write_scripts(m.work, "test", "render:bumble")

        result = m("--complete")

        assert result.stdout.splitlines() == ["render:bumble", "test"]

    def should_list_the_targets_of_the_makefile_first(self, m):
        (m.work / "Makefile").write_text(".PHONY: build test\nbuild:\n\ttrue\ntest: build\n\ttrue\n")
        write_scripts(m.work, "dev")

        result = m("--complete")

        assert result.stdout.splitlines() == ["build", "test"]

    def should_list_no_scripts_where_maven_builds(self, m):
        (m.work / "pom.xml").touch()
        write_scripts(m.work, "dev")

        result = m("--complete")

        assert result.stdout == ""

    def should_list_nothing_and_succeed_when_package_json_is_invalid(self, m):
        (m.work / "package.json").write_text("{")

        result = m("--complete")

        assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
