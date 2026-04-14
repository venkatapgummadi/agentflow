"""
Tests for the ResponseCache, CacheKey, and backends.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import time

import pytest

from agentflow.caching import (
    CacheKey,
    InMemoryCacheBackend,
    RedisStubCacheBackend,
    ResponseCache,
)
from agentflow.connectors.base import APIResponse


def _ok(body=None, status=200, headers=None) -> APIResponse:
    return APIResponse(
        status_code=status,
        body=body or {"ok": True},
        headers=headers or {},
        connector_id="conn",
    )


class TestCacheKey:
    def test_build_is_deterministic(self):
        k1 = CacheKey.build("c1", "GET /x", {"a": 1, "b": 2})
        k2 = CacheKey.build("c1", "GET /x", {"b": 2, "a": 1})
        assert k1 == k2
        assert k1.to_str() == k2.to_str()

    def test_different_params_yield_different_keys(self):
        k1 = CacheKey.build("c1", "GET /x", {"a": 1})
        k2 = CacheKey.build("c1", "GET /x", {"a": 2})
        assert k1 != k2


class TestInMemoryBackend:
    def test_set_and_get(self):
        bk = InMemoryCacheBackend()
        bk.set("k", "value", ttl_seconds=10)
        assert bk.get("k") == "value"

    def test_ttl_expiry(self):
        bk = InMemoryCacheBackend()
        bk.set("k", "value", ttl_seconds=0.01)
        time.sleep(0.02)
        assert bk.get("k") is None

    def test_ttl_zero_means_no_expiry(self):
        bk = InMemoryCacheBackend()
        bk.set("k", "value", ttl_seconds=0)
        assert bk.get("k") == "value"

    def test_eviction_at_capacity(self):
        bk = InMemoryCacheBackend(max_entries=2)
        bk.set("a", 1, ttl_seconds=10)
        bk.set("b", 2, ttl_seconds=10)
        bk.set("c", 3, ttl_seconds=10)
        assert bk.get("a") is None  # oldest evicted
        assert bk.get("b") == 2
        assert bk.get("c") == 3

    def test_delete_returns_presence(self):
        bk = InMemoryCacheBackend()
        bk.set("k", 1, ttl_seconds=10)
        assert bk.delete("k") is True
        assert bk.delete("k") is False


class TestRedisStubBackend:
    def test_namespace_isolation(self):
        bk1 = RedisStubCacheBackend(namespace="ns1")
        bk2 = RedisStubCacheBackend(namespace="ns2")
        bk1.set("k", "v1", ttl_seconds=10)
        bk2.set("k", "v2", ttl_seconds=10)
        # They share underlying storage class but namespaced keys differ
        assert bk1.get("k") == "v1"
        assert bk2.get("k") == "v2"


class TestResponseCacheBehavior:
    def test_lookup_miss_returns_key(self):
        cache = ResponseCache()
        entry, key = cache.lookup("conn", "GET /x", {"id": 1})
        assert entry is None
        assert key.connector_id == "conn"

    def test_store_then_lookup_hit(self):
        cache = ResponseCache(default_ttl_seconds=10)
        _, key = cache.lookup("conn", "GET /x", {"id": 1})
        cache.store(key, _ok())
        entry, _ = cache.lookup("conn", "GET /x", {"id": 1})
        assert entry is not None
        assert entry.response.success
        assert entry.hits == 1

    def test_post_is_not_cacheable(self):
        cache = ResponseCache(default_ttl_seconds=10)
        _, key = cache.lookup("conn", "POST /x", {"id": 1})
        stored = cache.store(key, _ok())
        assert stored is False

    def test_error_response_not_cached_by_default(self):
        cache = ResponseCache()
        _, key = cache.lookup("conn", "GET /x", {})
        err = APIResponse(status_code=500, is_error=True, connector_id="conn")
        assert cache.store(key, err) is False

    def test_error_cached_when_enabled(self):
        cache = ResponseCache(cache_error_responses=True)
        _, key = cache.lookup("conn", "GET /x", {})
        err = APIResponse(status_code=500, is_error=True, connector_id="conn")
        assert cache.store(key, err) is True

    def test_invalidate_drops_entry(self):
        cache = ResponseCache(default_ttl_seconds=10)
        _, key = cache.lookup("conn", "GET /x", {"id": 1})
        cache.store(key, _ok())
        assert cache.invalidate("conn", "GET /x", {"id": 1}) is True
        entry, _ = cache.lookup("conn", "GET /x", {"id": 1})
        assert entry is None

    def test_revalidate_304_refreshes_age(self):
        cache = ResponseCache(default_ttl_seconds=10)
        _, key = cache.lookup("conn", "GET /x", {})
        cache.store(key, _ok(headers={"etag": "abc"}), etag="abc")
        time.sleep(0.01)
        revalidated = cache.revalidate(key, upstream_status=304)
        assert revalidated is not None
        assert revalidated.etag == "abc"

    def test_revalidate_200_replaces_body(self):
        cache = ResponseCache(default_ttl_seconds=10)
        _, key = cache.lookup("conn", "GET /x", {})
        cache.store(key, _ok(body={"v": 1}))
        new = _ok(body={"v": 2})
        revalidated = cache.revalidate(key, upstream_status=200, new_response=new)
        assert revalidated is not None
        assert revalidated.response.body == {"v": 2}

    def test_revalidate_other_status_invalidates(self):
        cache = ResponseCache(default_ttl_seconds=10)
        _, key = cache.lookup("conn", "GET /x", {})
        cache.store(key, _ok())
        revalidated = cache.revalidate(key, upstream_status=410)
        assert revalidated is None

    def test_metrics_track_hits_and_misses(self):
        cache = ResponseCache(default_ttl_seconds=10)
        _, key = cache.lookup("conn", "GET /x", {})  # miss
        cache.store(key, _ok())
        cache.lookup("conn", "GET /x", {})  # hit
        cache.lookup("conn", "GET /y", {})  # miss
        m = cache.get_metrics()
        assert m["hits"] == 1
        assert m["misses"] == 2
        assert m["stores"] == 1
        assert 0.0 <= m["hit_rate"] <= 1.0

    def test_negative_ttl_rejected(self):
        with pytest.raises(ValueError):
            ResponseCache(default_ttl_seconds=-1)
