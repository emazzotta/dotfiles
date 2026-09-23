from bin.tests.conftest import marker_mocks


class TestLeonardoStart:
    def should_print_usage_for_help_before_loading_any_credential(self, run_cli, tmp_path):
        mocks = marker_mocks(tmp_path, "leonardo_account", "envify", "host-resolver",
                             "leonardo_vpn_toggle", "leonardo_drive", "tailscale", "scutil")

        result = run_cli("leonardo_start", ["--help"], mock_bins=mocks, isolate_path=True)

        assert result.returncode == 0
        assert "--disconnect" in result.stdout
        assert not (tmp_path / "calls").exists()
