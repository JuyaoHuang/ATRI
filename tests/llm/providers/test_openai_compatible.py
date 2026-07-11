"""Tests for src.llm.providers.openai_compatible.

All tests mock ``AsyncOpenAI`` -- no real network calls are made.

测试目的：验证 OpenAI 兼容提供商的行为——所有测试都 mock ``AsyncOpenAI``，
不会发起真实网络请求。覆盖点包括：工厂注册绑定、按序产出非空 delta、
跳过空 delta、``system`` 提示的前置与省略、``temperature`` 参数的启用/省略、
``tools`` 参数被接受但忽略，以及 SDK 异常（连接错误、速率限制、API 错误、
未知错误）到项目本地异常的正确转换。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from copy import deepcopy
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
from src.llm.providers.openai_compatible import OpenAICompatibleLLM
from src.vision import InputImage


def _chunk(text: str | None) -> SimpleNamespace:
    """Shape-compatible stand-in for an openai ChatCompletionChunk."""
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


class _FakeStream:
    """Async-iterable substitute for ``openai.AsyncStream``."""

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
    """Patch AsyncOpenAI in the provider module; yield the mock client."""
    with patch("src.llm.providers.openai_compatible.AsyncOpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        yield mock_client


async def _collect(stream: AsyncIterator[str]) -> list[str]:
    return [chunk async for chunk in stream]


def _image() -> InputImage:
    return InputImage(
        source="screen",
        media_type="image/jpeg",
        encoding="base64",
        data="c21hbGwtaW1hZ2U=",
    )


def test_factory_registration_binds_openai_compatible() -> None:
    assert LLMFactory._registry.get("openai_compatible") is OpenAICompatibleLLM


def test_factory_registration_binds_openai_alias() -> None:
    assert LLMFactory._registry.get("openai") is OpenAICompatibleLLM


@pytest.mark.asyncio
async def test_stream_yields_non_empty_deltas_in_order(patched_client: Any) -> None:
    patched_client.chat.completions.create = AsyncMock(
        return_value=_FakeStream([_chunk("he"), _chunk("llo"), _chunk(None), _chunk(" world")])
    )
    llm = OpenAICompatibleLLM(model="m", base_url="u", api_key="k")
    chunks = await _collect(
        llm.chat_completion_stream(messages=[{"role": "user", "content": "hi"}])
    )
    assert chunks == ["he", "llo", " world"]


@pytest.mark.asyncio
async def test_empty_delta_strings_are_skipped(patched_client: Any) -> None:
    patched_client.chat.completions.create = AsyncMock(
        return_value=_FakeStream([_chunk(""), _chunk("a"), _chunk("")])
    )
    llm = OpenAICompatibleLLM(model="m", base_url="u", api_key="k")
    chunks = await _collect(llm.chat_completion_stream(messages=[]))
    assert chunks == ["a"]


@pytest.mark.asyncio
async def test_system_prompt_prepended_when_provided(patched_client: Any) -> None:
    patched_client.chat.completions.create = AsyncMock(return_value=_FakeStream([]))
    llm = OpenAICompatibleLLM(model="m", base_url="u", api_key="k")
    await _collect(
        llm.chat_completion_stream(
            messages=[{"role": "user", "content": "hi"}],
            system="you are helpful",
        )
    )
    call_kwargs = patched_client.chat.completions.create.await_args.kwargs
    assert call_kwargs["messages"] == [
        {"role": "system", "content": "you are helpful"},
        {"role": "user", "content": "hi"},
    ]


@pytest.mark.asyncio
async def test_no_system_prompt_leaves_messages_untouched(
    patched_client: Any,
) -> None:
    patched_client.chat.completions.create = AsyncMock(return_value=_FakeStream([]))
    llm = OpenAICompatibleLLM(model="m", base_url="u", api_key="k")
    await _collect(llm.chat_completion_stream(messages=[{"role": "user", "content": "hi"}]))
    call_kwargs = patched_client.chat.completions.create.await_args.kwargs
    assert call_kwargs["messages"] == [{"role": "user", "content": "hi"}]


@pytest.mark.asyncio
async def test_image_multimodalizes_only_current_user_without_mutating_input(
    patched_client: Any,
) -> None:
    patched_client.chat.completions.create = AsyncMock(return_value=_FakeStream([]))
    llm = OpenAICompatibleLLM(
        model="m",
        base_url="u",
        api_key="k",
        image_detail="high",
    )
    messages = [
        {"role": "user", "content": "old"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "current"},
    ]
    before = deepcopy(messages)

    await _collect(llm.chat_completion_stream(messages=messages, input_image=_image()))

    assert messages == before
    request_messages = patched_client.chat.completions.create.await_args.kwargs["messages"]
    assert request_messages[:2] == before[:2]
    content = request_messages[-1]["content"]
    assert content[0] == {"type": "text", "text": "current"}
    assert content[1]["image_url"]["detail"] == "high"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_invalid_image_detail_is_rejected_before_client_creation() -> None:
    with pytest.raises(ValueError, match="detail"):
        OpenAICompatibleLLM(
            model="m",
            base_url="u",
            api_key="k",
            image_detail="original",  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_temperature_included_in_params_when_set(patched_client: Any) -> None:
    patched_client.chat.completions.create = AsyncMock(return_value=_FakeStream([]))
    llm = OpenAICompatibleLLM(model="m", base_url="u", api_key="k", temperature=0.42)
    await _collect(llm.chat_completion_stream(messages=[]))
    call_kwargs = patched_client.chat.completions.create.await_args.kwargs
    assert call_kwargs["temperature"] == 0.42
    assert call_kwargs["stream"] is True
    assert call_kwargs["model"] == "m"


@pytest.mark.asyncio
async def test_temperature_omitted_when_unset(patched_client: Any) -> None:
    patched_client.chat.completions.create = AsyncMock(return_value=_FakeStream([]))
    llm = OpenAICompatibleLLM(model="m", base_url="u", api_key="k")
    await _collect(llm.chat_completion_stream(messages=[]))
    call_kwargs = patched_client.chat.completions.create.await_args.kwargs
    assert "temperature" not in call_kwargs


@pytest.mark.asyncio
async def test_tools_parameter_accepted_but_ignored(patched_client: Any) -> None:
    patched_client.chat.completions.create = AsyncMock(return_value=_FakeStream([]))
    llm = OpenAICompatibleLLM(model="m", base_url="u", api_key="k")
    await _collect(llm.chat_completion_stream(messages=[], tools=[{"name": "t"}]))
    call_kwargs = patched_client.chat.completions.create.await_args.kwargs
    assert "tools" not in call_kwargs


@pytest.mark.asyncio
async def test_connection_error_translated(patched_client: Any) -> None:
    patched_client.chat.completions.create = AsyncMock(side_effect=_FakeConnErr("down"))
    llm = OpenAICompatibleLLM(model="m", base_url="u", api_key="k")
    with pytest.raises(LLMConnectionError, match="provider connection failed"):
        await _collect(llm.chat_completion_stream(messages=[]))


@pytest.mark.asyncio
async def test_rate_limit_error_translated(patched_client: Any) -> None:
    patched_client.chat.completions.create = AsyncMock(side_effect=_FakeRateLimitErr("slow down"))
    llm = OpenAICompatibleLLM(model="m", base_url="u", api_key="k")
    with pytest.raises(LLMRateLimitError, match="provider rate limit exceeded"):
        await _collect(llm.chat_completion_stream(messages=[]))


@pytest.mark.asyncio
async def test_api_error_translated(patched_client: Any) -> None:
    patched_client.chat.completions.create = AsyncMock(side_effect=_FakeAPIErr("bad api"))
    llm = OpenAICompatibleLLM(model="m", base_url="u", api_key="k")
    with pytest.raises(LLMAPIError, match="provider API request failed"):
        await _collect(llm.chat_completion_stream(messages=[]))


@pytest.mark.asyncio
async def test_unknown_error_translated_to_api_error(patched_client: Any) -> None:
    sensitive = "data:image/jpeg;base64,SENSITIVE_IMAGE"
    patched_client.chat.completions.create = AsyncMock(side_effect=RuntimeError(sensitive))
    llm = OpenAICompatibleLLM(model="m", base_url="u", api_key="k")
    with pytest.raises(LLMAPIError, match="provider request failed") as raised:
        await _collect(llm.chat_completion_stream(messages=[]))

    assert sensitive not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
