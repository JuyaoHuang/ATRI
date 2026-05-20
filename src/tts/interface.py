"""TTS provider interface.

TTS 提供商接口定义。

Defines the abstract base class and data structures that every TTS provider
must implement.

定义了每个 TTS 提供商必须实现的抽象基类和数据结构。

Reference: docs/TTS模块设计文档.md
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TTSHealth:
    """Provider availability state.

    提供商可用性状态。

    Attributes:
        available: Whether the provider is ready to accept requests.
                   提供商是否准备好接受请求。
        reason: Optional human-readable explanation when unavailable.
                不可用时的可选人类可读说明。
    """

    available: bool
    reason: str | None = None


@dataclass(frozen=True)
class TTSVoice:
    """Voice metadata shown by the settings UI.

    设置界面中展示的语音元数据。

    Attributes:
        id: Unique voice identifier passed to ``synthesize(voice_id=...)``.
            唯一语音标识符，传递给 ``synthesize(voice_id=...)``。
        name: Human-readable display name.
              人类可读的显示名称。
        language: BCP-47 locale tag (e.g. ``"zh-CN"``).
                  BCP-47 语言标签（如 ``"zh-CN"``）。
        gender: ``"Male"`` or ``"Female"`` when known.
                已知时为 ``"Male"`` 或 ``"Female"``。
        description: Short description of the voice.
                     语音的简短描述。
        preview_url: URL to a short audio preview sample.
                     短音频预览样本的 URL。
    """

    id: str
    name: str
    language: str | None = None
    gender: str | None = None
    description: str | None = None
    preview_url: str | None = None


class TTSInterface(ABC):
    """Base interface for all TTS providers.

    所有 TTS 提供商的基类接口。

    Concrete providers subclass this, implement :meth:`synthesize` and
    :meth:`get_voices`, and register themselves via ``@TTSFactory.register``.

    具体提供商继承此类，实现 :meth:`synthesize` 和 :meth:`get_voices`，
    并通过 ``@TTSFactory.register`` 注册自身。
    """

    provider_name = "unknown"
    supports_streaming = False
    media_type = "audio/mpeg"

    def __init__(self, **config: Any) -> None:
        self.config = dict(config)

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        **kwargs: Any,
    ) -> bytes:
        """Synthesize text and return complete audio bytes.

        合成文本并返回完整的音频字节数据。

        Args:
            text: The text to speak.
                  要合成的文本。
            voice_id: Optional voice identifier override.
                      可选的语音标识符覆盖。
            **kwargs: Provider-specific options.
                      提供商特定的选项。

        Returns:
            Raw audio bytes in the provider's ``media_type`` format.
            以提供商 ``media_type`` 格式编码的原始音频字节。
        """

    async def synthesize_stream(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[bytes]:
        """Reserved stream interface for future TTS optimization.

        为未来 TTS 优化预留的流式接口。

        Default implementation raises :class:`NotImplementedError`.
        Providers that support streaming should override this method.

        默认实现抛出 :class:`NotImplementedError`。
        支持流式的提供商应重写此方法。

        Args:
            text: The text to speak.
                  要合成的文本。
            voice_id: Optional voice identifier override.
                      可选的语音标识符覆盖。
            **kwargs: Provider-specific options.
                      提供商特定的选项。

        Yields:
            Audio chunks as they become available.
            逐块返回可用的音频数据。
        """

        raise NotImplementedError("Streaming TTS synthesis is not implemented")

    @abstractmethod
    async def get_voices(self) -> list[TTSVoice]:
        """Return available voices for this provider.

        返回此提供商可用的语音列表。

        Returns:
            A list of :class:`TTSVoice` objects.
            :class:`TTSVoice` 对象列表。
        """

    def health(self) -> TTSHealth:
        """Return provider availability without doing expensive work.

        返回提供商可用性状态，不做耗时操作。

        Subclasses should override this to check prerequisites such as
        package installation or API key configuration.

        子类应重写此方法以检查前置条件，如包安装或 API 密钥配置。

        Returns:
            A :class:`TTSHealth` indicating readiness.
            表示就绪状态的 :class:`TTSHealth`。
        """

        return TTSHealth(available=True)
