"""Xiaomi MiMo LLM provider.

Uses the ``openai`` SDK's ``AsyncOpenAI`` client against Xiaomi's
OpenAI-compatible endpoint, but keeps Xiaomi-specific request parameters
isolated from the generic ``openai_compatible`` provider.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from openai import (
    APIConnectionError,
    APIError,
    AsyncOpenAI,
    RateLimitError,
)

from src.llm.exceptions import (
    LLMAPIError,
    LLMConnectionError,
    LLMRateLimitError,
)
from src.llm.factory import LLMFactory
from src.llm.interface import LLMInterface
from src.llm.multimodal import (
    SUPPORTED_IMAGE_DETAILS,
    ImageDetail,
    build_multimodal_messages,
)
from src.vision.models import InputImage

_REQUEST_OPTION_KEYS = (
    "max_completion_tokens",
    "top_p",
    "stop",
    "frequency_penalty",
    "presence_penalty",
    "extra_body",
)


def _extract_content(chunk: Any) -> str | None:
    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return None

    delta = getattr(choices[0], "delta", None)
    if delta is None:
        return None

    content = getattr(delta, "content", None)
    return content if content else None


@LLMFactory.register("xiaomi")
class XiaomiLLM(LLMInterface):
    """Xiaomi MiMo provider using an OpenAI-compatible chat-completions API."""

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        temperature: float | None = None,
        request_options: dict[str, Any] | None = None,
        image_detail: ImageDetail = "auto",
        **extra: Any,
    ) -> None:
        if image_detail not in SUPPORTED_IMAGE_DETAILS:
            raise ValueError(f"Unsupported image detail: {image_detail!r}")
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.temperature = temperature
        self.request_options = dict(request_options or {})
        self.image_detail = image_detail
        self.extra = extra
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        *,
        input_image: InputImage | None = None,
    ) -> AsyncIterator[str]:
        request_messages = build_multimodal_messages(
            messages,
            input_image,
            image_detail=self.image_detail,
        )
        payload: list[dict[str, Any]] = (
            [{"role": "system", "content": system}, *request_messages]
            if system is not None
            else list(request_messages)
        )

        params: dict[str, Any] = {
            "model": self.model,
            "messages": payload,
            "stream": True,
        }
        if self.temperature is not None:
            params["temperature"] = self.temperature

        for key in _REQUEST_OPTION_KEYS:
            value = self.request_options.get(key)
            if value is not None:
                params[key] = value

        try:
            stream = await self.client.chat.completions.create(**params)
            async for chunk in stream:
                content = _extract_content(chunk)
                if content:
                    yield content
        except APIConnectionError as exc:
            raise LLMConnectionError(str(exc)) from exc
        except RateLimitError as exc:
            raise LLMRateLimitError(str(exc)) from exc
        except APIError as exc:
            raise LLMAPIError(str(exc)) from exc
        except Exception as exc:
            raise LLMAPIError(str(exc)) from exc
