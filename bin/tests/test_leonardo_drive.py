SECURITY_MOCK = "echo keychain-value"


class TestLeonardoDrive:
    def test_should_report_mounted_when_the_mount_table_lists_the_path_in_another_case(self, run_bash, tmp_path):
        mount_mock = f'echo "//user@192.168.5.155/Daten on {tmp_path / "daten"} (smbfs, nodev, nosuid)"'

        result = run_bash(
            "leonardo_drive", ["--status"],
            env_extra={"HOME": str(tmp_path)},
            mock_bins={"mount": mount_mock, "security": SECURITY_MOCK},
            isolate_path=True,
        )

        assert result.returncode == 0
        assert "is mounted" in result.stdout

    def test_should_print_usage_for_help_before_reading_the_keychain(self, run_bash,
                                                                    tmp_path):
        keychain_reads = tmp_path / "keychain-reads"

        result = run_bash(
            "leonardo_drive", ["--help"],
            env_extra={"HOME": str(tmp_path)},
            mock_bins={"security": f'echo read >> "{keychain_reads}"'},
            isolate_path=True,
        )

        assert result.returncode == 0
        assert "--mount" in result.stdout
        assert not keychain_reads.exists()
