from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def mod(load_script):
    return load_script("robust-rsync")


@pytest.fixture
def make_config(mod):
    defaults = dict(
        remote="user@host:/data", local=Path("/backup"),
        direction=mod.Direction.PULL, use_sudo=False, dry_run=False,
        max_retries=3, initial_wait=5, max_wait=300, timeout=300,
        bwlimit=None, verbose=False,
    )
    def _make(**overrides):
        return mod.SyncConfig(**(defaults | overrides))
    return _make


class TestSyncConfig:
    def test_frozen_dataclass(self, make_config):
        config = make_config()
        with pytest.raises(AttributeError):
            config.remote = "changed"


class TestRsyncCommandBuilder:
    def test_basic_pull(self, mod, make_config):
        cmd = mod.RsyncCommandBuilder(make_config()).build()
        assert cmd[0] == "rsync"
        assert "-a" in cmd
        assert "--partial" in cmd
        assert "--compress" in cmd
        assert cmd[-2] == "user@host:/data"
        assert cmd[-1] == "/backup"

    def test_push_direction(self, mod, make_config):
        cmd = mod.RsyncCommandBuilder(make_config(direction=mod.Direction.PUSH)).build()
        assert cmd[-2] == "/backup"
        assert cmd[-1] == "user@host:/data"

    def test_sudo_flag(self, mod, make_config):
        cmd = mod.RsyncCommandBuilder(make_config(use_sudo=True)).build()
        assert "--rsync-path=sudo rsync" in cmd

    def test_no_sudo(self, mod, make_config):
        cmd = mod.RsyncCommandBuilder(make_config(use_sudo=False)).build()
        assert "--rsync-path=sudo rsync" not in cmd

    def test_dry_run(self, mod, make_config):
        cmd = mod.RsyncCommandBuilder(make_config(dry_run=True)).build()
        assert "--dry-run" in cmd

    def test_bwlimit(self, mod, make_config):
        cmd = mod.RsyncCommandBuilder(make_config(bwlimit=5000)).build()
        assert "--bwlimit=5000" in cmd

    def test_no_bwlimit(self, mod, make_config):
        cmd = mod.RsyncCommandBuilder(make_config(bwlimit=None)).build()
        assert not any("--bwlimit" in c for c in cmd)

    def test_verbose(self, mod, make_config):
        cmd = mod.RsyncCommandBuilder(make_config(verbose=True)).build()
        assert "--progress" in cmd
        assert "--stats" in cmd

    def test_timeout_in_command(self, mod, make_config):
        cmd = mod.RsyncCommandBuilder(make_config(timeout=120)).build()
        assert "--timeout=120" in cmd

    def test_should_not_delete_at_the_destination_by_default(self, mod, make_config):
        cmd = mod.RsyncCommandBuilder(make_config()).build()

        assert not any(arg.startswith("--delete") for arg in cmd)

    def test_should_delete_after_the_transfer_when_delete_is_requested(self, mod, make_config):
        cmd = mod.RsyncCommandBuilder(make_config(delete=True)).build()

        assert "--delete-after" in cmd


class TestRetryStrategy:
    def test_initial_wait(self, mod):
        s = mod.RetryStrategy(initial_wait=5, max_wait=300)
        with patch.object(mod, "randint", return_value=0):
            assert s.calculate_next_wait() == 5

    def test_exponential_backoff(self, mod):
        s = mod.RetryStrategy(initial_wait=5, max_wait=300)
        with patch.object(mod, "randint", return_value=0):
            s.calculate_next_wait()
            assert s.calculate_next_wait() == 10

    def test_third_iteration_doubles_again(self, mod):
        s = mod.RetryStrategy(initial_wait=5, max_wait=300)
        with patch.object(mod, "randint", return_value=0):
            s.calculate_next_wait()
            s.calculate_next_wait()
            assert s.calculate_next_wait() == 20

    def test_max_wait_cap(self, mod):
        s = mod.RetryStrategy(initial_wait=200, max_wait=300)
        with patch.object(mod, "randint", return_value=0):
            s.calculate_next_wait()
            assert s.calculate_next_wait() <= 300

    def test_jitter_adds_randomness(self, mod):
        s = mod.RetryStrategy(initial_wait=5, max_wait=300)
        with patch.object(mod, "randint", return_value=3):
            assert s.calculate_next_wait() == 8

    def test_reset(self, mod):
        s = mod.RetryStrategy(initial_wait=5, max_wait=300)
        with patch.object(mod, "randint", return_value=0):
            s.calculate_next_wait()
            s.calculate_next_wait()
        assert s.current_wait > 5
        s.reset()
        assert s.current_wait == 5


class TestValidateConfig:
    def test_valid(self, mod, tmp_path):
        args = type("A", (), {"local": tmp_path, "retries": 5, "timeout": 300, "bwlimit": None})()
        assert mod.validate_config(args) is None

    @pytest.mark.parametrize("field,value,expected_msg", [
        ("retries", 0, "at least 1"),
        ("timeout", 0, "at least 1"),
        ("bwlimit", 0, "positive"),
        ("bwlimit", -1, "positive"),
    ])
    def test_invalid_values(self, mod, tmp_path, field, value, expected_msg):
        kwargs = {"local": tmp_path, "retries": 5, "timeout": 300, "bwlimit": None}
        kwargs[field] = value
        args = type("A", (), kwargs)()
        assert expected_msg in mod.validate_config(args)

    def test_nonexistent_dir(self, mod, tmp_path):
        args = type("A", (), {"local": tmp_path / "nope", "retries": 5, "timeout": 300, "bwlimit": None})()
        assert "does not exist" in mod.validate_config(args)


RSYNC_ARGV_RECORDER = 'printf "%s\\n" "$@" >> "$ARGV_LOG"'


@pytest.fixture
def sync(run_cli, tmp_path):
    local = tmp_path / "local"
    local.mkdir()
    argv_log = tmp_path / "rsync-argv"
    argv_log.touch()

    def _sync(*flags):
        return run_cli(
            "robust-rsync",
            ["--remote", "user@host:/data/", "--local", str(local), *flags],
            env_extra={"ARGV_LOG": str(argv_log)},
            mock_bins={"rsync": RSYNC_ARGV_RECORDER},
        )
    _sync.rsync_argv = lambda: argv_log.read_text().splitlines()
    return _sync


class TestDeleteFlag:
    def test_should_delete_nothing_at_the_destination_without_the_flag(self, sync):
        result = sync()

        assert result.returncode == 0, result.stderr
        assert sync.rsync_argv() != []
        assert not any(arg.startswith("--delete") for arg in sync.rsync_argv())

    def test_should_pass_delete_after_to_rsync_when_the_flag_is_given(self, sync):
        result = sync("--delete")

        assert result.returncode == 0, result.stderr
        assert "--delete-after" in sync.rsync_argv()

    def test_should_describe_the_delete_flag_in_the_help_text(self, run_cli):
        result = run_cli("robust-rsync", ["--help"])

        assert result.returncode == 0, result.stderr
        assert "--delete" in result.stdout
