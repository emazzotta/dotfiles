import json
import os
from pathlib import Path

import pytest

TRANSCRIPT = Path(".system_generated") / "logs" / "transcript.jsonl"
METADATA = Path("cache") / "conversation_metadata.json"


def user_record(text):
    wrapped = f"<USER_REQUEST>\n{text}\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nThe current local time is: now.\n</ADDITIONAL_METADATA>"
    return {"source": "USER_EXPLICIT", "type": "USER_INPUT", "status": "DONE", "content": wrapped}


def reply_record(text):
    return {"source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "content": text}


def tool_call_record():
    return {"source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "tool_calls": [{"name": "run_command"}]}


def tool_output_record(text):
    return {"source": "MODEL", "type": "GENERIC", "status": "DONE", "content": text}


class Store:
    def __init__(self, root, workspace):
        self.root = root
        self.workspace = workspace
        (root / "cache").mkdir(parents=True)

    def add(self, sid, records, mtime, title="", preview="", workspaces=None, internal=False):
        transcript = self.root / "brain" / sid / TRANSCRIPT
        transcript.parent.mkdir(parents=True, exist_ok=True)
        transcript.write_text("".join(json.dumps(record) + "\n" for record in records))
        os.utime(transcript, (mtime, mtime))
        listed = json.loads((self.root / METADATA).read_text())["conversations"] if (self.root / METADATA).exists() else {}
        uris = workspaces if workspaces is not None else [f"file://{self.workspace}"]
        listed[sid] = {
            "summary": {"ID": sid, "Title": title, "Preview": preview, "WorkspaceURIs": uris, "Internal": internal},
            "is_internal": internal,
        }
        (self.root / METADATA).write_text(json.dumps({"conversations": listed}))
        return transcript


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    folder = tmp_path / "work"
    folder.mkdir()
    monkeypatch.chdir(folder)
    return folder


@pytest.fixture
def store(tmp_path, workdir):
    return Store(tmp_path / "agy", workdir)


@pytest.fixture
def resume(load_script, monkeypatch, store, tmp_path):
    monkeypatch.setenv("AGY_DIR", str(store.root))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return load_script("agy-resume")


@pytest.fixture
def indexed(resume, store, workdir):
    store.add("adjacent", [user_record("fix the DOCKER compose stack"), reply_record("ok")], mtime=1000, title="Docker stack")
    store.add("scattered", [user_record("docker is fine"), reply_record("we compose later")], mtime=2000, title="Compose later")
    store.add("unrelated", [user_record("something else entirely")], mtime=3000, title="Other")
    return resume.build_sessions(store.root, workdir, all_projects=False)


def ids_of(output):
    return [line.split("\t")[1] for line in output.splitlines()]


class TestIndexing:
    def test_should_take_the_title_agy_gave_the_conversation(self, indexed):
        titles = {session.sid: session.title for session in indexed}

        assert titles["adjacent"] == "Docker stack"

    def test_should_fall_back_to_the_preview_when_agy_gave_no_title(self, resume, store, workdir):
        store.add("untitled", [user_record("hello")], mtime=1000, preview="hello preview")

        titles = {s.sid: s.title for s in resume.build_sessions(store.root, workdir, all_projects=False)}

        assert titles["untitled"] == "hello preview"

    def test_should_fall_back_to_the_first_prompt_when_agy_gave_no_title_or_preview(self, resume, store, workdir):
        store.add("bare", [user_record("adapt cl"), reply_record("done")], mtime=1000)

        titles = {s.sid: s.title for s in resume.build_sessions(store.root, workdir, all_projects=False)}

        assert titles["bare"] == "adapt cl"

    def test_should_fall_back_to_a_placeholder_when_nobody_asked_anything(self, resume, store, workdir):
        store.add("quiet", [reply_record("nobody asked")], mtime=1000)

        titles = {s.sid: s.title for s in resume.build_sessions(store.root, workdir, all_projects=False)}

        assert titles["quiet"] == resume.NO_PROMPT

    def test_should_index_the_prompt_without_the_metadata_agy_wraps_around_it(self, indexed):
        content = {session.sid: session.content_lower for session in indexed}

        assert content["adjacent"] == "fix the docker compose stack ok"

    def test_should_not_index_tool_calls_or_tool_output(self, resume, store, workdir):
        store.add("tools", [user_record("run it"), tool_call_record(), tool_output_record("secret output"), reply_record("done")], mtime=1000)

        content = {s.sid: s.content_lower for s in resume.build_sessions(store.root, workdir, all_projects=False)}

        assert content["tools"] == "run it done"

    def test_should_skip_a_line_of_a_transcript_that_is_not_json(self, resume, store, workdir):
        transcript = store.add("torn", [user_record("before")], mtime=1000)
        transcript.write_text(transcript.read_text() + '{"type": "PLANNER_RESP\n' + json.dumps(reply_record("after")) + "\n")

        content = {s.sid: s.content_lower for s in resume.build_sessions(store.root, workdir, all_projects=False)}

        assert content["torn"] == "before after"

    def test_should_skip_conversations_agy_marks_internal(self, resume, store, workdir):
        store.add("hidden", [user_record("background job")], mtime=1000, internal=True)

        sids = {s.sid for s in resume.build_sessions(store.root, workdir, all_projects=False)}

        assert "hidden" not in sids

    def test_should_skip_conversations_that_have_no_transcript(self, resume, store, workdir, indexed):
        (store.root / "brain" / "unrelated" / TRANSCRIPT).unlink()

        sids = {s.sid for s in resume.build_sessions(store.root, workdir, all_projects=False)}

        assert sids == {"adjacent", "scattered"}

    def test_should_list_nothing_when_agy_has_written_no_metadata(self, resume, store, workdir):
        assert resume.build_sessions(store.root / "elsewhere", workdir, all_projects=False) == []

    def test_should_stamp_each_conversation_with_its_transcript_mtime(self, indexed):
        assert {s.sid: s.updated_at for s in indexed} == {"adjacent": 1000, "scattered": 2000, "unrelated": 3000}

    def test_should_reuse_cached_text_when_the_transcript_mtime_is_unchanged(self, resume, store, workdir, indexed):
        store.add("unrelated", [user_record("rewritten behind the cache")], mtime=3000, title="")

        titles = {s.sid: s.title for s in resume.build_sessions(store.root, workdir, all_projects=False)}

        assert titles["unrelated"] == "Other"

    def test_should_reindex_when_the_transcript_mtime_moves_forward(self, resume, store, workdir, indexed):
        store.add("unrelated", [user_record("rewritten and restamped")], mtime=9000, title="")

        titles = {s.sid: s.title for s in resume.build_sessions(store.root, workdir, all_projects=False)}

        assert titles["unrelated"] == "rewritten and restamped"

    def test_should_show_a_title_agy_set_after_the_text_was_cached(self, resume, store, workdir, indexed):
        store.add("unrelated", [user_record("something else entirely")], mtime=3000, title="Renamed")

        titles = {s.sid: s.title for s in resume.build_sessions(store.root, workdir, all_projects=False)}

        assert titles["unrelated"] == "Renamed"


class TestScope:
    @pytest.fixture
    def mixed(self, store, workdir):
        store.add("here", [user_record("in this project")], mtime=1000)
        store.add("there", [user_record("in another project")], mtime=2000, workspaces=["file:///somewhere/else"])
        store.add("nowhere", [user_record("no workspace recorded")], mtime=3000, workspaces=[])

    def test_should_list_only_the_conversations_of_the_current_folder(self, resume, store, workdir, mixed):
        sids = {s.sid for s in resume.build_sessions(store.root, workdir, all_projects=False)}

        assert sids == {"here"}

    def test_should_list_every_conversation_when_asked_for_all_projects(self, resume, store, workdir, mixed):
        sids = {s.sid for s in resume.build_sessions(store.root, workdir, all_projects=True)}

        assert sids == {"here", "there", "nowhere"}

    def test_should_name_the_workspace_of_each_conversation_as_its_project(self, resume, store, workdir, mixed):
        projects = {s.sid: s.project for s in resume.build_sessions(store.root, workdir, all_projects=True)}

        assert projects == {"here": str(workdir), "there": "/somewhere/else", "nowhere": ""}

    def test_should_decode_a_percent_encoded_workspace_uri(self, resume):
        assert resume.workspace_path("file:///tmp/my%20project") == "/tmp/my project"

    def test_should_match_a_conversation_opened_in_several_workspaces_by_any_of_them(self, resume, store, workdir):
        store.add("multi", [user_record("two folders")], mtime=1000, workspaces=["file:///other", f"file://{workdir}"])

        sids = {s.sid for s in resume.build_sessions(store.root, workdir, all_projects=False)}

        assert sids == {"multi"}


class TestSearchCommand:
    def test_should_rank_adjacent_words_above_scattered_words(self, resume, indexed, capsys):
        resume.cmd_search("docker compose", count=10, all_projects=False)

        assert ids_of(capsys.readouterr().out) == ["adjacent", "scattered"]

    def test_should_print_nothing_when_nothing_matches(self, resume, indexed, capsys):
        resume.cmd_search("nonexistent-token", count=10, all_projects=False)

        assert capsys.readouterr().out == ""

    def test_should_list_every_conversation_by_recency_when_the_query_is_blank(self, resume, indexed, capsys):
        resume.cmd_search("", count=10, all_projects=False)

        assert ids_of(capsys.readouterr().out) == ["unrelated", "scattered", "adjacent"]

    def test_should_honour_the_count_limit(self, resume, indexed, capsys):
        resume.cmd_search("", count=2, all_projects=False)

        assert len(ids_of(capsys.readouterr().out)) == 2

    def test_should_match_case_insensitively(self, resume, indexed, capsys):
        resume.cmd_search("DOCKER", count=10, all_projects=False)

        assert set(ids_of(capsys.readouterr().out)) == {"adjacent", "scattered"}

    def test_should_show_the_project_column_only_when_listing_all_projects(self, resume, store, workdir, indexed):
        sessions = resume.build_sessions(store.root, workdir, all_projects=True)

        assert str(workdir) in resume.build_rows(sessions, True, 1)[0]
        assert str(workdir) not in resume.build_rows(sessions, False, 1)[0]


class TestReloadCommand:
    def test_should_quote_the_query_placeholder_for_the_shell(self, resume):
        assert "--search-query={q}" in resume.build_commands(count=50, all_projects=False).reload

    def test_should_pass_the_scope_flag_so_reload_matches_the_initial_list(self, resume):
        assert " -a" in resume.build_commands(count=50, all_projects=True).reload
        assert " -a" not in resume.build_commands(count=50, all_projects=False).reload


class TestPreview:
    def test_should_render_turns_with_role_labels(self, resume, store, indexed):
        rendered = resume.render_preview(store.root, "adjacent")

        assert "user" in rendered and "assistant" in rendered

    def test_should_highlight_query_tokens(self, resume, store, indexed, load_script):
        picker = load_script("session_picker.py")

        assert picker.HIGHLIGHT_ON in resume.render_preview(store.root, "adjacent", "compose")

    def test_should_report_a_missing_conversation_without_raising(self, resume, store):
        assert "not found" in resume.render_preview(store.root, "nope")


class TestPick:
    def run_picker(self, run_cli, store, workdir, home, args=None, fzf="head -n 1"):
        return run_cli(
            "agy-resume", args or [],
            env_extra={"AGY_DIR": str(store.root), "HOME": str(home)},
            mock_bins={"fzf": fzf, "agy": 'printf "%s\\n" "$@"'},
            cwd=workdir,
        )

    def test_should_resume_the_conversation_fzf_returns_and_forward_the_args_after_the_separator(
        self, run_cli, store, workdir, indexed, tmp_path,
    ):
        result = self.run_picker(run_cli, store, workdir, tmp_path / "home", ["--", "--dangerously-skip-permissions"])

        assert result.stdout.splitlines() == ["--conversation", "unrelated", "--dangerously-skip-permissions"]

    def test_should_resume_nothing_when_the_picker_is_cancelled(self, run_cli, store, workdir, indexed, tmp_path):
        result = self.run_picker(run_cli, store, workdir, tmp_path / "home", fzf="exit 130")

        assert (result.returncode, result.stdout) == (1, "")

    def test_should_say_so_when_the_current_folder_has_no_conversation(self, run_cli, store, tmp_path):
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        store.add("other", [user_record("hello")], mtime=1000, workspaces=["file:///not/here"])

        result = self.run_picker(run_cli, store, elsewhere, tmp_path / "home")

        assert result.returncode == 1
        assert "Use -a for all projects" in result.stderr

    def test_should_list_the_other_folders_when_asked_for_all_projects(self, run_cli, store, tmp_path):
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        store.add("other", [user_record("hello")], mtime=1000, workspaces=["file:///not/here"])

        result = self.run_picker(run_cli, store, elsewhere, tmp_path / "home", ["-a"])

        assert result.stdout.splitlines()[:2] == ["--conversation", "other"]

    def test_should_say_so_when_agy_has_stored_no_conversations(self, run_cli, store, workdir, tmp_path):
        result = self.run_picker(run_cli, store, workdir, tmp_path / "home")

        assert result.returncode == 1
        assert "agy conversations not found" in result.stderr
