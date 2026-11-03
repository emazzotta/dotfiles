import pytest


@pytest.fixture
def repolib(load_script, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return load_script("repolib.py")


def should_read_only_the_entries_of_the_named_section(repolib, repo_ignore):
    repo_ignore("[gck-hide]", "project", "[gck]", "# bots only", "", "  private/tad  ", "[gupallin]", "archive")

    assert repolib.ignore_entries("gck") == ("private/tad",)


def should_read_no_entries_without_an_ignore_file(repolib):
    assert repolib.ignore_entries("gck") == ()


@pytest.mark.parametrize("entry, ignored", [
    ("tad", True), ("private/tad", True), ("private/t*", True), ("ta", False), ("other/tad", False)])
def should_read_each_entry_as_a_glob_for_the_end_of_the_repository_path(repolib, tmp_path, entry, ignored):
    assert repolib.is_ignored(tmp_path / "private" / "tad", [entry]) is ignored
