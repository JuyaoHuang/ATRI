"""VAD provider interface and event data structures."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class VADEventType(StrEnum):
    """Stable semantic events emitted by the VAD session state machine."""

    SPEECH_START = "speech_start"
    SPEECH_CHUNK = "speech_chunk"
    SPEECH_END = "speech_end"
    SILENCE = "silence"
    ERROR = "error"


class VADState(StrEnum):
    """Internal session state."""

    IDLE = "idle"
    ACTIVE = "active"


@dataclass(frozen=True)
class VADHealth:
    """Provider availability state."""

    available: bool
    reason: str | None = None


@dataclass(frozen=True)
class VADResult:
    """Raw provider detection result for a single audio chunk."""

    is_speech: bool
    probability: float | None = None
    energy: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VADEvent:
    """Debounced VAD event returned to callers."""

    type: VADEventType
    state: VADState
    is_speech: bool
    probability: float | None = None
    energy: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class VADInterface(ABC):
    """Base interface for all VAD providers."""

    provider_name = "unknown"
    provider_type = "unknown"
    requires_model = False

    def __init__(self, **config: Any) -> None:
        self.config = dict(config)

    async def async_detect_speech(
        self,
        audio_chunk: Any,
        *,
        sample_rate: int,
    ) -> VADResult:
        """Detect speech in an audio chunk asynchronously."""

        return await asyncio.to_thread(
            self.detect_speech,
            audio_chunk,
            sample_rate=sample_rate,
        )

    @abstractmethod
    def detect_speech(
        self,
        audio_chunk: Any,
        *,
        sample_rate: int,
    ) -> VADResult:
        """Detect speech in a single audio chunk."""

    def health(self) -> VADHealth:
        """Return provider availability without loading heavyweight models."""

        return VADHealth(available=True)
