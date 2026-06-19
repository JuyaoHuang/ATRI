"""Silero VAD provider with OLV-style window smoothing and debounce."""

from __future__ import annotations

import importlib.util
import math
from collections import deque
from collections.abc import Sequence
from typing import Any

from loguru import logger

from src.vad.exceptions import VADProviderUnavailableError
from src.vad.factory import VADFactory, VADProviderMetadata
from src.vad.interface import VADHealth, VADInterface, VADResult

_INSTALL_COMMAND = "uv add silero-vad"
_INSTALL_HINT = (
    "Silero VAD requires optional dependencies. "
    f"Run `{_INSTALL_COMMAND}` before using provider 'silero_vad'."
)


@VADFactory.register(
    "silero_vad",
    metadata=VADProviderMetadata(
        name="silero_vad",
        display_name="Silero VAD",
        provider_type="local",
        requires_model=True,
        uses_internal_debounce=True,
        description="Local Silero VAD provider for realtime backend detection.",
    ),
)
class SileroVADProvider(VADInterface):
    """Run Silero VAD on 32 ms windows and expose debounced speech state."""

    SUPPORTED_SAMPLE_RATES = {8000, 16000}

    def __init__(self, **config: Any) -> None:
        super().__init__(**config)
        self.sample_rate = int(
            config.get("target_sr") or config.get("sample_rate") or config.get("orig_sr") or 16000
        )
        self.prob_threshold = float(config.get("prob_threshold", 0.4))
        self.db_threshold = float(config.get("db_threshold", 60))
        self.required_hits = max(1, int(config.get("required_hits", 3) or 3))
        self.required_misses = max(1, int(config.get("required_misses", 24) or 24))
        self.smoothing_window = max(1, int(config.get("smoothing_window", 5) or 5))

        self._model: Any | None = None
        self._active_sample_rate: int | None = None
        self._pending_samples: list[float] = []
        self._prob_window: deque[float] = deque(maxlen=self.smoothing_window)
        self._db_window: deque[float] = deque(maxlen=self.smoothing_window)
        self._is_active = False
        self._speech_hits = 0
        self._silence_misses = 0
        self._last_probability = 0.0
        self._last_db = 0.0

    def health(self) -> VADHealth:
        missing_packages = self._missing_optional_packages()
        if missing_packages:
            return VADHealth(
                False,
                f"{_INSTALL_HINT} Missing package(s): {', '.join(missing_packages)}.",
            )
        return VADHealth(True)

    def detect_speech(
        self,
        audio_chunk: Any,
        *,
        sample_rate: int,
    ) -> VADResult:
        """Detect debounced speech state for one realtime audio chunk."""

        health = self.health()
        if not health.available:
            raise VADProviderUnavailableError(health.reason or "silero_vad is unavailable")

        effective_sample_rate = self._resolve_sample_rate(sample_rate)
        if effective_sample_rate != self._active_sample_rate:
            self._active_sample_rate = effective_sample_rate
            self._reset_stream_state(reset_model=True)

        samples = self._to_float_list(audio_chunk)
        if samples:
            self._pending_samples.extend(samples)

        window_size = 512 if effective_sample_rate == 16000 else 256
        processed_windows = 0
        while len(self._pending_samples) >= window_size:
            window = self._pending_samples[:window_size]
            del self._pending_samples[:window_size]
            probability = self._infer_speech_probability(window, effective_sample_rate)
            db = self._calculate_db(window)
            smoothed_probability, smoothed_db = self._smooth(probability, db)
            self._last_probability = smoothed_probability
            self._last_db = smoothed_db
            self._update_debounce(
                smoothed_probability >= self.prob_threshold and smoothed_db >= self.db_threshold
            )
            processed_windows += 1

        return VADResult(
            is_speech=self._is_active,
            probability=self._last_probability,
            energy=self._last_db,
            metadata={
                "sample_rate": effective_sample_rate,
                "provider_state": "active" if self._is_active else "idle",
                "processed_windows": processed_windows,
                "pending_samples": len(self._pending_samples),
            },
        )

    def _resolve_sample_rate(self, sample_rate: int) -> int:
        value = int(sample_rate or self.sample_rate)
        if value not in self.SUPPORTED_SAMPLE_RATES:
            raise VADProviderUnavailableError(
                f"silero_vad only supports sample rates {sorted(self.SUPPORTED_SAMPLE_RATES)}"
            )
        return value

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model

        logger.info("Loading Silero VAD model")
        try:
            from silero_vad import load_silero_vad

            model = load_silero_vad()
            if hasattr(model, "to"):
                try:
                    model.to("cpu")
                except Exception as exc:  # noqa: BLE001
                    logger.debug(f"Silero VAD model CPU move skipped: {exc}")
            if hasattr(model, "eval"):
                model.eval()
        except Exception as exc:  # noqa: BLE001
            raise VADProviderUnavailableError(
                f"Failed to load Silero VAD model. {_INSTALL_HINT} Original error: {exc}"
            ) from exc

        self._model = model
        return model

    def _infer_speech_probability(self, window: list[float], sample_rate: int) -> float:
        try:
            import torch

            model = self._load_model()
            tensor = torch.tensor(window, dtype=torch.float32)
            with torch.no_grad():
                probability = model(tensor, sample_rate)
            return max(0.0, min(1.0, float(probability.item())))
        except VADProviderUnavailableError:
            raise
        except ModuleNotFoundError as exc:
            raise VADProviderUnavailableError(
                f"{_INSTALL_HINT} Missing module: {exc.name}."
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise VADProviderUnavailableError(f"Silero VAD inference failed: {exc}") from exc

    def _smooth(self, probability: float, db: float) -> tuple[float, float]:
        self._prob_window.append(probability)
        self._db_window.append(db)
        return (
            sum(self._prob_window) / len(self._prob_window),
            sum(self._db_window) / len(self._db_window),
        )

    def _update_debounce(self, is_hit: bool) -> None:
        if self._is_active:
            if is_hit:
                self._silence_misses = 0
                return
            self._silence_misses += 1
            if self._silence_misses >= self.required_misses:
                self._is_active = False
                self._silence_misses = 0
                self._speech_hits = 0
            return

        if is_hit:
            self._speech_hits += 1
            if self._speech_hits >= self.required_hits:
                self._is_active = True
                self._speech_hits = 0
                self._silence_misses = 0
        else:
            self._speech_hits = 0

    def _reset_stream_state(self, *, reset_model: bool = False) -> None:
        self._pending_samples.clear()
        self._prob_window.clear()
        self._db_window.clear()
        self._is_active = False
        self._speech_hits = 0
        self._silence_misses = 0
        self._last_probability = 0.0
        self._last_db = 0.0
        if reset_model and self._model is not None and hasattr(self._model, "reset_states"):
            try:
                self._model.reset_states()
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"Silero VAD model state reset skipped: {exc}")

    @staticmethod
    def _calculate_db(window: Sequence[float]) -> float:
        if not window:
            return 0.0
        squared_sum = sum((max(-1.0, min(1.0, float(sample))) * 32767) ** 2 for sample in window)
        rms = math.sqrt(squared_sum / len(window))
        if rms <= 0:
            return 0.0
        return 20 * math.log10(rms + 1e-7)

    @staticmethod
    def _to_float_list(audio_chunk: Any) -> list[float]:
        if audio_chunk is None:
            return []
        if isinstance(audio_chunk, Sequence) and not isinstance(audio_chunk, (str, bytes)):
            return [max(-1.0, min(1.0, float(sample))) for sample in audio_chunk]
        try:
            return [max(-1.0, min(1.0, float(sample))) for sample in audio_chunk]
        except TypeError:
            return [max(-1.0, min(1.0, float(audio_chunk)))]

    def _missing_optional_packages(self) -> list[str]:
        missing_packages: list[str] = []
        if importlib.util.find_spec("torch") is None:
            missing_packages.append("torch")
        if importlib.util.find_spec("silero_vad") is None:
            missing_packages.append("silero-vad")
        return missing_packages
