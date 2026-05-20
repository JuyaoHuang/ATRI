"""Small in-process cache for long-term memory search results.

长期记忆搜索结果的进程内小缓存。

Reference: docs/记忆系统设计讨论.md §8.3
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


def normalize_search_query(query: str) -> str:
    return " ".join(query.strip().split())


@dataclass(frozen=True)
class SearchCacheKey:
    """Composite cache key for a single mem0 search query.

    单次 mem0 搜索查询的组合缓存键。
    """

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
    """TTL + LRU cache for repeated mem0.search calls in one process.

    单进程内用于重复 mem0.search 调用的 TTL + LRU 缓存。
    """

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
        """Build a normalised cache key from search parameters.

        从搜索参数构建标准化的缓存键。
        """
        return SearchCacheKey(
            user_id=user_id,
            agent_id=agent_id,
            query=normalize_search_query(query),
            limit=limit,
            threshold=threshold,
        )

    def get(self, key: SearchCacheKey) -> list[dict[str, Any]] | None:
        """Return cached value if present and not expired, else None.

        若缓存存在且未过期则返回缓存值，否则返回 None。
        """
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self._time_fn():
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return deepcopy(entry.value)

    def set(self, key: SearchCacheKey, value: list[dict[str, Any]]) -> None:
        """Store a search result, evicting the oldest entry if at capacity.

        存储搜索结果，若达到容量上限则淘汰最早的条目。
        """
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
        """Drop all cached entries for one user/agent pair.

        丢弃某个 user/agent 对的所有缓存条目。
        """
        for key in list(self._entries):
            if key.user_id == user_id and key.agent_id == agent_id:
                self._entries.pop(key, None)

    def clear(self) -> None:
        """Remove all cached entries.

        移除所有缓存条目。
        """
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


__all__ = ["SearchCache", "SearchCacheKey", "normalize_search_query"]
