"""Tests for the dedicated SiliconFlow LLM provider registration.

These tests verify that ``siliconflow`` resolves to its own provider class
while preserving the shared OpenAI-compatible constructor behaviour.  No
network calls are made.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.llm.factory import LLMFactory
from src.llm.providers.openai_compatible import OpenAICompatibleLLM
from src.llm.providers.siliconflow import SiliconFlowLLM
from src.vision import InputImage


class _EmptyStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


def test_factory_registration_binds_siliconflow_provider() -> None:
    assert LLMFactory._registry.get("siliconflow") is SiliconFlowLLM
    assert SiliconFlowLLM is not OpenAICompatibleLLM
    assert issubclass(SiliconFlowLLM, OpenAICompatibleLLM)


def test_factory_creates_siliconflow_provider_with_existing_config_shape() -> None:
    with patch("src.llm.providers.openai_compatible.AsyncOpenAI") as client_cls:
        llm = LLMFactory.create(
            "siliconflow",
            model="deepseek-ai/DeepSeek-V4-Flash",
            base_url="https://api.siliconflow.cn/v1",
            api_key="test-key",
            temperature=0.8,
        )

    assert type(llm) is SiliconFlowLLM
    assert llm.model == "deepseek-ai/DeepSeek-V4-Flash"
    assert llm.base_url == "https://api.siliconflow.cn/v1"
    assert llm.api_key == "test-key"
    assert llm.temperature == 0.8
    client_cls.assert_called_once_with(
        base_url="https://api.siliconflow.cn/v1",
        api_key="test-key",
    )


@pytest.mark.asyncio
async def test_siliconflow_inherits_multimodal_serialization() -> None:
    with patch("src.llm.providers.openai_compatible.AsyncOpenAI") as client_cls:
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=AsyncMock(return_value=_EmptyStream()))
            )
        )
        client_cls.return_value = client
        llm = SiliconFlowLLM(
            model="vision-model",
            base_url="https://api.siliconflow.cn/v1",
            api_key="test-key",
            image_detail="low",
        )

        image = InputImage(
            source="screen",
            media_type="image/jpeg",
            encoding="base64",
            data="c21hbGwtaW1hZ2U=",
        )
        _ = [
            chunk
            async for chunk in llm.chat_completion_stream(
                [{"role": "user", "content": "describe"}],
                input_image=image,
            )
        ]

    content = client.chat.completions.create.await_args.kwargs["messages"][-1]["content"]
    assert content[0] == {"type": "text", "text": "describe"}
    assert content[1]["image_url"]["detail"] == "low"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
