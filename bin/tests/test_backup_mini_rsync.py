from pathlib import Path
from types import SimpleNamespace

import pytest

FAILED_TRANSFER = 23


@pytest.fixture
def mini_rsync(load_script):
    return load_script("backup_mini_rsync")


@pytest.fixture
def rsync(mini_rsync, monkeypatch):
    calls = []
    failing_sources = set()

    def run(command, **_):
        calls.append(command)
        return SimpleNamespace(returncode=FAILED_TRANSFER if command[-2] in failing_sources else 0)
    monkeypatch.setattr(mini_rsync.subprocess, "run", run)
    return SimpleNamespace(calls=calls, failing_sources=failing_sources)


@pytest.fixture
def drive(tmp_path):
    root = tmp_path / "source"
    for directory in ("Music", "Backup/Laptop", "Backup/Phone"):
        (root / directory).mkdir(parents=True)
    (root / "notes.txt").write_text("loose file in the root")
    (root / "Backup" / "index.txt").write_text("loose file in a split directory")
    return SimpleNamespace(source=f"{root}/", target=str(tmp_path / "target"))


def run_parallel(mini_rsync, drive):
    subdirectories = mini_rsync.find_subdirectories(drive.source)
    mini_rsync.confirm_and_execute_command(drive.source, drive.target, [], "rsync",
                                           parallel=True, subdirectories=subdirectories)


def anchored_excludes(command):
    return {value for flag, value in zip(command, command[1:]) if flag == "--exclude" and value.startswith("/")}


class TestParallelRsync:
    def should_first_sync_the_whole_drive_except_the_directories_synced_in_parallel(self, mini_rsync, rsync, drive):
        run_parallel(mini_rsync, drive)

        root_pass = rsync.calls[0]
        assert root_pass[:len(mini_rsync.RSYNC_FLAGS) + 1] == ["rsync", *mini_rsync.RSYNC_FLAGS]
        assert "--delete" in root_pass
        assert anchored_excludes(root_pass) == {"/Music/", "/Backup/Laptop/", "/Backup/Phone/"}
        assert root_pass[-2:] == [drive.source, drive.target]

    def should_then_sync_each_split_directory_into_its_place(self, mini_rsync, rsync, drive):
        run_parallel(mini_rsync, drive)

        assert {(command[-2], command[-1]) for command in rsync.calls[1:]} == {
            (f"{drive.source}Music/", f"{drive.target}/Music"),
            (f"{drive.source}Backup/Laptop/", f"{drive.target}/Backup/Laptop"),
            (f"{drive.source}Backup/Phone/", f"{drive.target}/Backup/Phone"),
        }

    def should_escape_wildcards_in_excluded_directory_names(self, mini_rsync, rsync, drive):
        Path(drive.source, "Photos [2020]*?").mkdir()

        run_parallel(mini_rsync, drive)

        assert "/Photos \\[2020]\\*\\?/" in anchored_excludes(rsync.calls[0])

    def should_exit_non_zero_and_name_the_failed_directory_when_an_rsync_fails(self, mini_rsync, rsync, drive, capsys):
        rsync.failing_sources.add(f"{drive.source}Music/")

        with pytest.raises(SystemExit) as exit_:
            run_parallel(mini_rsync, drive)

        output = capsys.readouterr()
        assert exit_.value.code == 1
        assert "All rsync processes completed" not in output.out
        assert f"{drive.source}Music" in output.err
