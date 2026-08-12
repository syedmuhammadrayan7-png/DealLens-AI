from __future__ import annotations

from time import monotonic
from typing import Callable, TypeVar

T = TypeVar("T")


class TTLCache:
    def __init__(self, ttl_seconds: int = 900):
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, tuple[float, object]] = {}

    def get_or_set(self, key: str, factory: Callable[[], T]) -> T:
        existing = self._entries.get(key)
        if existing and monotonic() - existing[0] < self.ttl_seconds:
            return existing[1]  # type: ignore[return-value]
        value = factory()
        self._entries[key] = (monotonic(), value)
        return value

    def clear(self) -> None:
        self._entries.clear()
