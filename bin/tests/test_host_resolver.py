import queue
import time

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

    def test_resolve_hosts_unknown_returns_fallback(self, mod):
        result = mod.resolve_hosts("nonexistent.invalid.host.xyz", timeout_ms=200)
        assert result == "127.0.0.1"
