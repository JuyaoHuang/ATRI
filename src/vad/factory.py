"""Decorator-based VAD provider registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .interface import VADInterface


@dataclass(frozen=True)
class VADProviderMetadata:
    """Static metadata shown in provider list responses."""

    name: str
    display_name: str
    provider_type: str
    requires_model: bool
    description: str


class VADFactory:
    """Class-scoped registry mapping provider names to provider classes."""

    _registry: dict[str, type[VADInterface]] = {}
    _metadata: dict[str, VADProviderMetadata] = {}

    @classmethod
    def register(
        cls,
        name: str,
        *,
        metadata: VADProviderMetadata,
    ) -> Callable[[type[VADInterface]], type[VADInterface]]:
        """Return a decorator that registers a VAD provider class."""

        def wrapper(provider_class: type[VADInterface]) -> type[VADInterface]:
            provider_class.provider_name = name
            provider_class.provider_type = metadata.provider_type
            provider_class.requires_model = metadata.requires_model
            cls._registry[name] = provider_class
            cls._metadata[name] = metadata
            return provider_class

        return wrapper

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> VADInterface:
        """Instantiate a registered VAD provider by name."""

        if name not in cls._registry:
            available = sorted(cls._registry.keys())
            raise ValueError(f"Unknown VAD provider: {name!r}. Available: {available}")
        return cls._registry[name](**kwargs)

    @classmethod
    def available(cls) -> list[str]:
        """Return sorted registered provider names."""

        return sorted(cls._registry.keys())

    @classmethod
    def metadata(cls, name: str) -> VADProviderMetadata:
        """Return static metadata for a registered provider."""

        if name not in cls._metadata:
            available = sorted(cls._metadata.keys())
            raise ValueError(f"Unknown VAD provider metadata: {name!r}. Available: {available}")
        return cls._metadata[name]
