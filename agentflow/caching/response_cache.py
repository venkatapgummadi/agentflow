"""
ResponseCache — TTL + ETag aware caching for idempotent API responses.

Designed to wrap a BaseConnector's `invoke` so repeated GET-style
calls within a TTL window return immediately without an upstream
hop. Supports ETag revalidation: when the cached entry is stale the
caller can perform a conditional request and refresh-or-extend the
cached entry on a 304.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from agentflow.caching.backends import CacheBackend, InMemoryCacheBackend
from agentflow.connectors.base import APIResponse

logger = logging.getLogger(__name__)


# Idempotent HTTP methods that are safe to cache by default.
_DEFAULT_CACHEABLE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class CacheKey:
    """Stable identifier for a cached response."""

    connector_id: str
    operation: str
    params_hash: str

    def to_str(self) -> str:
        return f"{self.connector_id}|{self.operation}|{self.params_hash}"

    @classmethod
    def build(
        cls,
        connector_id: str,
        operation: str,
        parameters: dict[str, Any] | None,
    ) -> CacheKey:
        normalized = json.dumps(parameters or {}, sort_keys=True, default=str)
        params_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
        return cls(
            connector_id=connector_id,
            operation=operation,
            params_hash=params_hash,
        )


@dataclass
class CachedEntry:
    """Stored representation of a cached response."""

    response: APIResponse
    etag: str = ""
    stored_at: float = field(default_factory=time.time)
    hits: int = 0

    def age_seconds(self) -> float:
        return time.time() - self.stored_at


class ResponseCache:
    """
    Idempotent-response cache with TTL and ETag revalidation.

    Args:
        backend: Pluggable storage backend. Defaults to in-memory.
        default_ttl_seconds: TTL applied when no per-call TTL is given.
        cacheable_methods: HTTP methods (uppercase) eligible for caching.
        cache_error_responses: When False (default), 4xx/5xx are not stored.

    Usage:
        cache = ResponseCache(default_ttl_seconds=30.0)

        cached, key = cache.lookup(connector.connector_id, "GET /x", params)
        if cached:
            return cached.response

        resp = await connector.invoke("GET /x", params)
        cache.store(key, resp, ttl_seconds=60)
    """

    def __init__(
        self,
        backend: CacheBackend | None = None,
        default_ttl_seconds: float = 60.0,
        cacheable_methods: frozenset[str] | None = None,
        cache_error_responses: bool = False,
    ):
        if default_ttl_seconds < 0:
            raise ValueError("default_ttl_seconds must be >= 0")
        self.backend = backend or InMemoryCacheBackend()
        self.default_ttl_seconds = default_ttl_seconds
        self.cacheable_methods = cacheable_methods or _DEFAULT_CACHEABLE_METHODS
        self.cache_error_responses = cache_error_responses

        self._hits = 0
        self._misses = 0
        self._stores = 0
        self._revalidations = 0

    # ── Public API ───────────────────────────────────────────────────────

    def is_cacheable(self, operation: str, response: APIResponse | None = None) -> bool:
        """Decide whether an operation/response combination is cacheable."""
        method = operation.split(" ", 1)[0].upper()
        if method not in self.cacheable_methods:
            return False
        if response is not None and response.is_error and not self.cache_error_responses:
            return False
        return True

    def lookup(
        self,
        connector_id: str,
        operation: str,
        parameters: dict[str, Any] | None,
    ) -> tuple[CachedEntry | None, CacheKey]:
        """
        Look up a cached entry. Always returns the (entry-or-None, key)
        pair so callers can pass the key straight into `store()` on miss.
        """
        key = CacheKey.build(connector_id, operation, parameters)
        if not self.is_cacheable(operation):
            self._misses += 1
            return None, key

        raw = self.backend.get(key.to_str())
        if raw is None:
            self._misses += 1
            return None, key

        if not isinstance(raw, CachedEntry):
            # Backend returned a foreign value — drop it.
            self.backend.delete(key.to_str())
            self._misses += 1
            return None, key

        raw.hits += 1
        self._hits += 1
        logger.debug(
            "Cache hit for %s (age=%.2fs, etag=%s)",
            key.to_str(),
            raw.age_seconds(),
            raw.etag or "-",
        )
        return raw, key

    def store(
        self,
        key: CacheKey,
        response: APIResponse,
        ttl_seconds: float | None = None,
        etag: str | None = None,
    ) -> bool:
        """
        Store a fresh response. Returns True if stored, False if skipped
        (e.g., non-cacheable method or error response).
        """
        if not self.is_cacheable(key.operation, response):
            return False

        effective_etag = etag or response.headers.get("etag", "") if response.headers else ""
        entry = CachedEntry(response=response, etag=effective_etag or "")
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        self.backend.set(key.to_str(), entry, ttl)
        self._stores += 1
        logger.debug("Cache store for %s (ttl=%.2fs)", key.to_str(), ttl)
        return True

    def revalidate(
        self,
        key: CacheKey,
        upstream_status: int,
        new_response: APIResponse | None = None,
        ttl_seconds: float | None = None,
    ) -> CachedEntry | None:
        """
        Revalidate a cached entry against an upstream conditional
        request. Pass the status returned by the upstream:

        - 304 Not Modified: refresh stored_at, keep stored body.
        - 200 (or any 2xx with a new body): replace the cached entry
          with `new_response`.
        - other: invalidate and return None.
        """
        raw = self.backend.get(key.to_str())
        if upstream_status == 304 and isinstance(raw, CachedEntry):
            raw.stored_at = time.time()
            ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
            self.backend.set(key.to_str(), raw, ttl)
            self._revalidations += 1
            return raw

        if 200 <= upstream_status < 300 and new_response is not None:
            self.store(key, new_response, ttl_seconds=ttl_seconds)
            return self.backend.get(key.to_str())  # type: ignore[return-value]

        # Anything else: drop the entry.
        self.backend.delete(key.to_str())
        return None

    def invalidate(
        self,
        connector_id: str,
        operation: str,
        parameters: dict[str, Any] | None = None,
    ) -> bool:
        """Drop a single cache entry. Returns True if it was present."""
        key = CacheKey.build(connector_id, operation, parameters)
        return self.backend.delete(key.to_str())

    def clear(self) -> None:
        """Drop every cached entry from the backend."""
        self.backend.clear()

    def get_metrics(self) -> dict[str, Any]:
        total_lookups = self._hits + self._misses
        hit_rate = self._hits / total_lookups if total_lookups else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "stores": self._stores,
            "revalidations": self._revalidations,
            "hit_rate": round(hit_rate, 4),
            "size": self.backend.size(),
        }
