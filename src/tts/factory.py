"""Decorator-based TTS provider registry.

基于装饰器的 TTS 提供商注册表。

Providers self-register via ``@TTSFactory.register("name", metadata=...)``
so that new providers can be added without modifying the factory itself.

提供商通过 ``@TTSFactory.register("name", metadata=...)`` 自注册，
新增提供商时无需修改工厂本身。

Reference: docs/TTS模块设计文档.md
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .interface import TTSInterface


@dataclass(frozen=True)
class TTSProviderMetadata:
    """Static metadata shown in provider list responses.

    提供商列表响应中展示的静态元数据。

    Attributes:
        name: Unique provider identifier (e.g. ``"edge_tts"``).
              唯一提供商标识符（如 ``"edge_tts"``）。
        display_name: Human-readable name for the UI.
                      用于 UI 的人类可读名称。
        provider_type: Either ``"cloud"`` or ``"local"``.
                       ``"cloud"`` 或 ``"local"``。
        supports_streaming: Whether the provider supports streaming synthesis.
                            提供商是否支持流式合成。
        media_type: Default audio MIME type (e.g. ``"audio/mpeg"``).
                    默认音频 MIME 类型（如 ``"audio/mpeg"``）。
        description: Short description of the provider.
                     提供商的简短描述。
    """

    name: str
    display_name: str
    provider_type: str
    supports_streaming: bool
    media_type: str
    description: str


class TTSFactory:
    """Class-scoped registry mapping provider name to provider class.

    类级注册表，将提供商名称映射到提供商类。

    All state is stored on the class itself so that every module importing
    ``TTSFactory`` shares the same registry.

    所有状态都存储在类本身上，因此每个导入 ``TTSFactory`` 的模块共享同一注册表。
    """

    _registry: dict[str, type[TTSInterface]] = {}
    _metadata: dict[str, TTSProviderMetadata] = {}

    @classmethod
    def register(
        cls,
        name: str,
        *,
        metadata: TTSProviderMetadata,
    ) -> Callable[[type[TTSInterface]], type[TTSInterface]]:
        """Return a decorator that registers a provider class.

        返回一个装饰器，用于注册提供商类。

        The decorator stamps ``provider_name``, ``supports_streaming``, and
        ``media_type`` onto the class and records it in the registry.

        装饰器会将 ``provider_name``、``supports_streaming`` 和 ``media_type``
        写入类属性，并将该类记录到注册表中。

        Args:
            name: Unique provider key used in config and API.
                  配置和 API 中使用的唯一提供商键。
            metadata: Static metadata for the provider list endpoint.
                      提供商列表端点的静态元数据。

        Returns:
            A class decorator.
            类装饰器。
        """

        def wrapper(provider_class: type[TTSInterface]) -> type[TTSInterface]:
            provider_class.provider_name = name
            provider_class.supports_streaming = metadata.supports_streaming
            provider_class.media_type = metadata.media_type
            cls._registry[name] = provider_class
            cls._metadata[name] = metadata
            return provider_class

        return wrapper

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> TTSInterface:
        """Instantiate a registered provider by name.

        根据名称实例化已注册的提供商。

        Args:
            name: Provider key (e.g. ``"edge_tts"``).
                  提供商键（如 ``"edge_tts"``）。
            **kwargs: Constructor arguments forwarded to the provider class.
                      传递给提供商构造函数的参数。

        Returns:
            An initialised :class:`TTSInterface` instance.
            已初始化的 :class:`TTSInterface` 实例。

        Raises:
            ValueError: If ``name`` is not in the registry.
                        如果 ``name`` 不在注册表中。
        """

        if name not in cls._registry:
            available = sorted(cls._registry.keys())
            raise ValueError(f"Unknown TTS provider: {name!r}. Available: {available}")
        return cls._registry[name](**kwargs)

    @classmethod
    def available(cls) -> list[str]:
        """Return sorted registered provider names.

        返回已注册提供商名称的排序列表。
        """

        return sorted(cls._registry.keys())

    @classmethod
    def metadata(cls, name: str) -> TTSProviderMetadata:
        """Return static metadata for a registered provider.

        返回已注册提供商的静态元数据。

        Args:
            name: Provider key.
                  提供商键。

        Returns:
            The :class:`TTSProviderMetadata` for the provider.
            该提供商的 :class:`TTSProviderMetadata`。

        Raises:
            ValueError: If ``name`` is not in the metadata registry.
                        如果 ``name`` 不在元数据注册表中。
        """

        if name not in cls._metadata:
            available = sorted(cls._metadata.keys())
            raise ValueError(f"Unknown TTS provider metadata: {name!r}. Available: {available}")
        return cls._metadata[name]
