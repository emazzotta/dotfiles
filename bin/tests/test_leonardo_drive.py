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
