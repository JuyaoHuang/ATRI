"""SiliconFlow TTS provider."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from src.tts.exceptions import TTSAPIError, TTSProviderUnavailableError, TTSRateLimitError
from src.tts.factory import TTSFactory, TTSProviderMetadata
from src.tts.interface import TTSHealth, TTSInterface, TTSVoice

DEFAULT_SILICONFLOW_MODEL = "FunAudioLLM/CosyVoice2-0.5B"
DEFAULT_SILICONFLOW_VOICE = f"{DEFAULT_SILICONFLOW_MODEL}:claire"
SYSTEM_VOICE_NAMES = ("alex", "benjamin", "charles", "david", "anna", "bella", "claire", "diana")


def _media_type_from_format(audio_format: str) -> str:
    value = audio_format.lower().lstrip(".")
    if value == "mp3":
        return "audio/mpeg"
    if value == "wav":
        return "audio/wav"
    if value == "ogg":
        return "audio/ogg"
    if value == "opus":
        return "audio/ogg"
    return f"audio/{value}" if value else "audio/mpeg"


def _secret_is_configured(value: str) -> bool:
    return bool(value) and not (value.startswith("${") and value.endswith("}"))


@TTSFactory.register(
    "siliconflow_tts",
    metadata=TTSProviderMetadata(
        name="siliconflow_tts",
        display_name="SiliconFlow TTS",
        provider_type="cloud",
        supports_streaming=False,
        media_type="audio/mpeg",
        description="SiliconFlow audio speech API.",
    ),
)
class SiliconFlowTTSProvider(TTSInterface):
    """Complete-audio SiliconFlow TTS provider."""

    def __init__(self, **config: Any) -> None:
        super().__init__(**config)
        self.api_key = str(config.get("api_key") or "")
        self.api_url = str(config.get("api_url") or "https://api.siliconflow.cn/v1/audio/speech")
        self.default_model = str(config.get("default_model") or DEFAULT_SILICONFLOW_MODEL)
        self.default_voice = str(
            config.get("default_voice") or self._default_voice_for_model(self.default_model)
        )
        self.sample_rate = int(config.get("sample_rate") or 32000)
        self.response_format = str(config.get("response_format") or "mp3")
        self.stream = bool(config.get("stream", False))
        self.speed = float(config.get("speed") or 1.0)
        self.gain = float(config.get("gain") or 0.0)
        self.timeout_seconds = float(config.get("timeout_seconds") or 120)
        self.media_type = _media_type_from_format(self.response_format)

    def health(self) -> TTSHealth:
        if not self.api_url:
            return TTSHealth(False, "siliconflow_tts.api_url is not configured")
        if not _secret_is_configured(self.api_key):
            return TTSHealth(False, "siliconflow_tts.api_key is not configured")
        return TTSHealth(True)

    async def synthesize(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        **kwargs: Any,
    ) -> bytes:
        health = self.health()
        if not health.available:
            raise TTSProviderUnavailableError(health.reason or "siliconflow_tts is unavailable")

        response_format = str(kwargs.get("response_format") or self.response_format)
        payload = {
            "input": text,
            "response_format": response_format,
            "sample_rate": int(kwargs.get("sample_rate") or self.sample_rate),
            "stream": bool(kwargs.get("stream", self.stream)),
            "speed": float(kwargs.get("speed") or self.speed),
            "gain": float(kwargs.get("gain") or self.gain),
            "model": str(kwargs.get("model") or self.default_model),
            "voice": voice_id or str(kwargs.get("voice") or self.default_voice),
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.api_url, json=payload, headers=headers)
        except httpx.HTTPError as error:
            raise TTSAPIError(f"siliconflow_tts request failed: {error}") from error

        if response.status_code == 429:
            raise TTSRateLimitError("siliconflow_tts rate limit exceeded")
        if response.status_code >= 400:
            raise TTSAPIError(
                f"siliconflow_tts returned HTTP {response.status_code}: {response.text[:200]}"
            )
        if not response.content:
            raise TTSAPIError("siliconflow_tts returned empty audio")

        self.media_type = _media_type_from_format(response_format)
        return response.content

    async def get_voices(self) -> list[TTSVoice]:
        voices = self._system_voices_for_model(self.default_model)
        if _secret_is_configured(self.api_key):
            voices.extend(await self._fetch_custom_voices())

        if self.default_voice and self.default_voice not in {voice.id for voice in voices}:
            voices.insert(
                0,
                TTSVoice(
                    id=self.default_voice,
                    name=self.default_voice,
                    description="Configured SiliconFlow voice.",
                ),
            )

        return self._dedupe_voices(voices)

    def _default_voice_for_model(self, model: str) -> str:
        return f"{model or DEFAULT_SILICONFLOW_MODEL}:claire"

    def _system_voices_for_model(self, model: str) -> list[TTSVoice]:
        if not model:
            return []

        return [
            TTSVoice(
                id=f"{model}:{voice_name}",
                name=voice_name,
                description=f"SiliconFlow system voice for {model}.",
            )
            for voice_name in SYSTEM_VOICE_NAMES
        ]

    async def _fetch_custom_voices(self) -> list[TTSVoice]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(self._voice_list_url(), headers=headers)
            if response.status_code >= 400:
                return []
            payload = response.json()
        except Exception:
            return []

        return self._parse_custom_voice_payload(payload)

    def _voice_list_url(self) -> str:
        parts = urlsplit(self.api_url)
        path = parts.path
        if "/audio/speech" in path:
            path = path.replace("/audio/speech", "/audio/voice/list")
        elif path.endswith("/v1"):
            path = f"{path}/audio/voice/list"
        else:
            path = "/v1/audio/voice/list"
        return urlunsplit((parts.scheme, parts.netloc, path, "", ""))

    def _parse_custom_voice_payload(self, payload: Any) -> list[TTSVoice]:
        candidates = payload
        if isinstance(payload, dict):
            for key in ("data", "voices", "result", "items"):
                if isinstance(payload.get(key), list):
                    candidates = payload[key]
                    break

        if not isinstance(candidates, list):
            return []

        voices: list[TTSVoice] = []
        for item in candidates:
            if isinstance(item, str):
                voices.append(
                    TTSVoice(id=item, name=item, description="SiliconFlow custom voice.")
                )
                continue

            if not isinstance(item, dict):
                continue

            voice_id = str(item.get("uri") or item.get("id") or item.get("voice") or "")
            if not voice_id:
                continue
            voices.append(
                TTSVoice(
                    id=voice_id,
                    name=str(item.get("name") or item.get("customName") or voice_id),
                    description="SiliconFlow custom voice.",
                )
            )
        return voices

    def _dedupe_voices(self, voices: list[TTSVoice]) -> list[TTSVoice]:
        seen: set[str] = set()
        deduped: list[TTSVoice] = []
        for voice in voices:
            if voice.id in seen:
                continue
            seen.add(voice.id)
            deduped.append(voice)
        return deduped
