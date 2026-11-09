import json

import pytest

SESSION = "4a015f0f-199b-4270-9c06-fecc5d85b976"
QUESTIONS = [{"question": "Tea or coffee?", "header": "Drink", "multiSelect": False,
              "options": [{"label": "Tea", "description": "green"}, {"label": "Coffee", "description": "black"}]}]
ASKED = {"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion", "tool_use_id": "toolu_01Abc",
         "tool_input": {"questions": QUESTIONS}}


def hook(run_cli, tmp_path, event):
    return run_cli("claude-question", env_extra={"CLAUDE_CONFIG_DIR": str(tmp_path / "claude")},
                   stdin=json.dumps({"session_id": SESSION, "cwd": "/workspace", **event}, indent=2))


def saved(tmp_path):
    return [json.loads(path.read_text()) for path in (tmp_path / "claude").glob("questions/*.json")]


def should_save_the_questions_and_their_step_under_the_session_when_claude_asks(run_cli, tmp_path):
    result = hook(run_cli, tmp_path, ASKED)

    assert (result.returncode, result.stdout, saved(tmp_path)) == (0, "", [{"id": "toolu_01Abc", "questions": QUESTIONS}])


@pytest.mark.parametrize("event", [
    {"hook_event_name": "PostToolUse", "tool_name": "AskUserQuestion", "tool_use_id": "toolu_01Abc"},
    {"hook_event_name": "PostToolUseFailure", "tool_name": "AskUserQuestion", "tool_use_id": "toolu_01Abc"},
    {"hook_event_name": "PermissionRequest", "tool_name": "Bash", "tool_input": {"command": "ls"}},
    {"hook_event_name": "UserPromptSubmit", "prompt": "hi"},
    {"hook_event_name": "Stop"},
    {"hook_event_name": "SessionEnd", "reason": "exit"},
])
def should_drop_the_questions_once_their_dialog_closes(run_cli, tmp_path, event):
    hook(run_cli, tmp_path, ASKED)

    result = hook(run_cli, tmp_path, event)

    assert (result.returncode, saved(tmp_path)) == (0, [])


@pytest.mark.parametrize("event", [
    {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}},
    {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_use_id": "toolu_02Def"},
    {"hook_event_name": "PermissionRequest", "tool_name": "AskUserQuestion", "tool_input": {"questions": QUESTIONS}},
    {"hook_event_name": "PermissionRequest", "tool_name": "Bash", "agent_id": "a3f9c2e1b7d04e55"},
])
def should_keep_the_questions_while_their_dialog_stays_open(run_cli, tmp_path, event):
    hook(run_cli, tmp_path, ASKED)

    hook(run_cli, tmp_path, event)

    assert saved(tmp_path) == [{"id": "toolu_01Abc", "questions": QUESTIONS}]


@pytest.mark.parametrize("stdin", ["not json", "[]", json.dumps({**ASKED, "session_id": "../../escape"})])
def should_save_nothing_and_never_block_claude_when_the_event_is_not_one(run_cli, tmp_path, stdin):
    result = run_cli("claude-question", env_extra={"CLAUDE_CONFIG_DIR": str(tmp_path / "claude")}, stdin=stdin)

    assert (result.returncode, list((tmp_path / "claude").glob("**/*"))) == (0, [])


def should_print_its_usage_on_help(run_cli):
    result = run_cli("claude-question", ["--help"])

    assert (result.returncode, result.stdout.splitlines()[0]) == (0, "Usage: claude-question")
