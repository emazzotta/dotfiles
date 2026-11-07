import json
import os
import time

SESSION = "4a015f0f-199b-4270-9c06-fecc5d85b976"
OTHER = "9b2c4d1e-0f3a-4b5c-8d7e-6f1a2b3c4d5e"
STATUS = {
    "session_id": SESSION,
    "context_window": {"used_percentage": 41.7, "context_window_size": 1000000},
    "rate_limits": {"five_hour": {"used_percentage": 24, "resets_at": 1738425600}},
}
EIGHT_DAYS = 8 * 24 * 3600


def run(run_cli, tmp_path, status, args=None):
    return run_cli("claude-statusline", args or [], env_extra={"CLAUDE_CONFIG_DIR": str(tmp_path / "claude")},
                   stdin=json.dumps(status, indent=2))


def should_save_the_status_under_its_session_and_hand_the_same_input_to_the_status_line(run_cli, tmp_path):
    result = run(run_cli, tmp_path, STATUS, ["sh", "-c", "printf 'line: '; tr -d ' \\n'"])

    saved = json.loads((tmp_path / "claude" / "statusline" / f"{SESSION}.json").read_text())
    assert (result.returncode, result.stdout[:23], saved) == (0, 'line: {"session_id":"4a', STATUS)


def should_save_nothing_when_the_session_id_is_not_one(run_cli, tmp_path):
    result = run(run_cli, tmp_path, {**STATUS, "session_id": "../../escape"})

    assert (result.returncode, list((tmp_path / "claude").glob("**/*.json"))) == (0, [])


def should_drop_statuses_older_than_a_week_when_a_new_session_starts(run_cli, tmp_path):
    folder = tmp_path / "claude" / "statusline"
    folder.mkdir(parents=True)
    old, recent = folder / f"{OTHER}.json", folder / f".{OTHER}.abc123"
    for file in (old, recent):
        file.write_text("{}")
    long_ago = time.time() - EIGHT_DAYS
    os.utime(old, (long_ago, long_ago))

    run(run_cli, tmp_path, STATUS)

    assert sorted(path.name for path in folder.iterdir()) == sorted([recent.name, f"{SESSION}.json"])
