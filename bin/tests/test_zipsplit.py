import os
import zipfile

import pytest

from bin.tests.conftest import requires_tool

FILES = ["f1.txt", "f 2.txt", "f3.txt", "f4.txt", "f5.txt"]


@pytest.fixture
def folder(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    for age, name in enumerate(FILES):
        (work / name).write_text(name)
        os.utime(work / name, (1_000_000 + age, 1_000_000 + age))
    return work


def archive_members(folder):
    return {archive.name: sorted(zipfile.ZipFile(archive).namelist()) for archive in sorted(folder.glob("*.zip"))}


@requires_tool("zip")
class TestZipsplit:
    def test_should_put_each_file_into_exactly_one_archive_oldest_first(self, run_cli, folder):
        result = run_cli("zipsplit", ["2"], cwd=folder)

        assert result.returncode == 0, result.stderr
        assert archive_members(folder) == {
            "0.zip": ["f 2.txt", "f1.txt"],
            "2.zip": ["f3.txt", "f4.txt"],
            "4.zip": ["f5.txt"],
        }

    def test_should_not_pack_the_archives_it_just_made(self, run_cli, folder):
        run_cli("zipsplit", ["3"], cwd=folder)

        members = [name for names in archive_members(folder).values() for name in names]
        assert sorted(members) == sorted(FILES)

    def test_should_make_one_archive_when_the_amount_exceeds_the_file_count(self, run_cli, folder):
        result = run_cli("zipsplit", ["50"], cwd=folder)

        assert result.returncode == 0, result.stderr
        assert list(archive_members(folder)) == ["0.zip"]

    @pytest.mark.parametrize("amount", ["0", "abc", "-2"])
    def test_should_reject_an_amount_that_is_not_a_positive_integer(self, run_cli, folder, amount):
        result = run_cli("zipsplit", [amount], cwd=folder)

        assert result.returncode == 1
        assert "usage:" in result.stderr
        assert list(folder.glob("*.zip")) == []

    def test_should_print_usage_without_arguments(self, run_cli, folder):
        result = run_cli("zipsplit", cwd=folder)

        assert "usage:" in result.stdout
