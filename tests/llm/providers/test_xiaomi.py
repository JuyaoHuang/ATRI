"""Tests for src.llm.providers.xiaomi.

All tests mock ``AsyncOpenAI`` -- no real network calls are made.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIConnectionError, APIError, RateLimitError

from src.llm.exceptions import (
    LLMAPIError,
    LLMConnectionError,
    LLMRateLimitError,
)
from src.llm.factory import LLMFactory
from src.llm.providers.xiaomi import XiaomiLLM


def _chunk(text: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=text,
                    reasoning_content=None,
                )
            )
        ]
    )


def _reasoning_chunk(text: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=None,
                    reasoning_content=text,
                )
            )
        ]
    )


def _empty_choices_chunk() -> SimpleNamespace:
    return SimpleNamespace(choices=[])


def _missing_delta_chunk() -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace()])


class _FakeStream:
    def __init__(self, items: list[Any]) -> None:
        self._items = iter(items)

    def __aiter__(self) -> _FakeStream:
        return self

    async def __anext__(self) -> Any:
        try:
            return next(self._items)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeConnErr(APIConnectionError):
    def __init__(self, msg: str = "conn failed") -> None:
        Exception.__init__(self, msg)


class _FakeRateLimitErr(RateLimitError):
    def __init__(self, msg: str = "rate limited") -> None:
        Exception.__init__(self, msg)


class _FakeAPIErr(APIError):
    def __init__(self, msg: str = "api failure") -> None:
        Exception.__init__(self, msg)


@pytest.fixture
def patched_client() -> Any:
    with patch("src.llm.providers.xiaomi.AsyncOpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        yield mock_client


async def _collect(stream: AsyncIterator[str]) -> list[str]:
    return [chunk async for chunk in stream]


def test_factory_registration_binds_xiaomi() -> None:
    assert LLMFactory._registry.get("xiaomi") is XiaomiLLM


@pytest.mark.asyncio
async def test_stream_yields_non_empty_deltas_in_order(patched_client: Any) -> None:
    patched_client.chat.completions.create = AsyncMock(
        return_value=_FakeStream([_chunk("he"), _chunk("llo"), _chunk(None), _chunk(" world")])
    )
    llm = XiaomiLLM(model="m", base_url="u", api_key="k")
    chunks = await _collect(
        llm.chat_completion_stream(messages=[{"role": "user", "content": "hi"}])
    )
    assert chunks == ["he", "llo", " world"]


@pytest.mark.asyncio
async def test_request_options_forwarded_when_present(patched_client: Any) -> None:
    patched_client.chat.completions.create = AsyncMock(return_value=_FakeStream([]))
    llm = XiaomiLLM(
        model="m",
        base_url="u",
        api_key="k",
        temperature=1.0,
        request_options={
            "max_completion_tokens": 1024,
            "top_p": 0.95,
            "frequency_penalty": 0,
            "presence_penalty": 0,
            "extra_body": {"thinking": {"type": "disabled"}},
        },
    )
    await _collect(llm.chat_completion_stream(messages=[]))
    call_kwargs = patched_client.chat.completions.create.await_args.kwargs
    assert call_kwargs["temperature"] == 1.0
    assert call_kwargs["max_completion_tokens"] == 1024
    assert call_kwargs["top_p"] == 0.95
    assert call_kwargs["frequency_penalty"] == 0
    assert call_kwargs["presence_penalty"] == 0
    assert call_kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert call_kwargs["stream"] is True


@pytest.mark.asyncio
async def test_reasoning_chunks_are_ignored_when_content_is_empty(patched_client: Any) -> None:
    patched_client.chat.completions.create = AsyncMock(
        return_value=_FakeStream(
            [
                _reasoning_chunk("Okay, the user"),
                _chunk("final"),
                _reasoning_chunk("more hidden reasoning"),
                _chunk(" answer"),
            ]
        )
    )
    llm = XiaomiLLM(model="m", base_url="u", api_key="k")
    chunks = await _collect(llm.chat_completion_stream(messages=[]))
    assert chunks == ["final", " answer"]


@pytest.mark.asyncio
async def test_control_chunks_without_choices_or_delta_are_ignored(
    patched_client: Any,
) -> None:
    patched_client.chat.completions.create = AsyncMock(
        return_value=_FakeStream(
            [
                _empty_choices_chunk(),
                _missing_delta_chunk(),
                _chunk("final"),
                _empty_choices_chunk(),
                _chunk(" answer"),
            ]
        )
    )
    llm = XiaomiLLM(model="m", base_url="u", api_key="k")
    chunks = await _collect(llm.chat_completion_stream(messages=[]))
    assert chunks == ["final", " answer"]


@pytest.mark.asyncio
async def test_tools_parameter_accepted_but_ignored(patched_client: Any) -> None:
    patched_client.chat.completions.create = AsyncMock(return_value=_FakeStream([]))
    llm = XiaomiLLM(model="m", base_url="u", api_key="k")
    await _collect(llm.chat_completion_stream(messages=[], tools=[{"name": "t"}]))
    call_kwargs = patched_client.chat.completions.create.await_args.kwargs
    assert "tools" not in call_kwargs


@pytest.mark.asyncio
async def test_connection_error_translated(patched_client: Any) -> None:
    patched_client.chat.completions.create = AsyncMock(side_effect=_FakeConnErr("down"))
    llm = XiaomiLLM(model="m", base_url="u", api_key="k")
    with pytest.raises(LLMConnectionError, match="down"):
        await _collect(llm.chat_completion_stream(messages=[]))


@pytest.mark.asyncio
async def test_rate_limit_error_translated(patched_client: Any) -> None:
    patched_client.chat.completions.create = AsyncMock(side_effect=_FakeRateLimitErr("slow down"))
    llm = XiaomiLLM(model="m", base_url="u", api_key="k")
    with pytest.raises(LLMRateLimitError, match="slow down"):
        await _collect(llm.chat_completion_stream(messages=[]))


@pytest.mark.asyncio
async def test_api_error_translated(patched_client: Any) -> None:
    patched_client.chat.completions.create = AsyncMock(side_effect=_FakeAPIErr("bad api"))
    llm = XiaomiLLM(model="m", base_url="u", api_key="k")
    with pytest.raises(LLMAPIError, match="bad api"):
        await _collect(llm.chat_completion_stream(messages=[]))


@pytest.mark.asyncio
async def test_unknown_error_translated_to_api_error(patched_client: Any) -> None:
    patched_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("unexpected"))
    llm = XiaomiLLM(model="m", base_url="u", api_key="k")
    with pytest.raises(LLMAPIError, match="unexpected"):
        await _collect(llm.chat_completion_stream(messages=[]))
