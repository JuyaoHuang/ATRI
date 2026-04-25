"""Decorator-based TTS provider registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .interface import TTSInterface


@dataclass(frozen=True)
class TTSProviderMetadata:
    """Static metadata shown in provider list responses."""

    name: str
    display_name: str
    provider_type: str
    supports_streaming: bool
    media_type: str
    description: str


class TTSFactory:
    """Class-scoped registry mapping provider name to provider class."""

    _registry: dict[str, type[TTSInterface]] = {}
    _metadata: dict[str, TTSProviderMetadata] = {}

    @classmethod
    def register(
        cls,
        name: str,
        *,
        metadata: TTSProviderMetadata,
    ) -> Callable[[type[TTSInterface]], type[TTSInterface]]:
        """Return a decorator that registers a provider class."""

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
        """Instantiate a registered provider by name."""

        if name not in cls._registry:
            available = sorted(cls._registry.keys())
            raise ValueError(f"Unknown TTS provider: {name!r}. Available: {available}")
        return cls._registry[name](**kwargs)

    @classmethod
    def available(cls) -> list[str]:
        """Return sorted registered provider names."""

        return sorted(cls._registry.keys())

    @classmethod
    def metadata(cls, name: str) -> TTSProviderMetadata:
        """Return static metadata for a registered provider."""

        if name not in cls._metadata:
            available = sorted(cls._metadata.keys())
            raise ValueError(f"Unknown TTS provider metadata: {name!r}. Available: {available}")
        return cls._metadata[name]
