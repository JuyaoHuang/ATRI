"""GPT-SoVITS HTTP TTS provider."""

from __future__ import annotations

import re
from typing import Any

import httpx

from src.tts.exceptions import TTSAPIError, TTSProviderUnavailableError, TTSRateLimitError
from src.tts.factory import TTSFactory, TTSProviderMetadata
from src.tts.interface import TTSHealth, TTSInterface, TTSVoice

_BRACKETED_TEXT = re.compile(r"\[.*?\]")


def _media_type_from_format(audio_format: str) -> str:
    value = audio_format.lower().lstrip(".")
    if value == "mp3":
        return "audio/mpeg"
    if value == "wav":
        return "audio/wav"
    if value == "ogg":
        return "audio/ogg"
    return f"audio/{value}" if value else "audio/wav"


@TTSFactory.register(
    "gpt_sovits_tts",
    metadata=TTSProviderMetadata(
        name="gpt_sovits_tts",
        display_name="GPT-SoVITS",
        provider_type="local",
        supports_streaming=False,
        media_type="audio/wav",
        description="Local GPT-SoVITS HTTP API compatible with Open-LLM-VTuber.",
    ),
)
class GPTSoVITSTTSProvider(TTSInterface):
    """Complete-audio GPT-SoVITS provider."""

    def __init__(self, **config: Any) -> None:
        super().__init__(**config)
        self.api_url = str(config.get("api_url") or "http://127.0.0.1:9880/tts")
        self.text_lang = str(config.get("text_lang") or "zh")
        self.ref_audio_path = str(config.get("ref_audio_path") or "")
        self.prompt_lang = str(config.get("prompt_lang") or "zh")
        self.prompt_text = str(config.get("prompt_text") or "")
        self.text_split_method = str(config.get("text_split_method") or "cut5")
        self.batch_size = str(config.get("batch_size") or "1")
        self.output_format = str(config.get("media_type") or "wav")
        self.streaming_mode = str(config.get("streaming_mode") or "false")
        self.timeout_seconds = float(config.get("timeout_seconds") or 120)
        self.media_type = _media_type_from_format(self.output_format)

    def health(self) -> TTSHealth:
        if not self.api_url:
            return TTSHealth(False, "gpt_sovits_tts.api_url is not configured")
        return TTSHealth(True, "HTTP endpoint availability is checked during synthesis")

    async def synthesize(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        **kwargs: Any,
    ) -> bytes:
        health = self.health()
        if not health.available:
            raise TTSProviderUnavailableError(health.reason or "gpt_sovits_tts is unavailable")

        params = {
            "text": _BRACKETED_TEXT.sub("", text).strip(),
            "text_lang": str(kwargs.get("text_lang") or self.text_lang),
            "ref_audio_path": str(kwargs.get("ref_audio_path") or self.ref_audio_path),
            "prompt_lang": str(kwargs.get("prompt_lang") or self.prompt_lang),
            "prompt_text": str(kwargs.get("prompt_text") or self.prompt_text),
            "text_split_method": str(kwargs.get("text_split_method") or self.text_split_method),
            "batch_size": str(kwargs.get("batch_size") or self.batch_size),
            "media_type": str(kwargs.get("media_type") or self.output_format),
            "streaming_mode": str(kwargs.get("streaming_mode") or self.streaming_mode),
        }
        if not params["text"]:
            params["text"] = text

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.api_url, params=params)
        except httpx.HTTPError as error:
            raise TTSAPIError(f"gpt_sovits_tts request failed: {error}") from error

        if response.status_code == 429:
            raise TTSRateLimitError("gpt_sovits_tts rate limit exceeded")
        if response.status_code >= 400:
            raise TTSAPIError(
                f"gpt_sovits_tts returned HTTP {response.status_code}: {response.text[:200]}"
            )
        if not response.content:
            raise TTSAPIError("gpt_sovits_tts returned empty audio")
        return response.content

    async def get_voices(self) -> list[TTSVoice]:
        return [
            TTSVoice(
                id="default",
                name="GPT-SoVITS Default",
                language=self.text_lang,
                description="Voice is determined by ref_audio_path and prompt_text.",
            )
        ]
