"""Microsoft Edge TTS provider."""

from __future__ import annotations

import importlib.util
from typing import Any

from src.tts.exceptions import TTSProviderUnavailableError, TTSSynthesisError
from src.tts.factory import TTSFactory, TTSProviderMetadata
from src.tts.interface import TTSHealth, TTSInterface, TTSVoice


def _media_type_from_format(audio_format: str) -> str:
    value = audio_format.lower().lstrip(".")
    if value == "mp3":
        return "audio/mpeg"
    if value == "wav":
        return "audio/wav"
    if value == "ogg":
        return "audio/ogg"
    return f"audio/{value}" if value else "audio/mpeg"


@TTSFactory.register(
    "edge_tts",
    metadata=TTSProviderMetadata(
        name="edge_tts",
        display_name="Microsoft Edge TTS",
        provider_type="cloud",
        supports_streaming=False,
        media_type="audio/mpeg",
        description="Free Microsoft Edge neural voices through the edge-tts package.",
    ),
)
class EdgeTTSProvider(TTSInterface):
    """Complete-audio Edge TTS provider."""

    def __init__(self, **config: Any) -> None:
        super().__init__(**config)
        self.voice = str(config.get("voice") or "zh-CN-XiaoxiaoNeural")
        self.rate = str(config.get("rate") or "+0%")
        self.pitch = str(config.get("pitch") or "+0Hz")
        self.volume = str(config.get("volume") or "+0%")
        self.output_format = str(config.get("format") or "mp3")
        self.media_type = _media_type_from_format(self.output_format)

    def health(self) -> TTSHealth:
        if importlib.util.find_spec("edge_tts") is None:
            return TTSHealth(False, "Python package 'edge-tts' is not installed")
        if not self.voice:
            return TTSHealth(False, "edge_tts.voice is not configured")
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
            raise TTSProviderUnavailableError(health.reason or "edge_tts is unavailable")

        try:
            import edge_tts
        except ImportError as error:
            raise TTSProviderUnavailableError(
                "Python package 'edge-tts' is not installed"
            ) from error

        voice = voice_id or str(kwargs.get("voice") or self.voice)
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=str(kwargs.get("rate") or self.rate),
            pitch=str(kwargs.get("pitch") or self.pitch),
            volume=str(kwargs.get("volume") or self.volume),
        )

        audio = bytearray()
        try:
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    audio.extend(chunk.get("data") or b"")
        except Exception as error:  # noqa: BLE001
            raise TTSSynthesisError(f"edge_tts synthesis failed: {error}") from error

        if not audio:
            raise TTSSynthesisError("edge_tts returned empty audio")
        return bytes(audio)

    async def get_voices(self) -> list[TTSVoice]:
        health = self.health()
        if not health.available:
            raise TTSProviderUnavailableError(health.reason or "edge_tts is unavailable")

        try:
            import edge_tts
        except ImportError as error:
            raise TTSProviderUnavailableError(
                "Python package 'edge-tts' is not installed"
            ) from error

        raw_voices = await edge_tts.list_voices()
        voices: list[TTSVoice] = []
        for raw in raw_voices:
            voice_id = str(raw.get("ShortName") or "")
            if not voice_id:
                continue
            voices.append(
                TTSVoice(
                    id=voice_id,
                    name=str(raw.get("FriendlyName") or voice_id),
                    language=str(raw.get("Locale") or "") or None,
                    gender=str(raw.get("Gender") or "") or None,
                )
            )
        return voices
