import pytest

INTERACTION_NOT_ALLOWED = 36
WRONG_PASSPHRASE = 51

SECURITY_MOCK = f'''
echo "$*" >> "$KEYCHAIN_STATE/calls"
case "$1" in
    show-keychain-info)
        if [ -e "$KEYCHAIN_STATE/locked" ]; then
            echo "security: SecKeychainCopySettings: User interaction is not allowed." >&2
            exit {INTERACTION_NOT_ALLOWED}
        fi
        ;;
    unlock-keychain)
        if [ -e "$KEYCHAIN_STATE/unlock_fails" ]; then
            echo "security: SecKeychainUnlock: The user name or passphrase you entered is not correct." >&2
            exit {WRONG_PASSPHRASE}
        fi
        /bin/rm -f "$KEYCHAIN_STATE/locked"
        ;;
    find-generic-password)
        shift
        service=""
        wants_secret=false
        while [ $# -gt 0 ]; do
            case "$1" in
                -a) shift ;;
                -s) service="$2"; shift ;;
                -w) wants_secret=true ;;
            esac
            shift
        done
        [ "$wants_secret" = true ] || exit 0
        if [ -e "$KEYCHAIN_STATE/locked" ]; then
            echo "security: SecKeychainSearchCopyNext: User interaction is not allowed." >&2
            exit {INTERACTION_NOT_ALLOWED}
        fi
        if [ -e "$KEYCHAIN_STATE/read_fails" ]; then
            echo "security: SecKeychainItemCopyContent: The user name or passphrase you entered is not correct." >&2
            exit {WRONG_PASSPHRASE}
        fi
        if [ "$service" = LeonardoActiveDirectoryUsername ]; then
            echo first.last
        else
            echo secret
        fi
        ;;
esac
'''

CALLER = '''#!/bin/bash
set -euo pipefail
source leonardo_account
echo "account=$AD_ACCOUNT"
'''


@pytest.fixture
def keychain(tmp_path, create_mock_bin):
    create_mock_bin("security", SECURITY_MOCK)
    state = tmp_path / "keychain"
    state.mkdir()
    return state


@pytest.fixture
def source_account(tmp_path, run_script, keychain):
    caller = tmp_path / "caller"
    caller.write_text(CALLER)
    return lambda: run_script(caller, env_extra={"KEYCHAIN_STATE": str(keychain)})


def security_calls(keychain):
    calls = keychain / "calls"
    return calls.read_text() if calls.exists() else ""


class TestLeonardoAccount:
    def should_read_the_account_without_unlocking_a_reachable_keychain(self, source_account, keychain):
        result = source_account()

        assert result.returncode == 0, result.stderr
        assert "account=first.last" in result.stdout
        assert "unlock-keychain" not in security_calls(keychain)

    def should_unlock_the_keychain_when_this_session_cannot_reach_it(self, source_account, keychain):
        (keychain / "locked").touch()

        result = source_account()

        assert result.returncode == 0, result.stderr
        assert "account=first.last" in result.stdout
        assert "unlock-keychain" in security_calls(keychain)

    def should_stop_when_the_keychain_cannot_be_unlocked(self, source_account, keychain):
        (keychain / "locked").touch()
        (keychain / "unlock_fails").touch()

        result = source_account()

        assert result.returncode != 0
        assert "account=" not in result.stdout
        assert "add-generic-password" not in security_calls(keychain)

    def should_stop_and_show_the_keychain_error_when_a_read_fails(self, source_account, keychain):
        (keychain / "read_fails").touch()

        result = source_account()

        assert result.returncode != 0
        assert "account=" not in result.stdout
        assert "passphrase you entered is not correct" in result.stderr
        assert "add-generic-password" not in security_calls(keychain)
