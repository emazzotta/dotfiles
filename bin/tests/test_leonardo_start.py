import os
import pty
import subprocess

import pytest

from bin.tests.conftest import BIN_DIR, marker_mocks

PERSONAL_LOGIN = "me@example.com"
TAILSCALE_STATUS = ('{"BackendState":"Running","Self":{"UserID":7},'
                    f'"User":{{"7":{{"LoginName":"{PERSONAL_LOGIN}"}}}}}}')
SKIPPED_PERSONAL = "Tailscale on personal account - skipping disconnect"
NOT_SUPPLIED = "PRIMARY_EMAIL is not set and keyguard did not supply it"
ENVIFY_SUPPLIES = f'echo envify >> "$CALLS"; export PRIMARY_EMAIL={PERSONAL_LOGIN}'
ENVIFY_FAILS = 'echo envify >> "$CALLS"; echo "Error: param server unreachable" >&2; return 1'
ENVIFY_LEAVES_EMPTY = 'echo envify >> "$CALLS"; return 0'


def disconnect_mocks(tmp_path, envify):
    return {
        **marker_mocks(tmp_path, "leonardo_drive", "leonardo_vpn_toggle", "scutil"),
        "leonardo_account": "GREEN= YELLOW= RED= RESET=",
        "envify": envify.replace("$CALLS", str(tmp_path / "calls")),
        "tailscale": f'''case "$1" in
    status) echo '{TAILSCALE_STATUS}' ;;
    *) echo "tailscale $*" >> "{tmp_path / "calls"}" ;;
esac''',
    }


def calls(tmp_path):
    calls_file = tmp_path / "calls"
    return calls_file.read_text().splitlines() if calls_file.exists() else []


def run_on_terminal(tmp_path, create_mock_bin, mocks, typed):
    for name, body in mocks.items():
        create_mock_bin(name, body)
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{BIN_DIR}:{os.environ['PATH']}", "PRIMARY_EMAIL": ""}
    leader, follower = pty.openpty()
    try:
        os.write(leader, typed.encode())
        return subprocess.run([str(BIN_DIR / "leonardo_start"), "--disconnect"], stdin=follower,
                              capture_output=True, text=True, env=env, timeout=30)
    finally:
        os.close(leader)
        os.close(follower)


class TestLeonardoStart:
    def should_print_usage_for_help_before_loading_any_credential(self, run_cli, tmp_path):
        mocks = marker_mocks(tmp_path, "leonardo_account", "envify", "host-resolver",
                             "leonardo_vpn_toggle", "leonardo_drive", "tailscale", "scutil")

        result = run_cli("leonardo_start", ["--help"], mock_bins=mocks, isolate_path=True)

        assert result.returncode == 0
        assert "--disconnect" in result.stdout
        assert not (tmp_path / "calls").exists()


class TestPrimaryEmail:
    def should_connect_without_loading_or_asking_for_the_address(self, run_cli, tmp_path):
        mocks = {
            **disconnect_mocks(tmp_path, ENVIFY_FAILS),
            **marker_mocks(tmp_path, "tailscale-toggle-exit-node"),
            "host-resolver": "echo 10.0.0.1",
        }

        result = run_cli("leonardo_start", [], env_extra={"PRIMARY_EMAIL": ""}, mock_bins=mocks,
                         isolate_path=True, stdin="")

        assert result.returncode == 0, result.stderr
        assert "envify" not in calls(tmp_path)
        assert "leonardo_drive" in calls(tmp_path)

    def should_use_the_address_already_set_without_calling_envify(self, run_cli, tmp_path):
        mocks = disconnect_mocks(tmp_path, ENVIFY_FAILS)

        result = run_cli("leonardo_start", ["--disconnect"], env_extra={"PRIMARY_EMAIL": PERSONAL_LOGIN},
                         mock_bins=mocks, isolate_path=True, stdin="")

        assert result.returncode == 0
        assert SKIPPED_PERSONAL in result.stdout
        assert "envify" not in calls(tmp_path)

    def should_load_the_address_through_envify_when_it_is_not_set(self, run_cli, tmp_path):
        mocks = disconnect_mocks(tmp_path, ENVIFY_SUPPLIES)

        result = run_cli("leonardo_start", ["--disconnect"], env_extra={"PRIMARY_EMAIL": ""},
                         mock_bins=mocks, isolate_path=True, stdin="")

        assert result.returncode == 0
        assert SKIPPED_PERSONAL in result.stdout
        assert "envify" in calls(tmp_path)

    @pytest.mark.parametrize("envify", [ENVIFY_FAILS, ENVIFY_LEAVES_EMPTY], ids=["fails", "leaves_it_empty"])
    def should_explain_how_to_set_the_address_and_fail_without_a_terminal(self, run_cli, tmp_path, envify):
        mocks = disconnect_mocks(tmp_path, envify)

        result = run_cli("leonardo_start", ["--disconnect"], env_extra={"PRIMARY_EMAIL": ""},
                         mock_bins=mocks, isolate_path=True, stdin="")

        assert result.returncode == 1
        assert NOT_SUPPLIED in result.stderr
        assert "export PRIMARY_EMAIL=" in result.stderr
        assert "leonardo_drive" not in calls(tmp_path)

    def should_ask_for_the_address_on_a_terminal_and_use_it_for_this_run(self, tmp_path, create_mock_bin):
        mocks = disconnect_mocks(tmp_path, ENVIFY_FAILS)

        result = run_on_terminal(tmp_path, create_mock_bin, mocks, f"{PERSONAL_LOGIN}\n")

        assert result.returncode == 0
        assert NOT_SUPPLIED in result.stderr
        assert f"export PRIMARY_EMAIL={PERSONAL_LOGIN}" in result.stderr
        assert SKIPPED_PERSONAL in result.stdout

    def should_fail_when_the_answer_on_the_terminal_is_empty(self, tmp_path, create_mock_bin):
        mocks = disconnect_mocks(tmp_path, ENVIFY_FAILS)

        result = run_on_terminal(tmp_path, create_mock_bin, mocks, "\n")

        assert result.returncode == 1
        assert "No email address entered" in result.stderr
        assert "leonardo_drive" not in calls(tmp_path)
