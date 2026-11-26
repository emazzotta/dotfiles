import pytest

INTERACTION_NOT_ALLOWED = 36
WRONG_PASSPHRASE = 51
ITEM_NOT_FOUND = 44
VPN_SECRET_ITEM = "VPN:LeonardoVPNSecret"

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
        if [ -e "$KEYCHAIN_STATE/empty" ] && [ ! -e "$KEYCHAIN_STATE/item-$service" ]; then
            exit {ITEM_NOT_FOUND}
        fi
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
    add-generic-password)
        shift
        while [ $# -gt 0 ]; do
            [ "$1" = -s ] && touch "$KEYCHAIN_STATE/item-$2"
            shift
        done
        ;;
esac
'''

CALLER = '''#!/bin/bash
set -euo pipefail
source leonardo_account
echo "account=$AD_ACCOUNT"
'''

VPN_CALLER = '''#!/bin/bash
set -euo pipefail
source leonardo_account
load_vpn_shared_secret
echo "vpn=$VPN_SHARED_SECRET"
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
    return lambda stdin=None: run_script(caller, env_extra={"KEYCHAIN_STATE": str(keychain)}, stdin=stdin)


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

    def should_ask_only_for_the_ad_login_when_a_tool_needs_no_vpn(self, source_account, keychain):
        (keychain / "empty").touch()

        result = source_account(stdin="first.last\nad-password\n")

        assert result.returncode == 0, result.stderr
        assert "account=first.last" in result.stdout
        assert VPN_SECRET_ITEM not in security_calls(keychain)

    def should_ask_for_the_vpn_secret_when_a_tool_loads_it(self, tmp_path, run_script, keychain):
        (keychain / "empty").touch()
        caller = tmp_path / "vpn_caller"
        caller.write_text(VPN_CALLER)

        result = run_script(caller, env_extra={"KEYCHAIN_STATE": str(keychain)},
                            stdin="first.last\nad-password\nvpn-secret\n")

        assert result.returncode == 0, result.stderr
        assert "vpn=secret" in result.stdout
        assert f"-s {VPN_SECRET_ITEM} -w vpn-secret" in security_calls(keychain)
