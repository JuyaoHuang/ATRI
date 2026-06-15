"""Per-connection VAD state machine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .interface import VADEvent, VADEventType, VADInterface, VADState


@dataclass(frozen=True)
class VADSessionConfig:
    """Debounce and audio format settings for a VAD session."""

    sample_rate: int = 16000
    required_hits: int = 2
    required_misses: int = 3


class VADSession:
    """Debounce raw provider results into stable speech events."""

    def __init__(
        self,
        provider: VADInterface,
        *,
        config: VADSessionConfig | None = None,
    ) -> None:
        self.provider = provider
        self.config = config or VADSessionConfig()
        self.state = VADState.IDLE
        self._speech_hits = 0
        self._silence_misses = 0

    async def process_audio(self, audio_chunk: Any) -> VADEvent:
        """Process one audio chunk and return the debounced semantic event."""

        result = await self.provider.async_detect_speech(
            audio_chunk,
            sample_rate=self.config.sample_rate,
        )

        if result.is_speech:
            self._silence_misses = 0
            self._speech_hits += 1
            if self.state is VADState.IDLE and self._speech_hits >= self.config.required_hits:
                self.state = VADState.ACTIVE
                return VADEvent(
                    type=VADEventType.SPEECH_START,
                    state=self.state,
                    is_speech=True,
                    probability=result.probability,
                    energy=result.energy,
                    metadata=result.metadata,
                )
            if self.state is VADState.ACTIVE:
                return VADEvent(
                    type=VADEventType.SPEECH_CHUNK,
                    state=self.state,
                    is_speech=True,
                    probability=result.probability,
                    energy=result.energy,
                    metadata=result.metadata,
                )
            return VADEvent(
                type=VADEventType.SILENCE,
                state=self.state,
                is_speech=True,
                probability=result.probability,
                energy=result.energy,
                metadata=result.metadata,
            )

        self._speech_hits = 0
        if self.state is VADState.ACTIVE:
            self._silence_misses += 1
            if self._silence_misses >= self.config.required_misses:
                self.state = VADState.IDLE
                self._silence_misses = 0
                return VADEvent(
                    type=VADEventType.SPEECH_END,
                    state=self.state,
                    is_speech=False,
                    probability=result.probability,
                    energy=result.energy,
                    metadata=result.metadata,
                )
            return VADEvent(
                type=VADEventType.SPEECH_CHUNK,
                state=self.state,
                is_speech=False,
                probability=result.probability,
                energy=result.energy,
                metadata=result.metadata,
            )

        return VADEvent(
            type=VADEventType.SILENCE,
            state=self.state,
            is_speech=False,
            probability=result.probability,
            energy=result.energy,
            metadata=result.metadata,
        )

    def reset(self) -> None:
        """Reset session state to idle."""

        self.state = VADState.IDLE
        self._speech_hits = 0
        self._silence_misses = 0
