import json
import os

import pytest


def write_session(scope, sid, turns, mtime):
    jsonl = scope / f"{sid}.jsonl"
    jsonl.write_text("".join(
        json.dumps({"type": kind, "message": {"content": text}}) + "\n" for kind, text in turns
    ))
    os.utime(jsonl, (mtime, mtime))
    return jsonl


@pytest.fixture
def projects(tmp_path):
    return tmp_path / "projects"


@pytest.fixture
def resume(load_script, monkeypatch, projects):
    monkeypatch.setenv("CLAUDE_PROJECTS", str(projects))
    return load_script("claude-resume")


@pytest.fixture
def scope(projects, monkeypatch, tmp_path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    scope_dir = projects / str(workdir).replace("/", "-")
    scope_dir.mkdir(parents=True)
    return scope_dir


@pytest.fixture
def indexed(resume, scope):
    write_session(scope, "adjacent", [("user", "fix the DOCKER compose stack"), ("assistant", "ok")], mtime=1000)
    write_session(scope, "scattered", [("user", "docker is fine"), ("assistant", "we compose later")], mtime=2000)
    write_session(scope, "unrelated", [("user", "something else entirely")], mtime=3000)
    return resume.build_sessions(resume.resolve_scopes(all_projects=False))


def ids_of(output):
    return [line.split("\t")[1] for line in output.splitlines()]


class TestIndexing:
    def test_should_take_the_first_user_turn_as_the_title(self, resume, indexed):
        titles = {session.sid: session.title for session in indexed}

        assert titles["adjacent"] == "fix the DOCKER compose stack"

    def test_should_lowercase_indexed_content_for_searching(self, resume, indexed):
        content = {session.sid: session.content_lower for session in indexed}

        assert "docker compose" in content["adjacent"]

    def test_should_drop_sessions_whose_file_has_disappeared(self, resume, scope, indexed):
        (scope / "adjacent.jsonl").unlink()

        assert {s.sid for s in resume.build_sessions([scope])} == {"scattered", "unrelated"}

    def test_should_reuse_cached_text_when_mtime_is_unchanged(self, resume, scope, indexed):
        write_session(scope, "unrelated", [("user", "rewritten behind the cache")], mtime=3000)

        titles = {s.sid: s.title for s in resume.build_sessions([scope])}

        assert titles["unrelated"] == "something else entirely"

    def test_should_reindex_when_mtime_moves_forward(self, resume, scope, indexed):
        write_session(scope, "unrelated", [("user", "rewritten and restamped")], mtime=9000)

        titles = {s.sid: s.title for s in resume.build_sessions([scope])}

        assert titles["unrelated"] == "rewritten and restamped"

    def test_should_fall_back_to_a_placeholder_when_there_is_no_user_turn(self, resume, scope):
        write_session(scope, "quiet", [("assistant", "nobody asked")], mtime=1000)

        titles = {s.sid: s.title for s in resume.build_sessions([scope])}

        assert titles["quiet"] == resume.NO_PROMPT


class TestSearchCommand:
    def test_should_rank_adjacent_words_above_scattered_words(self, resume, indexed, capsys):
        resume.cmd_search("docker compose", count=10, all_projects=False)

        assert ids_of(capsys.readouterr().out) == ["adjacent", "scattered"]

    def test_should_print_nothing_when_nothing_matches(self, resume, indexed, capsys):
        resume.cmd_search("nonexistent-token", count=10, all_projects=False)

        assert capsys.readouterr().out == ""

    def test_should_list_every_session_by_recency_when_query_is_blank(self, resume, indexed, capsys):
        resume.cmd_search("", count=10, all_projects=False)

        assert ids_of(capsys.readouterr().out) == ["unrelated", "scattered", "adjacent"]

    def test_should_honour_the_count_limit(self, resume, indexed, capsys):
        resume.cmd_search("", count=2, all_projects=False)

        assert len(ids_of(capsys.readouterr().out)) == 2

    def test_should_match_case_insensitively(self, resume, indexed, capsys):
        resume.cmd_search("DOCKER", count=10, all_projects=False)

        assert set(ids_of(capsys.readouterr().out)) == {"adjacent", "scattered"}


class TestReloadCommand:
    def test_should_quote_the_query_placeholder_for_the_shell(self, resume):
        commands = resume.build_commands(count=50, all_projects=False)

        assert "--search-query={q}" in commands.reload

    def test_should_pass_the_scope_flag_so_reload_matches_the_initial_list(self, resume):
        assert " -a" in resume.build_commands(count=50, all_projects=True).reload
        assert " -a" not in resume.build_commands(count=50, all_projects=False).reload


class TestPreview:
    def test_should_render_turns_with_role_labels(self, resume, scope, indexed):
        rendered = resume.render_preview(scope / "adjacent.jsonl")

        assert "user" in rendered and "assistant" in rendered

    def test_should_highlight_query_tokens(self, resume, scope, indexed, load_script):
        picker = load_script("session_picker.py")

        rendered = resume.render_preview(scope / "adjacent.jsonl", "compose")

        assert picker.HIGHLIGHT_ON in rendered

    def test_should_report_a_missing_session_without_raising(self, resume, indexed, capsys):
        assert resume.cmd_preview("00000000-0000-0000-0000-000000000000", "") == 1
