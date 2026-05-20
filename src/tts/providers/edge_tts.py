"""Microsoft Edge TTS provider.

Microsoft Edge TTS 提供商。

Uses the ``edge-tts`` Python package to access free Microsoft Edge neural
voices.  No API key is required.

使用 ``edge-tts`` Python 包访问免费的 Microsoft Edge 神经语音。无需 API 密钥。

Reference: docs/TTS模块设计文档.md
"""

from __future__ import annotations

import importlib.util
from typing import Any

from src.tts.exceptions import TTSProviderUnavailableError, TTSSynthesisError
from src.tts.factory import TTSFactory, TTSProviderMetadata
from src.tts.interface import TTSHealth, TTSInterface, TTSVoice


def _media_type_from_format(audio_format: str) -> str:
    """Map an audio format string to a MIME type.

    将音频格式字符串映射为 MIME 类型。

    Args:
        audio_format: Format extension (e.g. ``"mp3"``, ``"wav"``).
                      格式扩展名（如 ``"mp3"``、``"wav"``）。

    Returns:
        The corresponding MIME type string.
        对应的 MIME 类型字符串。
    """
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
    """Complete-audio Edge TTS provider.

    完整音频 Edge TTS 提供商。

    Collects all audio chunks from ``edge_tts.Communicate.stream()`` and
    returns the concatenated result as a single ``bytes`` object.

    从 ``edge_tts.Communicate.stream()`` 收集所有音频块，
    并将拼接后的结果作为单个 ``bytes`` 对象返回。
    """

    def __init__(self, **config: Any) -> None:
        super().__init__(**config)
        self.voice = str(config.get("voice") or "zh-CN-XiaoxiaoNeural")
        self.rate = str(config.get("rate") or "+0%")
        self.pitch = str(config.get("pitch") or "+0Hz")
        self.volume = str(config.get("volume") or "+0%")
        self.output_format = str(config.get("format") or "mp3")
        self.media_type = _media_type_from_format(self.output_format)

    def health(self) -> TTSHealth:
        """Check whether the ``edge-tts`` package is installed and voice is set.

        检查 ``edge-tts`` 包是否已安装以及语音是否已配置。
        """
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
        """Synthesize text using the ``edge-tts`` package.

        使用 ``edge-tts`` 包合成文本。

        Args:
            text: The text to synthesize.
                  要合成的文本。
            voice_id: Optional voice name (e.g. ``"zh-CN-XiaoxiaoNeural"``).
                      可选的语音名称（如 ``"zh-CN-XiaoxiaoNeural"``）。
            **kwargs: Optional overrides for ``rate``, ``pitch``, ``volume``.
                      可选的 ``rate``、``pitch``、``volume`` 覆盖。

        Returns:
            MP3 (or configured format) audio bytes.
            MP3（或配置的格式）音频字节。
        """
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
        """Fetch all available Edge TTS voices from the service.

        从服务端获取所有可用的 Edge TTS 语音。

        Returns:
            A list of :class:`TTSVoice` with locale and gender metadata.
            包含语言和性别元数据的 :class:`TTSVoice` 列表。
        """
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
