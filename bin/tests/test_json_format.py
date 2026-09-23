from bin.tests.conftest import marker_mocks


class TestJsonFormat:
    def should_print_usage_for_help_without_touching_the_clipboard(self, run_cli, tmp_path):
        mocks = marker_mocks(tmp_path, "pbpaste", "pbcopy", "jq")

        result = run_cli("json_format", ["--help"], mock_bins=mocks, isolate_path=True)

        assert result.returncode == 0
        assert "--clipboard" in result.stdout
        assert not (tmp_path / "calls").exists()
