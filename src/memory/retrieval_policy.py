"""Long-term memory retrieval policy.

This module decides whether a chat turn should call ``mem0.search`` before
building the LLM context. It is intentionally pure so quota-saving behavior can
be tested without touching mem0.

长期记忆检索策略。

本模块决定某次聊天轮次是否应在组装 LLM 上下文前调用 ``mem0.search``。
设计为纯函数，使配额节省行为可在不触及 mem0 的情况下进行测试。

Reference: docs/记忆系统设计讨论.md §8.1–§8.4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VALID_POLICIES = {"always", "interval", "triggered", "hybrid"}


def _parse_trigger_keywords(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        return (text,) if text else ()
    if not isinstance(value, list | tuple):
        raise ValueError("mem0.retrieval.trigger_keywords must be a list of strings")

    keywords: list[str] = []
    for keyword in value:
        if not isinstance(keyword, str):
            raise ValueError("mem0.retrieval.trigger_keywords must contain only strings")
        text = keyword.strip()
        if text:
            keywords.append(text)
    return tuple(keywords)


@dataclass(frozen=True)
class RetrievalDecision:
    """Result of a retrieval policy evaluation.

    检索策略评估的结果。
    """

    should_search: bool
    reason: str


@dataclass(frozen=True)
class LongTermRetrievalPolicy:
    """Configuration-driven policy that decides when to call mem0.search.

    由配置驱动的策略，决定何时调用 mem0.search。
    """

    enabled: bool = True
    policy: str = "always"
    interval_turns: int = 10
    min_query_chars: int = 0
    trigger_keywords: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_mem0_config(cls, mem0_config: dict[str, Any]) -> LongTermRetrievalPolicy:
        """Build a policy instance from the ``mem0`` section of config yaml.

        从配置 yaml 的 ``mem0`` 部分构建策略实例。
        """
        retrieval_cfg = mem0_config.get("retrieval")
        if not isinstance(retrieval_cfg, dict):
            return cls()

        policy = str(retrieval_cfg.get("policy", "always")).strip().lower()
        if policy not in VALID_POLICIES:
            raise ValueError(
                f"mem0.retrieval.policy must be one of {sorted(VALID_POLICIES)}, got {policy!r}"
            )

        return cls(
            enabled=bool(retrieval_cfg.get("enabled", True)),
            policy=policy,
            interval_turns=max(1, int(retrieval_cfg.get("interval_turns", 10))),
            min_query_chars=max(0, int(retrieval_cfg.get("min_query_chars", 0))),
            trigger_keywords=_parse_trigger_keywords(retrieval_cfg.get("trigger_keywords")),
        )

    def decide(
        self,
        query: str,
        *,
        current_round: int,
        last_search_round: int | None,
    ) -> RetrievalDecision:
        """Evaluate whether the current turn should trigger a long-term search.

        评估当前轮次是否应触发长期记忆搜索。
        """
        text = " ".join(query.strip().split())
        if not self.enabled:
            return RetrievalDecision(False, "disabled")
        if not text:
            return RetrievalDecision(False, "empty_query")
        if len(text) < self.min_query_chars:
            return RetrievalDecision(False, "short_query")

        if self.policy == "always":
            return RetrievalDecision(True, "always")

        trigger_matched = self._matches_trigger(text)
        interval_due = self._is_interval_due(current_round, last_search_round)

        if self.policy == "triggered":
            return RetrievalDecision(
                trigger_matched, "triggered" if trigger_matched else "no_trigger"
            )
        if self.policy == "interval":
            return RetrievalDecision(interval_due, "interval" if interval_due else "interval_skip")

        should_search = trigger_matched or interval_due
        if trigger_matched:
            return RetrievalDecision(True, "hybrid_trigger")
        if interval_due:
            return RetrievalDecision(True, "hybrid_interval")
        return RetrievalDecision(should_search, "hybrid_skip")

    def _matches_trigger(self, text: str) -> bool:
        folded = text.casefold()
        return any(keyword.casefold() in folded for keyword in self.trigger_keywords)

    def _is_interval_due(self, current_round: int, last_search_round: int | None) -> bool:
        if last_search_round is None:
            return True
        return current_round - last_search_round >= self.interval_turns


__all__ = ["LongTermRetrievalPolicy", "RetrievalDecision"]
