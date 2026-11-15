import os

import pytest

KUBECTL_MOCK = """echo "kubectl $*" >> "$CALLS"
case "$*" in
    *pg_dump*) exit "${PG_DUMP_STATUS:-0}" ;;
    *"rm -r"*) exit "${REMOTE_RM_STATUS:-0}" ;;
esac"""
RSYNC_MOCK = """echo "rsync" >> "$CALLS"
[ "${RSYNC_STATUS:-0}" = 0 ] || exit "$RSYNC_STATUS"
remote="${@: -2:1}"
printf 'COPY public.cars\\n' > "${@: -1}/$(basename "$remote")"
"""
VERIFY_MOCK = """echo "tmbackupverify $1" >> "$CALLS"
exit ${VERIFY_STATUS:-0}"""
OLD_BACKUPS = {"a.sql", "b.sql", "c.sql", "d.sql"}
KEPT_BACKUPS = 2


@pytest.fixture
def tmbackup(run_cli, tmp_path):
    wdir = tmp_path / "wdir"
    backups = wdir / "private" / "infrastructure" / "backup" / "teslamate"
    backups.mkdir(parents=True)
    for age, name in enumerate(["a.sql", "b.sql", "c.sql", "d.sql"]):
        (backups / name).write_text("old\n")
        os.utime(backups / name, (1_000_000 + age, 1_000_000 + age))
    calls = tmp_path / "calls"
    calls.touch()
    cwd = tmp_path / "cwd"
    cwd.mkdir()

    def _run(**env):
        return run_cli(
            "tmbackup",
            env_extra={"TM_USER": "teslamate", "WDIR": str(wdir), "CALLS": str(calls), **env},
            mock_bins={"kubectl": KUBECTL_MOCK, "rsync": RSYNC_MOCK, "tmbackupverify": VERIFY_MOCK},
            cwd=cwd,
        )
    _run.backups = backups
    _run.calls = lambda: calls.read_text().splitlines()
    return _run


class TestTmbackup:
    def test_should_report_success_and_keep_the_newest_backups(self, tmbackup):
        result = tmbackup()

        assert result.returncode == 0, result.stderr
        assert "Backup SUCCESS" in result.stdout
        assert len(list(tmbackup.backups.glob("*.sql"))) == KEPT_BACKUPS

    def test_should_report_failure_and_keep_every_backup_when_pg_dump_fails(self, tmbackup):
        result = tmbackup(PG_DUMP_STATUS="1")

        assert result.returncode == 1
        assert "Backup FAILED" in result.stdout
        assert "Backup SUCCESS" not in result.stdout
        assert sorted(path.name for path in tmbackup.backups.iterdir()) == ["a.sql", "b.sql", "c.sql", "d.sql"]
        assert not any(call.startswith("tmbackupverify") for call in tmbackup.calls())

    def test_should_report_failure_and_keep_the_remote_dump_when_rsync_fails(self, tmbackup):
        result = tmbackup(RSYNC_STATUS="23")

        assert result.returncode == 1
        assert "Backup FAILED" in result.stdout
        assert "Backup SUCCESS" not in result.stdout
        assert sorted(path.name for path in tmbackup.backups.iterdir()) == ["a.sql", "b.sql", "c.sql", "d.sql"]
        assert not any("rm -r" in call for call in tmbackup.calls())

    def test_should_still_succeed_when_only_the_remote_cleanup_fails(self, tmbackup):
        result = tmbackup(REMOTE_RM_STATUS="1")

        assert result.returncode == 0, result.stderr
        assert "Backup SUCCESS" in result.stdout

    def test_should_fail_and_keep_every_old_backup_when_the_verify_rejects_the_dump(self, tmbackup):
        result = tmbackup(VERIFY_STATUS="1")

        assert result.returncode == 1
        assert "verification FAILED" in result.stderr
        assert "Backup SUCCESS" not in result.stdout
        kept = {path.name for path in tmbackup.backups.iterdir()}
        assert {name for name in kept if name.endswith(".sql")} == OLD_BACKUPS
        assert len({name for name in kept if name.endswith(".sql.rejected")}) == 1

    def test_should_not_count_a_rejected_dump_among_the_backups_to_keep(self, tmbackup):
        tmbackup(VERIFY_STATUS="1")

        result = tmbackup()

        assert result.returncode == 0, result.stderr
        assert len(list(tmbackup.backups.glob("*.sql"))) == KEPT_BACKUPS
        assert len(list(tmbackup.backups.glob("*.sql.rejected"))) == 1
