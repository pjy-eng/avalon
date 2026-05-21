from __future__ import annotations

import time
from collections.abc import Callable


class InMemoryTTLStore:
    def __init__(self, clock: Callable[[], float] | None = None):
        self._clock = clock or time.monotonic
        self._values: dict[str, tuple[str, float]] = {}

    def set_once(self, key: str, value: str, ttl_seconds: float) -> bool:
        self._cleanup_key(key)
        if ttl_seconds <= 0:
            return False
        if key in self._values:
            return False

        self._values[key] = (value, self._clock() + ttl_seconds)
        return True

    def get(self, key: str) -> str | None:
        self._cleanup_key(key)
        entry = self._values.get(key)
        if entry is None:
            return None
        return entry[0]

    def delete(self, key: str) -> None:
        self._values.pop(key, None)

    def _cleanup_key(self, key: str) -> None:
        entry = self._values.get(key)
        if entry is None:
            return
        _value, expires_at = entry
        if expires_at <= self._clock():
            self.delete(key)
