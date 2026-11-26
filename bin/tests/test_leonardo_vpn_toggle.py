from bin.tests.conftest import marker_mocks


class TestLeonardoVpnToggle:
    def should_print_usage_for_help_before_reading_the_keychain(self, run_cli, tmp_path):
        mocks = marker_mocks(tmp_path, "leonardo_account", "security", "scutil", "sudo",
                             "leonardo_drive")

        result = run_cli("leonardo_vpn_toggle", ["--help"], mock_bins=mocks, isolate_path=True)

        assert result.returncode == 0
        assert "--enable" in result.stdout
        assert "--disable" in result.stdout
        assert not (tmp_path / "calls").exists()

    def should_load_the_vpn_secret_before_connecting(self, run_cli, tmp_path):
        calls = tmp_path / "calls"
        mocks = {
            "leonardo_account": (
                "GREEN= YELLOW= RED= RESET=\n"
                f'load_vpn_shared_secret() {{ echo load-vpn-secret >> "{calls}"; VPN_SHARED_SECRET=s3cret; }}'
            ),
            "scutil": (
                f'case "$2" in\n'
                f'    status) if [ -e "{tmp_path / "started"}" ]; then echo Connected; else echo Disconnected; fi ;;\n'
                f'    start) echo "scutil $*" >> "{calls}"; touch "{tmp_path / "started"}" ;;\n'
                f'esac'
            ),
        }

        result = run_cli("leonardo_vpn_toggle", ["--enable"], mock_bins=mocks, isolate_path=True)

        assert result.returncode == 0, result.stderr
        assert calls.read_text().splitlines() == [
            "load-vpn-secret",
            "scutil --nc start --secret s3cret LeonardoVPN",
        ]
