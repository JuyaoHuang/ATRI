"""Tests for the dedicated SiliconFlow LLM provider registration.

These tests verify that ``siliconflow`` resolves to its own provider class
while preserving the shared OpenAI-compatible constructor behaviour.  No
network calls are made.
"""

from __future__ import annotations

from unittest.mock import patch

from src.llm.factory import LLMFactory
from src.llm.providers.openai_compatible import OpenAICompatibleLLM
from src.llm.providers.siliconflow import SiliconFlowLLM


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
