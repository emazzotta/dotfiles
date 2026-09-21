import pytest

HOST_RESOLVER_MOCK = "echo 100.75.167.92"
ENVIFY_MOCK = "export DEVBOX_SAMBA_PASSWORD=secret"


@pytest.fixture
def devbox_drive(run_bash, tmp_path):
    def _run(args, mounted_at=None, expect_log=None):
        mount_mock = (
            f'echo "//emanuele@devbox-1.example/Devbox on {mounted_at} (smbfs, nodev, nosuid)"'
            if mounted_at else "true"
        )
        expect_mock = f'echo "$@" >> "{expect_log}"' if expect_log else "true"
        return run_bash(
            "devbox-drive", args,
            env_extra={"HOME": str(tmp_path)},
            mock_bins={
                "mount": mount_mock,
                "expect": expect_mock,
                "host-resolver": HOST_RESOLVER_MOCK,
                "envify": ENVIFY_MOCK,
            },
            isolate_path=True,
        )
    return _run


class TestDevboxDrive:
    def test_should_report_mounted_when_the_mount_table_lists_the_path_in_another_case(self, devbox_drive, tmp_path):
        result = devbox_drive(["--status"], mounted_at=tmp_path / "devbox")

        assert result.returncode == 0
        assert "is mounted" in result.stdout

    def test_should_refuse_to_mount_over_a_directory_that_has_contents(self, devbox_drive, tmp_path):
        mount_point = tmp_path / "Devbox"
        mount_point.mkdir()
        (mount_point / "notes.txt").write_text("keep me")
        expect_log = tmp_path / "expect.log"

        result = devbox_drive(["--mount"], expect_log=expect_log)

        assert result.returncode == 1
        assert "not empty" in result.stderr
        assert not expect_log.exists()

    def test_should_treat_a_mount_point_holding_only_a_ds_store_as_empty(self, devbox_drive, tmp_path):
        mount_point = tmp_path / "Devbox"
        mount_point.mkdir()
        (mount_point / ".DS_Store").write_bytes(b"")
        expect_log = tmp_path / "expect.log"

        devbox_drive(["--mount"], expect_log=expect_log)

        assert "mount_smbfs" in expect_log.read_text()
