"""OpenAI Whisper-compatible cloud ASR provider.

OpenAI Whisper 兼容的云端 ASR 提供商模块。

Provides cloud-based audio transcription through the OpenAI-compatible
SDK.  Audio bytes are written to a temporary file and sent via the
``audio.transcriptions`` API.

通过 OpenAI 兼容 SDK 提供基于云端的音频转录。音频字节写入临时文件后通过
``audio.transcriptions`` API 发送。

Reference: docs/ASR模块设计文档.md
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path
from typing import Any

from src.asr.exceptions import ASRProviderUnavailableError
from src.asr.factory import ASRFactory, ASRProviderMetadata
from src.asr.interface import ASRAudioUploadMetadata, ASRHealth, ASRInterface


@ASRFactory.register(
    "openai_whisper",
    metadata=ASRProviderMetadata(
        name="openai_whisper",
        display_name="OpenAI Whisper",
        provider_type="cloud",
        supports_backend_transcription=True,
        supports_browser_streaming=False,
        description="Cloud audio transcription through the OpenAI-compatible SDK.",
    ),
)
class OpenAIWhisperASR(ASRInterface):
    """Cloud transcription provider with lazy OpenAI client creation.

    云端转录提供商，延迟创建 OpenAI 客户端。

    This provider does **not** support numpy-array transcription; it
    only accepts uploaded audio bytes.  The OpenAI client is created
    per-request to avoid holding credentials in long-lived objects.

    此提供商**不**支持 numpy 数组转录；仅接受上传的音频字节。OpenAI 客户端
    每次请求时创建，避免在长生命周期对象中持有凭证。
    """

    def __init__(self, **config: Any) -> None:
        super().__init__(**config)
        self.model = str(config.get("model") or "whisper-1")
        self.api_key = str(config.get("api_key") or "")
        self.base_url = str(config.get("base_url") or "")
        self.language = str(config.get("language") or "")
        self.prompt = str(config.get("prompt") or "")

    def health(self) -> ASRHealth:
        if importlib.util.find_spec("openai") is None:
            return ASRHealth(False, "Python package 'openai' is not installed")
        if not self.api_key or self.api_key.startswith("${"):
            return ASRHealth(False, "openai_whisper.api_key is not configured")
        if not self.model:
            return ASRHealth(False, "openai_whisper.model is not configured")
        return ASRHealth(True)

    def transcribe_np(self, audio: Any) -> str:
        """Not supported — cloud providers do not accept numpy arrays.

        不支持 — 云端提供商不接受 numpy 数组。

        Always raises ``ASRProviderUnavailableError``.

        始终抛出 ``ASRProviderUnavailableError``。
        """
        raise ASRProviderUnavailableError(
            "openai_whisper accepts uploaded audio files, not numpy arrays"
        )

    async def async_transcribe_audio(
        self,
        audio: bytes,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        upload_metadata: ASRAudioUploadMetadata | None = None,
    ) -> str:
        """Transcribe uploaded audio bytes via the OpenAI API.

        通过 OpenAI API 转录上传的音频字节。

        Audio is written to a temporary file (preserving the original
        extension) and sent to the ``audio.transcriptions`` endpoint.

        音频写入临时文件（保留原始扩展名）并发送到 ``audio.transcriptions`` 端点。
        """
        health = self.health()
        if not health.available:
            raise ASRProviderUnavailableError(health.reason or "openai_whisper is unavailable")

        suffix = Path(filename or "recording.wav").suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as temp_audio:
            temp_audio.write(audio)
            temp_audio.flush()
            return await self._transcribe_file(temp_audio.name)

    async def _transcribe_file(self, path: str) -> str:
        from openai import AsyncOpenAI

        client_kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        client = AsyncOpenAI(**client_kwargs)

        kwargs: dict[str, Any] = {"model": self.model}
        if self.language:
            kwargs["language"] = self.language
        if self.prompt:
            kwargs["prompt"] = self.prompt

        with Path(path).open("rb") as audio_file:
            response = await client.audio.transcriptions.create(file=audio_file, **kwargs)

        return str(getattr(response, "text", "") or "")
