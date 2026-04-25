"""CosyVoice3 Gradio TTS provider."""

from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path
from typing import Any

from src.tts.exceptions import TTSAPIError, TTSProviderUnavailableError
from src.tts.factory import TTSFactory, TTSProviderMetadata
from src.tts.interface import TTSHealth, TTSInterface, TTSVoice

DEFAULT_PROMPT_WAV_URL = (
    "https://github.com/gradio-app/gradio/raw/main/test/test_files/audio_sample.wav"
)
DEFAULT_MODE = "\u9884\u8bad\u7ec3\u97f3\u8272"
DEFAULT_SFT_VOICE = "\u4e2d\u6587\u5973"


def _load_gradio_client() -> tuple[Any, Any]:
    try:
        from gradio_client import Client, handle_file
    except ImportError as error:
        raise TTSProviderUnavailableError(
            "Python package 'gradio-client' is not installed"
        ) from error
    return Client, handle_file


@TTSFactory.register(
    "cosyvoice3_tts",
    metadata=TTSProviderMetadata(
        name="cosyvoice3_tts",
        display_name="CosyVoice3",
        provider_type="local",
        supports_streaming=False,
        media_type="audio/wav",
        description="Local CosyVoice3 Gradio API compatible with Open-LLM-VTuber.",
    ),
)
class CosyVoice3TTSProvider(TTSInterface):
    """Complete-audio CosyVoice3 provider through the Gradio client."""

    def __init__(self, **config: Any) -> None:
        super().__init__(**config)
        self.client_url = str(config.get("client_url") or "http://127.0.0.1:50000/")
        self.mode_checkbox_group = str(config.get("mode_checkbox_group") or DEFAULT_MODE)
        self.sft_dropdown = str(config.get("sft_dropdown") or DEFAULT_SFT_VOICE)
        self.prompt_text = str(config.get("prompt_text") or "")
        self.prompt_wav_upload_url = str(
            config.get("prompt_wav_upload_url") or DEFAULT_PROMPT_WAV_URL
        )
        self.prompt_wav_record_url = str(
            config.get("prompt_wav_record_url") or DEFAULT_PROMPT_WAV_URL
        )
        self.instruct_text = str(config.get("instruct_text") or "")
        self.stream = bool(config.get("stream", False))
        self.seed = int(config.get("seed") or 0)
        self.speed = float(config.get("speed") or 1.0)
        self.api_name = str(config.get("api_name") or "/generate_audio")
        self.media_type = "audio/wav"

    def health(self) -> TTSHealth:
        if not self.client_url:
            return TTSHealth(False, "cosyvoice3_tts.client_url is not configured")
        if importlib.util.find_spec("gradio_client") is None:
            return TTSHealth(False, "Python package 'gradio-client' is not installed")
        return TTSHealth(True, "Gradio endpoint availability is checked during synthesis")

    async def synthesize(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        **kwargs: Any,
    ) -> bytes:
        health = self.health()
        if not health.available:
            raise TTSProviderUnavailableError(health.reason or "cosyvoice3_tts is unavailable")

        return await asyncio.to_thread(self._synthesize_sync, text, voice_id, kwargs)

    async def get_voices(self) -> list[TTSVoice]:
        return [
            TTSVoice(
                id=self.sft_dropdown,
                name=self.sft_dropdown,
                description="Configured CosyVoice SFT voice.",
            )
        ]

    def _synthesize_sync(
        self,
        text: str,
        voice_id: str | None,
        kwargs: dict[str, Any],
    ) -> bytes:
        Client, handle_file = _load_gradio_client()
        try:
            client = Client(self.client_url)
            result = client.predict(
                tts_text=text,
                mode_checkbox_group=str(
                    kwargs.get("mode_checkbox_group") or self.mode_checkbox_group
                ),
                sft_dropdown=voice_id or str(kwargs.get("sft_dropdown") or self.sft_dropdown),
                prompt_text=str(kwargs.get("prompt_text") or self.prompt_text),
                prompt_wav_upload=handle_file(
                    str(kwargs.get("prompt_wav_upload_url") or self.prompt_wav_upload_url)
                ),
                prompt_wav_record=handle_file(
                    str(kwargs.get("prompt_wav_record_url") or self.prompt_wav_record_url)
                ),
                instruct_text=str(kwargs.get("instruct_text") or self.instruct_text),
                stream=bool(kwargs.get("stream", self.stream)),
                seed=int(kwargs.get("seed") or self.seed),
                speed=float(kwargs.get("speed") or self.speed),
                api_name=self.api_name,
            )
        except TTSProviderUnavailableError:
            raise
        except Exception as error:
            raise TTSAPIError(f"cosyvoice3_tts request failed: {error}") from error

        audio = self._read_audio_result(result)
        if not audio:
            raise TTSAPIError("cosyvoice3_tts returned empty audio")
        return audio

    def _read_audio_result(self, result: Any) -> bytes:
        if isinstance(result, bytes | bytearray):
            return bytes(result)
        if isinstance(result, str | os.PathLike):
            return self._read_audio_path(Path(result))
        if isinstance(result, dict):
            for key in ("path", "name", "file"):
                value = result.get(key)
                if value:
                    return self._read_audio_result(value)
        if isinstance(result, list | tuple):
            for value in result:
                try:
                    audio = self._read_audio_result(value)
                except TTSAPIError:
                    continue
                if audio:
                    return audio
        raise TTSAPIError(f"cosyvoice3_tts returned unsupported result: {type(result).__name__}")

    def _read_audio_path(self, path: Path) -> bytes:
        if not path.is_file():
            raise TTSAPIError(f"cosyvoice3_tts result file does not exist: {path}")
        return path.read_bytes()
