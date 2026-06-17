"""Browser Web Speech API provider marker.

浏览器 Web Speech API 提供商标记模块。

The implementation follows AIRI's split: Web Speech API runs in the browser
with live recognition, while the backend only exposes configuration and
provider status.

实现遵循 AIRI 的分离策略：Web Speech API 在浏览器中运行实时识别，
而后端仅暴露配置和提供商状态。

Reference: docs/ASR模块设计文档.md
"""

from __future__ import annotations

from typing import Any

from src.asr.exceptions import ASRProviderUnavailableError
from src.asr.factory import ASRFactory, ASRProviderMetadata
from src.asr.interface import ASRAudioUploadMetadata, ASRHealth, ASRInterface


@ASRFactory.register(
    "web_speech_api",
    metadata=ASRProviderMetadata(
        name="web_speech_api",
        display_name="Web Speech API",
        provider_type="browser",
        supports_backend_transcription=False,
        supports_browser_streaming=True,
        description="Browser-native Web Speech API provider; transcription runs in frontend.",
    ),
)
class WebSpeechAPIASR(ASRInterface):
    """Configuration-only provider for browser Web Speech API.

    浏览器 Web Speech API 的纯配置提供商。

    Transcription runs entirely in the browser via the native Web Speech
    API.  This backend class only stores configuration (language, mode,
    etc.) and reports health; it does **not** accept audio uploads.

    转录完全在浏览器中通过原生 Web Speech API 运行。此后端类仅存储配置
    （语言、模式等）并报告健康状态；**不**接受音频上传。
    """

    def __init__(self, **config: Any) -> None:
        super().__init__(**config)
        self.language = str(config.get("language") or "zh-CN")
        self.continuous = bool(config.get("continuous", True))
        self.interim_results = bool(config.get("interim_results", True))
        self.max_alternatives = int(config.get("max_alternatives", 1))

    def health(self) -> ASRHealth:
        return ASRHealth(True, "Browser availability is checked in the frontend")

    def transcribe_np(self, audio: Any) -> str:
        """Not supported — transcription runs in the browser.

        不支持 — 转录在浏览器中运行。

        Always raises ``ASRProviderUnavailableError``.

        始终抛出 ``ASRProviderUnavailableError``。
        """
        raise ASRProviderUnavailableError(
            "Web Speech API runs in the browser and does not support backend audio uploads"
        )

    async def async_transcribe_audio(
        self,
        audio: bytes,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        upload_metadata: ASRAudioUploadMetadata | None = None,
    ) -> str:
        """Not supported — transcription runs in the browser.

        不支持 — 转录在浏览器中运行。

        Always raises ``ASRProviderUnavailableError``.

        始终抛出 ``ASRProviderUnavailableError``。
        """
        raise ASRProviderUnavailableError(
            "Web Speech API runs in the browser and does not support backend audio uploads"
        )
