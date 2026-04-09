import queue
import time
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def mod(load_script):
    return load_script("host-resolver")


class TestResolveIp:
    def test_resolves_localhost(self, mod):
        assert mod.resolve_ip("localhost", timeout_ms=2000) == "127.0.0.1"

    def test_nonexistent_host_returns_none(self, mod):
        assert mod.resolve_ip("nonexistent.invalid.host.xyz", timeout_ms=500) is None

    def test_respects_timeout(self, mod):
        start = time.monotonic()
        mod.resolve_ip("nonexistent.invalid.host.xyz", timeout_ms=200)
        elapsed = time.monotonic() - start
        assert elapsed < 2.0


class TestEnforceTimeout:
    def test_yields_all_items(self, mod):
        q = queue.Queue()
        q.put("a")
        q.put("b")
        assert list(mod.enforce_timeout(q, 2, 5000)) == ["a", "b"]

    def test_stops_at_count(self, mod):
        q = queue.Queue()
        for item in ("a", "b", "c"):
            q.put(item)
        assert len(list(mod.enforce_timeout(q, 2, 5000))) == 2

    def test_stops_on_empty_queue_timeout(self, mod):
        q = queue.Queue()
        start = time.monotonic()
        results = list(mod.enforce_timeout(q, 3, 100))
        elapsed = time.monotonic() - start
        assert len(results) == 0
        assert elapsed < 1.0

    def test_yields_none_values(self, mod):
        q = queue.Queue()
        q.put(None)
        q.put("a")
        results = list(mod.enforce_timeout(q, 2, 5000))
        assert results == [None, "a"]


class TestHostsLookup:
    def test_known_host_has_aliases(self, mod):
        assert "ci-macmini" in mod.HOSTS
        assert len(mod.HOSTS["ci-macmini"]) >= 1

    def test_unknown_host_falls_back_to_literal(self, mod):
        hostnames = mod.HOSTS.get("unknown-host-xyz", ("unknown-host-xyz",))
        assert hostnames == ("unknown-host-xyz",)

    def test_resolve_hosts_unknown_returns_default_fallback(self, mod):
        result = mod.resolve_hosts("nonexistent.invalid.host.xyz", timeout_ms=200)
        assert result == "127.0.0.1"

    def test_resolve_hosts_unknown_returns_custom_fallback(self, mod):
        result = mod.resolve_hosts("nonexistent.invalid.host.xyz", timeout_ms=200, fallback_ip="10.0.0.1")
        assert result == "10.0.0.1"


class TestDnsServer:
    def test_resolve_ip_uses_dig_when_dns_server_set(self, mod):
        completed = MagicMock()
        completed.returncode = 0
        completed.stdout = b"192.168.0.61\n"
        with patch.object(mod.subprocess, "run", return_value=completed) as mock_run:
            result = mod.resolve_ip("myhost", timeout_ms=2000, dns_server="192.168.0.254")
        assert result == "192.168.0.61"
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "dig"
        assert "@192.168.0.254" in cmd
        assert "myhost" in cmd

    def test_resolve_ip_without_dns_server_uses_socket(self, mod):
        completed = MagicMock()
        completed.returncode = 0
        completed.stdout = b"127.0.0.1\n"
        with patch.object(mod.subprocess, "run", return_value=completed) as mock_run:
            mod.resolve_ip("localhost", timeout_ms=2000)
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == mod.sys.executable

    def test_resolve_ip_dig_empty_response_returns_none(self, mod):
        completed = MagicMock()
        completed.returncode = 0
        completed.stdout = b"\n"
        with patch.object(mod.subprocess, "run", return_value=completed):
            assert mod.resolve_ip("nohost", timeout_ms=2000, dns_server="1.1.1.1") is None


class TestSilentMode:
    def test_silent_suppresses_fallback_message(self, mod, capsys):
        mod.resolve_hosts("nonexistent.invalid.host.xyz", timeout_ms=200, silent=True)
        assert capsys.readouterr().err == ""

    def test_non_silent_prints_fallback_message(self, mod, capsys):
        mod.resolve_hosts("nonexistent.invalid.host.xyz", timeout_ms=200, silent=False)
        assert "No reachable host found" in capsys.readouterr().err

    def test_silent_with_custom_fallback_suppresses_message(self, mod, capsys):
        result = mod.resolve_hosts("nonexistent.invalid.host.xyz", timeout_ms=200,
                                   fallback_ip="10.0.0.1", silent=True)
        assert result == "10.0.0.1"
        assert capsys.readouterr().err == ""

    def test_non_silent_with_custom_fallback_prints_message(self, mod, capsys):
        result = mod.resolve_hosts("nonexistent.invalid.host.xyz", timeout_ms=200,
                                   fallback_ip="10.0.0.1", silent=False)
        assert result == "10.0.0.1"
        assert "No reachable host found" in capsys.readouterr().err


class TestAlertMode:
    def test_alert_exits_1_when_resolved_differs_from_fallback(self, mod):
        with patch.object(mod, "resolve_hosts", return_value="192.168.0.61"):
            with patch.object(mod.sys, "argv", ["host-resolver", "myhost", "-a"]):
                with pytest.raises(SystemExit, match="1"):
                    mod.main()

    def test_alert_exits_0_when_resolved_equals_default_fallback(self, mod):
        with patch.object(mod, "resolve_hosts", return_value="127.0.0.1"):
            with patch.object(mod.sys, "argv", ["host-resolver", "myhost", "-a"]):
                mod.main()

    def test_alert_exits_0_when_resolved_equals_custom_fallback(self, mod):
        with patch.object(mod, "resolve_hosts", return_value="10.0.0.1"):
            with patch.object(mod.sys, "argv", ["host-resolver", "myhost", "-a", "-f", "10.0.0.1"]):
                mod.main()

    def test_alert_exits_1_when_resolved_differs_from_custom_fallback(self, mod):
        with patch.object(mod, "resolve_hosts", return_value="192.168.0.61"):
            with patch.object(mod.sys, "argv", ["host-resolver", "myhost", "-a", "-f", "10.0.0.1"]):
                with pytest.raises(SystemExit, match="1"):
                    mod.main()

    def test_no_alert_flag_does_not_exit_1(self, mod):
        with patch.object(mod, "resolve_hosts", return_value="192.168.0.61"):
            with patch.object(mod.sys, "argv", ["host-resolver", "myhost"]):
                mod.main()
