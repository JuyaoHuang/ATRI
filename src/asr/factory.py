"""Decorator-based ASR provider registry.

基于装饰器的 ASR 提供商注册表模块。

Provides a class-level registry that maps provider names to their
implementations, along with static metadata for each provider.

提供类级别的注册表，将提供商名称映射到其实现，以及每个提供商的静态元数据。

Reference: docs/ASR模块设计文档.md
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .interface import ASRInterface


@dataclass(frozen=True)
class ASRProviderMetadata:
    """Static metadata shown in provider list responses.

    在提供商列表响应中显示的静态元数据。

    Carries display information and capability flags for a single ASR
    provider.  Instances are frozen (immutable) after creation.

    携带单个 ASR 提供商的展示信息和能力标志。实例创建后为冻结（不可变）状态。
    """

    name: str
    display_name: str
    provider_type: str
    supports_backend_transcription: bool
    supports_browser_streaming: bool
    description: str


class ASRFactory:
    """Class-scoped registry mapping provider name to provider class.

    类级别的注册表，将提供商名称映射到提供商类。

    Provider classes register themselves via the ``@ASRFactory.register``
    decorator.  The factory can then instantiate providers by name and
    query available providers and their metadata.

    提供商类通过 ``@ASRFactory.register`` 装饰器自行注册。工厂随后可按名称
    实例化提供商，并查询可用提供商及其元数据。
    """

    _registry: dict[str, type[ASRInterface]] = {}
    _metadata: dict[str, ASRProviderMetadata] = {}

    @classmethod
    def register(
        cls,
        name: str,
        *,
        metadata: ASRProviderMetadata,
    ) -> Callable[[type[ASRInterface]], type[ASRInterface]]:
        """Return a decorator that registers a provider class.

        返回一个装饰器，用于注册提供商类。

        The decorated class is stored in the internal registry under
        *name* and its ``provider_name`` / capability flags are set
        from *metadata*.

        被装饰的类以 name 为键存入内部注册表，其 ``provider_name`` 和能力标志
        从 metadata 中设置。
        """

        def wrapper(provider_class: type[ASRInterface]) -> type[ASRInterface]:
            provider_class.provider_name = name
            provider_class.supports_backend_transcription = metadata.supports_backend_transcription
            provider_class.supports_browser_streaming = metadata.supports_browser_streaming
            cls._registry[name] = provider_class
            cls._metadata[name] = metadata
            return provider_class

        return wrapper

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> ASRInterface:
        """Instantiate a registered provider by name.

        按名称实例化已注册的提供商。

        Raises ``ValueError`` if *name* is not found in the registry.

        若 name 不在注册表中，则抛出 ``ValueError``。
        """

        if name not in cls._registry:
            available = sorted(cls._registry.keys())
            raise ValueError(f"Unknown ASR provider: {name!r}. Available: {available}")
        return cls._registry[name](**kwargs)

    @classmethod
    def available(cls) -> list[str]:
        """Return sorted registered provider names.

        返回已注册提供商名称的排序列表。
        """

        return sorted(cls._registry.keys())

    @classmethod
    def metadata(cls, name: str) -> ASRProviderMetadata:
        """Return static metadata for a registered provider.

        返回已注册提供商的静态元数据。

        Raises ``ValueError`` if *name* is not found in the metadata
        registry.

        若 name 不在元数据注册表中，则抛出 ``ValueError``。
        """

        if name not in cls._metadata:
            available = sorted(cls._metadata.keys())
            raise ValueError(f"Unknown ASR provider metadata: {name!r}. Available: {available}")
        return cls._metadata[name]
