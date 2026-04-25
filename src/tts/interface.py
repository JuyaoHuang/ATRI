"""TTS provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TTSHealth:
    """Provider availability state."""

    available: bool
    reason: str | None = None


@dataclass(frozen=True)
class TTSVoice:
    """Voice metadata shown by the settings UI."""

    id: str
    name: str
    language: str | None = None
    gender: str | None = None
    description: str | None = None
    preview_url: str | None = None


class TTSInterface(ABC):
    """Base interface for all TTS providers."""

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
        """Synthesize text and return complete audio bytes."""

    async def synthesize_stream(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[bytes]:
        """Reserved stream interface for future TTS optimization."""

        raise NotImplementedError("Streaming TTS synthesis is not implemented")

    @abstractmethod
    async def get_voices(self) -> list[TTSVoice]:
        """Return available voices for this provider."""

    def health(self) -> TTSHealth:
        """Return provider availability without doing expensive work."""

        return TTSHealth(available=True)
