import unicodedata
from types import SimpleNamespace

import pytest

STORED = "p\u00c4ss"
NFD = unicodedata.normalize("NFD", STORED)


@pytest.fixture
def notion_backup(load_script, monkeypatch):
    module = load_script("notion_backup")
    monkeypatch.setattr(module, "ARCHIVE_PASSWORD", STORED)
    return module


@pytest.fixture
def seven_zip(notion_backup, monkeypatch):
    tried = []

    def install(accepted):
        def run(args, **_):
            password = next(a for a in args if isinstance(a, bytes) and a.startswith(b"-p"))[2:]
            tried.append(password)
            opened = password == accepted.encode()
            return SimpleNamespace(returncode=0 if opened else 2, stdout="", stderr="Wrong password?")
        monkeypatch.setattr(notion_backup.subprocess, "run", run)
        return tried
    return install


@pytest.fixture
def cache_archive(tmp_path):
    archive = tmp_path / "cache.7z"
    archive.touch()
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    return archive, work_dir


def test_should_open_the_cache_with_the_nfd_spelling_when_the_stored_one_fails(notion_backup, seven_zip, cache_archive):
    archive, work_dir = cache_archive
    tried = seven_zip(accepted=NFD)

    cache_dir = notion_backup.extract_cache_archive(archive, work_dir)

    assert tried == [STORED.encode(), NFD.encode()]
    assert cache_dir == work_dir / notion_backup.CACHE_DIR_NAME
    assert cache_dir.is_dir()


def test_should_exit_when_no_spelling_opens_the_cache(notion_backup, seven_zip, cache_archive):
    archive, work_dir = cache_archive
    seven_zip(accepted="something-else")

    with pytest.raises(SystemExit):
        notion_backup.extract_cache_archive(archive, work_dir)
