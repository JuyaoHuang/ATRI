"""Silero VAD provider placeholder with lazy optional dependency checks."""

from __future__ import annotations

import importlib.util
from typing import Any

from src.vad.exceptions import VADProviderUnavailableError
from src.vad.factory import VADFactory, VADProviderMetadata
from src.vad.interface import VADHealth, VADInterface, VADResult


@VADFactory.register(
    "silero_vad",
    metadata=VADProviderMetadata(
        name="silero_vad",
        display_name="Silero VAD",
        provider_type="local",
        requires_model=True,
        description="Local Silero VAD provider reserved for realtime backend detection.",
    ),
)
class SileroVADProvider(VADInterface):
    """Silero VAD provider shell that avoids model loading at import time."""

    def __init__(self, **config: Any) -> None:
        super().__init__(**config)
        self.sample_rate = int(config.get("sample_rate", 16000))
        self.prob_threshold = float(config.get("prob_threshold", 0.5))
        self._model: Any | None = None

    def health(self) -> VADHealth:
        if importlib.util.find_spec("torch") is None:
            return VADHealth(False, "Python package 'torch' is not installed")
        if importlib.util.find_spec("silero_vad") is None:
            return VADHealth(False, "Python package 'silero-vad' is not installed")
        return VADHealth(True)

    def detect_speech(
        self,
        audio_chunk: Any,
        *,
        sample_rate: int,
    ) -> VADResult:
        """Detect speech with Silero VAD.

        Real inference is intentionally left for the provider completion milestone.
        M1 only defines the provider boundary and verifies lazy dependency handling.
        """

        health = self.health()
        if not health.available:
            raise VADProviderUnavailableError(health.reason or "silero_vad is unavailable")
        raise VADProviderUnavailableError(
            "silero_vad provider is registered but model inference is not implemented yet"
        )
