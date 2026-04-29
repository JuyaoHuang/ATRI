"""Small in-process cache for long-term memory search results."""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SearchCacheKey:
    user_id: str
    agent_id: str
    query: str
    limit: int
    threshold: float


@dataclass
class _SearchCacheEntry:
    expires_at: float
    value: list[dict[str, Any]]


class SearchCache:
    """TTL + LRU cache for repeated mem0.search calls in one process."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        max_entries: int,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = max(0, int(ttl_seconds))
        self.max_entries = max(1, int(max_entries))
        self._time_fn = time_fn
        self._entries: OrderedDict[SearchCacheKey, _SearchCacheEntry] = OrderedDict()

    @staticmethod
    def make_key(
        *,
        user_id: str,
        agent_id: str,
        query: str,
        limit: int,
        threshold: float,
    ) -> SearchCacheKey:
        return SearchCacheKey(
            user_id=user_id,
            agent_id=agent_id,
            query=" ".join(query.strip().split()),
            limit=limit,
            threshold=threshold,
        )

    def get(self, key: SearchCacheKey) -> list[dict[str, Any]] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self._time_fn():
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return deepcopy(entry.value)

    def set(self, key: SearchCacheKey, value: list[dict[str, Any]]) -> None:
        if self.ttl_seconds <= 0:
            return
        self._entries[key] = _SearchCacheEntry(
            expires_at=self._time_fn() + self.ttl_seconds,
            value=deepcopy(value),
        )
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def invalidate_scope(self, *, user_id: str, agent_id: str) -> None:
        for key in list(self._entries):
            if key.user_id == user_id and key.agent_id == agent_id:
                self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
