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
