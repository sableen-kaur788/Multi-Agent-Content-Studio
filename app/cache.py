"""
TTL cache for extracted source text (1 hour).

Uses a simple dict with expiry timestamps to avoid re-fetching the same URL or path.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

# Default TTL: 1 hour in seconds
_CACHE_TTL_SECONDS = 3600


class ExtractionCache:
    """
    Thread-safe async-friendly cache for extraction results.

    Keys are normalized source strings (URL or path); values are (expires_at, text).
    """

    def __init__(self, ttl_seconds: int = _CACHE_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._data: dict[str, tuple[float, str]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        async with self._lock:
            now = time.monotonic()
            entry = self._data.get(key)
            if not entry:
                return None
            expires_at, text = entry
            if now >= expires_at:
                del self._data[key]
                return None
            return text

    async def set(self, key: str, value: str) -> None:
        async with self._lock:
            self._data[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        """Clear all entries (mainly for tests)."""
        self._data.clear()


# Singleton used by the extractor agent
extraction_cache = ExtractionCache()
