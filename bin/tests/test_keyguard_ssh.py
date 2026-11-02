import pytest

from bin.tests.conftest import BIN_DIR, _run_in_mocked_env

HOST = "git.example.com"
KEYGUARD_SOCKET = "/tmp/keyguard-test.sock"
UPLOAD_PACK = "git-upload-pack 'group/project.git'"
WRAPPER = [str(BIN_DIR / "keyguard-ssh")]


def _lines(path):
    return path.read_text().splitlines() if path.exists() else []


@pytest.fixture
def keyguard_ssh(tmp_path, git_env):
    ssh_calls = tmp_path / "ssh.calls"
    keyguard_calls = tmp_path / "keyguard.calls"

    def _run(command, agent_has_key=False, identity_file=None, keyguard_loads=True):
        if identity_file:
            key = tmp_path / ".ssh" / identity_file
            key.parent.mkdir(exist_ok=True)
            key.touch()
        mocks = {
            "ssh": (
                f'echo "SSH_AUTH_SOCK=${{SSH_AUTH_SOCK:-}} $*" >> "{ssh_calls}"\n'
                'if [ "$1" = "-G" ]; then\n'
                f'    printf "user git\\nhostname {HOST}\\nidentityfile ~/.ssh/id_ed25519\\n"\n'
                "fi"
            ),
            "ssh-add": f"exit {0 if agent_has_key else 1}",
            "keyguard-ssh-agent": (
                f'echo "$*" >> "{keyguard_calls}"\n'
                + (f'echo "export SSH_AUTH_SOCK={KEYGUARD_SOCKET}"' if keyguard_loads
                   else 'echo "approval timed out" >&2; exit 1')
            ),
        }
        env = {**git_env, "HOME": str(tmp_path), "SSH_AUTH_SOCK": "", "GIT_SSH_COMMAND": "keyguard-ssh"}
        result = _run_in_mocked_env(command, tmp_path, env, mocks, None, True)
        connections = [call for call in _lines(ssh_calls) if " -G " not in f"{call} "]
        return result, connections, _lines(keyguard_calls)
    return _run


def should_connect_with_the_identity_file_ssh_names_for_the_host_without_asking_keyguard(keyguard_ssh):
    result, connections, asked = keyguard_ssh([*WRAPPER, f"git@{HOST}", UPLOAD_PACK], identity_file="id_ed25519")

    assert (result.returncode, connections, asked) == (0, [f"SSH_AUTH_SOCK= git@{HOST} {UPLOAD_PACK}"], [])


def should_connect_with_the_key_the_agent_holds_without_asking_keyguard(keyguard_ssh):
    result, connections, asked = keyguard_ssh([*WRAPPER, f"git@{HOST}", UPLOAD_PACK], agent_has_key=True)

    assert (result.returncode, len(connections), asked) == (0, 1, [])


def should_ask_keyguard_despite_a_key_on_disk_that_ssh_would_not_offer_to_the_host(keyguard_ssh):
    _, _, asked = keyguard_ssh([*WRAPPER, f"git@{HOST}", UPLOAD_PACK], identity_file="id_ed25519_other")

    assert len(asked) == 1


def should_load_the_keyguard_key_for_the_host_and_connect_through_its_agent_when_no_key_exists(keyguard_ssh):
    result, connections, asked = keyguard_ssh([*WRAPPER, f"git@{HOST}", UPLOAD_PACK])

    assert result.returncode == 0
    assert asked == [f"GITLAB_SSH_KEY_BASE64 GITLAB_SSH_KEY_PASSPHRASE {HOST}"]
    assert connections == [f"SSH_AUTH_SOCK={KEYGUARD_SOCKET} git@{HOST} {UPLOAD_PACK}"]


def should_fail_like_ssh_without_connecting_when_the_keyguard_key_does_not_load(keyguard_ssh):
    result, connections, _ = keyguard_ssh([*WRAPPER, f"git@{HOST}", UPLOAD_PACK], keyguard_loads=False)

    assert (result.returncode, connections) == (255, [])
    assert "approval timed out" in result.stderr


def should_answer_gits_option_probe_without_asking_keyguard(keyguard_ssh):
    result, _, asked = keyguard_ssh([*WRAPPER, "-G", "-o", "SendEnv=GIT_PROTOCOL", f"git@{HOST}"])

    assert (result.returncode, asked) == (0, [])
    assert f"hostname {HOST}" in result.stdout


def should_ask_keyguard_once_when_git_reaches_a_remote_through_the_wrapper(keyguard_ssh):
    _, connections, asked = keyguard_ssh(["git", "ls-remote", f"git@{HOST}:group/project.git"])

    assert len(asked) == 1
    assert connections == [f"SSH_AUTH_SOCK={KEYGUARD_SOCKET} -o SendEnv=GIT_PROTOCOL git@{HOST} {UPLOAD_PACK}"]
