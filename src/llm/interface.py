"""Abstract LLM interface -- stateless streaming + non-streaming.

Stateless by design: system prompt and messages are supplied on every call,
never stored on the instance. Subclasses implement only the streaming
method; the non-streaming variant has a default implementation that
collects the stream, so concrete providers only carry one abstract method.

The ``tools`` parameter is reserved for future tool-calling support and is
currently ignored by all providers.

Reference: docs/LLM调用层设计讨论.md §2.2, §2.7
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class LLMInterface(ABC):
    """Stateless LLM call contract.

    Subclasses must implement :meth:`chat_completion_stream` as an async
    generator. :meth:`chat_completion` defaults to collecting the stream.
    """

    @abstractmethod
    def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """Yield non-empty content deltas from the LLM response stream.

        Args:
            messages: Chat history in OpenAI-style format -- a list of
                ``{"role": "user" | "assistant" | ..., "content": str}``.
            system: Optional system prompt. Providers prepend this as a
                ``{"role": "system", "content": system}`` message when
                present.
            tools: Reserved for tool-calling (§2.7). Currently unused by
                all providers.

        Yields:
            str: Content chunks in order of arrival. Empty chunks are
            skipped by provider implementations.
        """

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        """Return the full response as a single string.

        Default implementation collects the streaming result. Override
        when a non-streaming API path is meaningfully cheaper.
        """
        parts: list[str] = []
        async for chunk in self.chat_completion_stream(messages, system, tools):
            parts.append(chunk)
        return "".join(parts)
