"""Sherpa-ONNX SenseVoice ASR provider.

This provider mirrors Open-LLM-VTuber's default ASR path for the
SenseVoice int8 ONNX model.  It is intentionally scoped to the
``sense_voice`` model type so the first backend VAD-to-ASR validation
uses a small, predictable CPU-friendly configuration.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

from src.asr.exceptions import ASRProviderUnavailableError, ASRTranscriptionError
from src.asr.factory import ASRFactory, ASRProviderMetadata
from src.asr.interface import ASRHealth, ASRInterface

_ATRI_ROOT = Path(__file__).resolve().parents[3]
_SUPPORTED_MODEL_TYPE = "sense_voice"
_SUPPORTED_PROVIDERS = {"cpu", "cuda"}
_ONNXRUNTIME_DLL_DIRECTORY_ADDED = False
_DLL_DIRECTORY_HANDLES: list[Any] = []


@ASRFactory.register(
    "sherpa_onnx_asr",
    metadata=ASRProviderMetadata(
        name="sherpa_onnx_asr",
        display_name="Sherpa-ONNX SenseVoice",
        provider_type="local",
        supports_backend_transcription=True,
        supports_browser_streaming=False,
        description="Local Sherpa-ONNX SenseVoice transcription compatible with OLV flow.",
    ),
)
class SherpaOnnxASR(ASRInterface):
    """Local Sherpa-ONNX provider for OLV's default SenseVoice model."""

    def __init__(self, **config: Any) -> None:
        super().__init__(**config)
        self.model_type = str(config.get("model_type") or _SUPPORTED_MODEL_TYPE)
        self.sense_voice = self._resolve_path(config.get("sense_voice"))
        self.tokens = self._resolve_path(config.get("tokens"))
        self.num_threads = int(config.get("num_threads") or 4)
        self.use_itn = bool(config.get("use_itn", True))
        self.provider = str(config.get("provider") or "cpu")
        self.debug = bool(config.get("debug", False))
        self.sample_rate = int(config.get("sample_rate") or self.SAMPLE_RATE)
        self._recognizer: Any | None = None

    def health(self) -> ASRHealth:
        if importlib.util.find_spec("sherpa_onnx") is None:
            return ASRHealth(False, "Python package 'sherpa_onnx' is not installed")
        if self.model_type != _SUPPORTED_MODEL_TYPE:
            return ASRHealth(
                False,
                "sherpa_onnx_asr currently supports only model_type='sense_voice'",
            )
        if self.provider not in _SUPPORTED_PROVIDERS:
            return ASRHealth(False, "sherpa_onnx_asr.provider must be 'cpu' or 'cuda'")
        if not self.sense_voice:
            return ASRHealth(False, "sherpa_onnx_asr.sense_voice is not configured")
        if not self.tokens:
            return ASRHealth(False, "sherpa_onnx_asr.tokens is not configured")
        if not self.sense_voice.is_file():
            return ASRHealth(False, f"SenseVoice model not found: {self.sense_voice}")
        if not self.tokens.is_file():
            return ASRHealth(False, f"SenseVoice tokens not found: {self.tokens}")
        if self.num_threads < 1:
            return ASRHealth(False, "sherpa_onnx_asr.num_threads must be >= 1")
        if self.sample_rate != self.SAMPLE_RATE:
            return ASRHealth(False, "sherpa_onnx_asr.sample_rate must be 16000")
        return ASRHealth(True)

    def transcribe_np(self, audio: Any) -> str:
        """Transcribe a 16 kHz mono float32 numpy audio array."""

        recognizer = self._get_recognizer()
        audio = self._ensure_float32_array(audio)
        try:
            stream = recognizer.create_stream()
            stream.accept_waveform(self.sample_rate, audio)
            recognizer.decode_streams([stream])
            return str(getattr(stream.result, "text", "") or "").strip()
        except Exception as error:  # noqa: BLE001
            raise ASRTranscriptionError("Sherpa-ONNX SenseVoice transcription failed") from error

    def _get_recognizer(self) -> Any:
        health = self.health()
        if not health.available:
            raise ASRProviderUnavailableError(health.reason or "sherpa_onnx_asr is unavailable")

        if self._recognizer is None:
            try:
                _add_onnxruntime_dll_directory()
                import sherpa_onnx

                self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                    model=str(self.sense_voice),
                    tokens=str(self.tokens),
                    num_threads=self.num_threads,
                    use_itn=self.use_itn,
                    debug=self.debug,
                    provider=self.provider,
                )
            except Exception as error:  # noqa: BLE001
                raise ASRProviderUnavailableError(
                    "Sherpa-ONNX SenseVoice recognizer initialization failed"
                ) from error
        return self._recognizer

    def _resolve_path(self, value: Any) -> Path | None:
        if not value:
            return None
        path = Path(str(value))
        if path.is_absolute():
            return path
        return _ATRI_ROOT / path


def _add_onnxruntime_dll_directory() -> None:
    """Prefer the venv onnxruntime DLL on Windows before importing sherpa_onnx."""

    global _ONNXRUNTIME_DLL_DIRECTORY_ADDED
    if _ONNXRUNTIME_DLL_DIRECTORY_ADDED or os.name != "nt":
        return

    _ONNXRUNTIME_DLL_DIRECTORY_ADDED = True
    spec = importlib.util.find_spec("onnxruntime")
    if not spec or not spec.submodule_search_locations:
        return

    package_dir = Path(next(iter(spec.submodule_search_locations)))
    capi_dir = package_dir / "capi"
    if capi_dir.is_dir():
        _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(capi_dir)))
