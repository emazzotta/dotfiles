import io
import json
import os
import shutil
import sys
import time
import unicodedata
import urllib.error
from types import SimpleNamespace

import pytest

STORED = "p\u00c4ss"
NFD = unicodedata.normalize("NFD", STORED)
OLD_EDIT = "2026-01-01T00:00:00.000Z"
NEW_EDIT = "2026-02-01T00:00:00.000Z"


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


ENVIFY_STAND_IN = """\
printf '%s\\n' "$@" >> "$ENVIFY_CALLS"
echo ENVIFY_EXTRA=leaked
if [ -n "${ENVIFY_FAIL+x}" ]; then
    printf '%s' "$ENVIFY_FAIL" >&2
    return 1
fi
for name in "$@"; do
    given="ENVIFY_STANDIN_$name"
    if [ -z "${!name}" ] && [ -n "${!given}" ]; then
        export "$name=${!given}"
    fi
done
"""


@pytest.fixture
def asked_of_envify(tmp_path, monkeypatch):
    stand_in = tmp_path / "stand_in" / "envify"
    stand_in.parent.mkdir()
    stand_in.write_text(ENVIFY_STAND_IN)
    calls = tmp_path / "envify_calls"
    monkeypatch.setenv("PATH", f"{stand_in.parent}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("ENVIFY_CALLS", str(calls))
    for name in ("ENVIFY_EXTRA", "NOTION_API_KEY", "PASSWORD_ZIPS"):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    return lambda: calls.read_text().split() if calls.exists() else []


@pytest.fixture
def logged_errors(notion_backup, monkeypatch):
    errors = []
    monkeypatch.setattr(notion_backup.logger, "error", errors.append)
    return errors


def test_should_ask_envify_for_both_secrets_and_keep_their_values_intact(notion_backup, asked_of_envify, monkeypatch):
    monkeypatch.setenv("ENVIFY_STANDIN_NOTION_API_KEY", "secret_key=with equals==")
    monkeypatch.setenv("ENVIFY_STANDIN_PASSWORD_ZIPS", "zip pass")

    notion_backup.load_env()

    assert asked_of_envify() == ["NOTION_API_KEY", "PASSWORD_ZIPS"]
    assert (notion_backup.NOTION_API_KEY, notion_backup.ARCHIVE_PASSWORD) == ("secret_key=with equals==", "zip pass")
    assert (os.environ["NOTION_API_KEY"], os.environ["PASSWORD_ZIPS"]) == ("secret_key=with equals==", "zip pass")


def test_should_copy_nothing_but_the_two_secrets_into_the_environment(notion_backup, asked_of_envify, monkeypatch):
    monkeypatch.setenv("ENVIFY_STANDIN_NOTION_API_KEY", "key")
    monkeypatch.setenv("ENVIFY_STANDIN_PASSWORD_ZIPS", "zip")

    notion_backup.load_env()

    assert "ENVIFY_EXTRA" not in os.environ


def test_should_keep_a_secret_that_is_already_in_the_environment(notion_backup, asked_of_envify, monkeypatch):
    monkeypatch.setenv("NOTION_API_KEY", "kept-key")
    monkeypatch.setenv("ENVIFY_STANDIN_NOTION_API_KEY", "other-key")
    monkeypatch.setenv("ENVIFY_STANDIN_PASSWORD_ZIPS", "zip")

    notion_backup.load_env()

    assert asked_of_envify() == ["NOTION_API_KEY", "PASSWORD_ZIPS"]
    assert notion_backup.NOTION_API_KEY == "kept-key"


@pytest.mark.parametrize("stderr", ["keyguard cancelled\n", ""])
def test_should_log_the_raw_stderr_and_exit_when_envify_fails(
    notion_backup, asked_of_envify, logged_errors, monkeypatch, stderr
):
    monkeypatch.setenv("ENVIFY_FAIL", stderr)

    with pytest.raises(SystemExit) as raised:
        notion_backup.load_env()

    assert raised.value.code == 1
    assert logged_errors == [f"Failed to load credentials via envify: {stderr}"]


@pytest.mark.parametrize("provided,missing", [
    ("PASSWORD_ZIPS", "NOTION_API_KEY"),
    ("NOTION_API_KEY", "PASSWORD_ZIPS"),
])
def test_should_exit_naming_the_secret_envify_did_not_provide(
    notion_backup, asked_of_envify, logged_errors, monkeypatch, provided, missing
):
    monkeypatch.setenv(f"ENVIFY_STANDIN_{provided}", "value")

    with pytest.raises(SystemExit) as raised:
        notion_backup.load_env()

    assert raised.value.code == 1
    assert logged_errors == [f"{missing} not set"]


def notion_page(page_id, title):
    return {
        "id": page_id,
        "last_edited_time": NEW_EDIT,
        "properties": {"title": {"type": "title", "title": [{"plain_text": title}]}},
    }


def paragraph(text):
    return {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": text}]}}


def connection_reset():
    return urllib.error.URLError("connection reset")


def server_error():
    return urllib.error.HTTPError("https://api.notion.com", 500, "Server Error", {}, io.BytesIO(b"boom"))


def rate_limited():
    return urllib.error.HTTPError("https://api.notion.com", 429, "Too Many Requests", {"Retry-After": "0"}, io.BytesIO(b""))


class FakeNotion:
    def __init__(self, search_batches, children, broken=(), error=connection_reset):
        self.search_batches = search_batches
        self.children = children
        self.broken = set(broken)
        self.error = error
        self.timeouts = []

    def urlopen(self, request, timeout=None):
        self.timeouts.append(timeout)
        key, payload = self._route(request)
        if key in self.broken:
            raise self.error()
        return io.BytesIO(json.dumps(payload).encode())

    def _route(self, request):
        if request.full_url.endswith("/search"):
            batch = int(json.loads(request.data).get("start_cursor", 0))
            has_more = batch + 1 < len(self.search_batches)
            payload = {"results": self.search_batches[batch], "has_more": has_more, "next_cursor": str(batch + 1)}
            return f"search:{batch}", payload
        block_id = request.full_url.split("/blocks/")[1].split("/")[0]
        return f"block:{block_id}", {"results": self.children.get(block_id, []), "has_more": False}


@pytest.fixture
def backup_run(notion_backup, monkeypatch, tmp_path):
    previous_cache = tmp_path / "previous_cache"
    previous_cache.mkdir()
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    staging = tmp_path / "staging"
    archived = {}
    credential_loads = []

    def restore_cache(_archive_path, work_dir):
        cache_dir = work_dir / notion_backup.CACHE_DIR_NAME
        shutil.copytree(previous_cache, cache_dir)
        return cache_dir

    def archive(source_parent, source_name, archive_path, label):
        archived[label] = {f.name: f.read_text() for f in (source_parent / source_name).iterdir()}
        archive_path.touch()

    def seed(titles):
        for title in titles.values():
            (previous_cache / f"{title}.html").write_text(f"old {title}")
        index = [{"id": pid, "title": title, "last_edited": OLD_EDIT} for pid, title in titles.items()]
        (previous_cache / notion_backup.INDEX_FILENAME).write_text(json.dumps(index))

    def run(api, *args):
        monkeypatch.setattr(notion_backup.urllib.request, "urlopen", api.urlopen)
        monkeypatch.setattr(sys, "argv", ["notion_backup", str(backup_dir), *args])
        try:
            notion_backup.main()
        except SystemExit as exit_:
            return exit_.code
        return 0

    monkeypatch.setattr(notion_backup, "load_env", lambda: credential_loads.append(True))
    monkeypatch.setattr(notion_backup, "STAGING_ROOT", staging)
    monkeypatch.setattr(notion_backup, "verify_encryption_paths", lambda *_: None)
    monkeypatch.setattr(notion_backup, "extract_cache_archive", restore_cache)
    monkeypatch.setattr(notion_backup, "create_encrypted_archive", archive)
    monkeypatch.setattr(notion_backup, "time", SimpleNamespace(sleep=lambda _: None, strftime=time.strftime))
    return SimpleNamespace(run=run, seed=seed, backup_dir=backup_dir, staging=staging,
                           archived=archived, credential_loads=credential_loads)


def edit_times(notion_backup, cache):
    return {page["id"]: page["last_edited"] for page in json.loads(cache[notion_backup.INDEX_FILENAME])}


@pytest.mark.parametrize("error", [connection_reset, server_error, rate_limited])
def test_should_keep_the_cached_copy_and_edit_time_of_a_page_whose_fetch_fails(notion_backup, backup_run, error):
    backup_run.seed({"a": "Alpha", "b": "Beta"})
    api = FakeNotion([[notion_page("a", "Alpha"), notion_page("b", "Beta")]],
                     {"a": [paragraph("new alpha")]}, broken={"block:b"}, error=error)

    backup_run.run(api)

    cache = backup_run.archived["cache"]
    assert cache["Beta.html"] == "old Beta"
    assert "new alpha" in cache["Alpha.html"]
    assert edit_times(notion_backup, cache) == {"a": NEW_EDIT, "b": OLD_EDIT}


def test_should_write_the_backup_and_exit_non_zero_when_a_page_fails(backup_run):
    backup_run.seed({"a": "Alpha", "b": "Beta"})
    api = FakeNotion([[notion_page("a", "Alpha"), notion_page("b", "Beta")]],
                     {"a": [paragraph("new alpha")]}, broken={"block:b"})

    code = backup_run.run(api)

    assert code == 1
    assert set(backup_run.archived) == {"cache", "snapshot"}
    assert not list(backup_run.staging.glob("run_*"))


def test_should_abort_before_pruning_cache_or_snapshots_when_the_search_is_incomplete(notion_backup, backup_run):
    backup_run.seed({"a": "Alpha", "b": "Beta"})
    old_snapshots = [backup_run.backup_dir / f"notion_everything_2026010{n}_000000.7z" for n in (1, 2, 3)]
    for snapshot in old_snapshots:
        snapshot.touch()
    api = FakeNotion([[notion_page("a", "Alpha")], [notion_page("b", "Beta")]], {}, broken={"search:1"})

    code = backup_run.run(api, "3")

    assert code == 1
    assert backup_run.archived == {}
    assert all(snapshot.exists() for snapshot in old_snapshots)
    assert list(backup_run.staging.glob(f"run_*/{notion_backup.CACHE_DIR_NAME}/Beta.html"))


def test_should_give_every_request_a_timeout(backup_run):
    backup_run.seed({"a": "Alpha"})
    api = FakeNotion([[notion_page("a", "Alpha")]], {"a": [paragraph("text")]})

    backup_run.run(api)

    assert api.timeouts
    assert all(timeout is not None and timeout > 0 for timeout in api.timeouts)


@pytest.mark.parametrize("max_copies", ["0", "-1"])
def test_should_reject_fewer_than_one_copy_before_loading_credentials(backup_run, max_copies):
    api = FakeNotion([[notion_page("a", "Alpha")]], {"a": [paragraph("text")]})

    code = backup_run.run(api, max_copies)

    assert code == 2
    assert backup_run.credential_loads == []
