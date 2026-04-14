"""
Pluggable cache backends.

The backend interface is intentionally minimal so it can wrap an
in-memory dict, Redis, Memcached, or any other key-value store.

Author: Venkata Pavan Kumar Gummadi
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from typing import Any


class CacheBackend(ABC):
    """Minimal key-value cache interface."""

    @abstractmethod
    def get(self, key: str) -> Any | None:
        """Return the stored value, or None if absent / expired."""

    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        """Store a value with a TTL. ttl<=0 means no expiry."""

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a key. Returns True if it was present."""

    @abstractmethod
    def clear(self) -> None:
        """Drop all entries."""

    @abstractmethod
    def size(self) -> int:
        """Approximate number of stored entries."""


class InMemoryCacheBackend(CacheBackend):
    """Thread-safe in-process cache backend."""

    def __init__(self, max_entries: int = 1024):
        if max_entries <= 0:
            raise ValueError("max_entries must be > 0")
        self.max_entries = max_entries
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at and time.time() >= expires_at:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        with self._lock:
            if len(self._store) >= self.max_entries and key not in self._store:
                # Naive eviction: drop the oldest by insertion order
                oldest = next(iter(self._store))
                self._store.pop(oldest, None)
            expires_at = (time.time() + ttl_seconds) if ttl_seconds > 0 else 0.0
            self._store[key] = (value, expires_at)

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._store.pop(key, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._store)


class RedisStubCacheBackend(InMemoryCacheBackend):
    """
    Redis-compatible stub for environments without a Redis dependency.

    Mirrors the InMemoryCacheBackend interface so unit tests and
    examples can run without a Redis broker. Replace with a real
    Redis client for production use.
    """

    def __init__(self, namespace: str = "agentflow", max_entries: int = 4096):
        super().__init__(max_entries=max_entries)
        self.namespace = namespace

    def _ns(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    def get(self, key: str) -> Any | None:  # type: ignore[override]
        return super().get(self._ns(key))

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:  # type: ignore[override]
        super().set(self._ns(key), value, ttl_seconds)

    def delete(self, key: str) -> bool:  # type: ignore[override]
        return super().delete(self._ns(key))
