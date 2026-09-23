from bin.tests.conftest import marker_mocks


class TestTmtoken:
    def should_print_usage_for_help_before_loading_the_database_user(self, run_cli, tmp_path):
        mocks = marker_mocks(tmp_path, "envify", "kubectl")

        result = run_cli("tmtoken", ["--help"], mock_bins=mocks, isolate_path=True)

        assert result.returncode == 0
        assert "--token-only" in result.stdout
        assert not (tmp_path / "calls").exists()
