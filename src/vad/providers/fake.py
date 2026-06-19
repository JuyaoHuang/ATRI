"""Fake VAD provider for deterministic tests and local development."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from src.vad.factory import VADFactory, VADProviderMetadata
from src.vad.interface import VADInterface, VADResult


@VADFactory.register(
    "fake",
    metadata=VADProviderMetadata(
        name="fake",
        display_name="Fake VAD",
        provider_type="test",
        requires_model=False,
        description="Threshold-based fake VAD provider for tests and development.",
    ),
)
class FakeVADProvider(VADInterface):
    """Simple threshold-based provider that does not require model dependencies."""

    def __init__(self, **config: Any) -> None:
        super().__init__(**config)
        self.speech_threshold = float(config.get("speech_threshold", 0.5))

    def detect_speech(
        self,
        audio_chunk: Any,
        *,
        sample_rate: int,
    ) -> VADResult:
        """Detect speech by max absolute sample amplitude."""

        samples = self._to_sequence(audio_chunk)
        if not samples:
            return VADResult(is_speech=False, probability=0.0, energy=0.0)

        energy = max(abs(float(sample)) for sample in samples)
        probability = min(1.0, energy / self.speech_threshold) if self.speech_threshold else 1.0
        return VADResult(
            is_speech=energy >= self.speech_threshold,
            probability=probability,
            energy=energy,
            metadata={"sample_rate": sample_rate},
        )

    def _to_sequence(self, audio_chunk: Any) -> Sequence[float]:
        if audio_chunk is None:
            return []
        if isinstance(audio_chunk, Sequence) and not isinstance(audio_chunk, (str, bytes)):
            return audio_chunk
        try:
            return list(audio_chunk)
        except TypeError:
            return [float(audio_chunk)]
