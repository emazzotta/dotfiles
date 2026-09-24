import os

import pytest

BLOCK_START = "# BEGIN dotfiles dns-hosts"
BLOCK_END = "# END dotfiles dns-hosts"
RECORD_CALL = 'printf \'%s\\n\' "$*" >> "{calls}"'
LONG_AGO = 1_000_000_000


@pytest.fixture
def hosts_file(tmp_path):
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n")
    return hosts


@pytest.fixture
def fragments(tmp_path):
    directory = tmp_path / "dns-hosts"
    directory.mkdir()
    return directory


@pytest.fixture
def sudo_calls(tmp_path):
    calls = tmp_path / "sudo-calls"
    calls.touch()
    return calls


@pytest.fixture
def hosts_sync(run_bash, hosts_file, fragments, sudo_calls):
    def _hosts_sync(*args):
        mocks = {"sudo": RECORD_CALL.format(calls=sudo_calls), "dscacheutil": "exit 0"}
        return run_bash("hosts-sync", ["--hosts-file", str(hosts_file), "--fragments", str(fragments), *args],
                        mock_bins=mocks)
    return _hosts_sync


def should_add_the_fragments_between_markers_and_flush_the_dns_cache(hosts_sync, hosts_file, fragments,
                                                                      sudo_calls):
    (fragments / "a.hosts").write_text("10.0.0.1 a.example\n")
    (fragments / "b.hosts").write_text("10.0.0.2 b.example")

    result = hosts_sync()

    assert result.returncode == 0, result.stderr
    assert hosts_file.read_text() == ("127.0.0.1 localhost\n"
                                      f"{BLOCK_START}\n10.0.0.1 a.example\n10.0.0.2 b.example\n{BLOCK_END}\n")
    assert sudo_calls.read_text().splitlines() == ["dscacheutil -flushcache", "killall -HUP mDNSResponder"]


def should_leave_the_hosts_file_and_dns_cache_alone_when_the_block_is_current(hosts_sync, hosts_file, fragments,
                                                                              sudo_calls):
    (fragments / "a.hosts").write_text("10.0.0.1 a.example\n")
    hosts_sync()
    os.utime(hosts_file, (LONG_AGO, LONG_AGO))
    sudo_calls.write_text("")

    result = hosts_sync()

    assert result.returncode == 0, result.stderr
    assert hosts_file.stat().st_mtime == LONG_AGO
    assert sudo_calls.read_text() == ""


def should_replace_an_outdated_block_and_keep_every_other_line(hosts_sync, hosts_file, fragments):
    hosts_file.write_text(f"127.0.0.1 localhost\n{BLOCK_START}\n10.0.0.9 old.example\n{BLOCK_END}\n::1 localhost\n")
    (fragments / "a.hosts").write_text("10.0.0.1 a.example\n")

    hosts_sync()

    assert hosts_file.read_text() == ("127.0.0.1 localhost\n::1 localhost\n"
                                      f"{BLOCK_START}\n10.0.0.1 a.example\n{BLOCK_END}\n")


def should_write_a_hosts_file_it_cannot_write_itself_through_sudo(hosts_sync, hosts_file, fragments, sudo_calls):
    (fragments / "a.hosts").write_text("10.0.0.1 a.example\n")
    hosts_file.chmod(0o444)

    hosts_sync()

    copy = sudo_calls.read_text().splitlines()[0].split()
    assert (copy[0], copy[-1]) == ("/bin/cp", str(hosts_file))


def should_remove_the_block_once_no_fragments_are_left(hosts_sync, hosts_file):
    hosts_file.write_text(f"127.0.0.1 localhost\n{BLOCK_START}\n10.0.0.1 a.example\n{BLOCK_END}\n")

    hosts_sync()

    assert hosts_file.read_text() == "127.0.0.1 localhost\n"


def should_describe_its_options_in_the_help(run_bash):
    result = run_bash("hosts-sync", ["--help"])

    assert result.returncode == 0
    assert "--hosts-file FILE" in result.stdout
    assert "--fragments DIR" in result.stdout
