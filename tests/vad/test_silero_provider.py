from __future__ import annotations

import sys
from contextlib import nullcontext
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

from src.vad import VADConfigStore, VADEventType, VADService
from src.vad.exceptions import VADProviderUnavailableError
from src.vad.providers import silero_vad as silero_module
from src.vad.providers.silero_vad import SileroVADProvider


class FakeTensor:
    def __init__(self, value) -> None:  # noqa: ANN001
        self.value = value

    def item(self) -> float:
        return float(self.value)


class FakeTorchModule(ModuleType):
    float32 = "float32"

    def tensor(self, value, dtype=None):  # noqa: ANN001, ARG002
        return FakeTensor(value)

    def no_grad(self):  # noqa: ANN201
        return nullcontext()


class FakeSileroModel:
    def __init__(self, probabilities: list[float]) -> None:
        self.probabilities = list(probabilities)
        self.calls = 0

    def __call__(self, tensor, sample_rate: int):  # noqa: ANN001
        self.calls += 1
        probability = self.probabilities.pop(0) if self.probabilities else 0.0
        return FakeTensor(probability)

    def to(self, device: str) -> FakeSileroModel:
        return self

    def eval(self) -> FakeSileroModel:
        return self

    def reset_states(self) -> None:
        return None


def _install_fake_optional_deps(monkeypatch: pytest.MonkeyPatch) -> None:
    original_find_spec = silero_module.importlib.util.find_spec

    def fake_find_spec(name: str, *args, **kwargs):
        if name in {"torch", "silero_vad"}:
            return ModuleSpec(name, loader=None)
        return original_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(silero_module.importlib.util, "find_spec", fake_find_spec)
    monkeypatch.setitem(sys.modules, "torch", FakeTorchModule("torch"))


def test_silero_provider_debounces_on_internal_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_optional_deps(monkeypatch)
    model = FakeSileroModel([0.9, 0.9, 0.1, 0.1])
    provider = SileroVADProvider(
        prob_threshold=0.4,
        db_threshold=1,
        required_hits=2,
        required_misses=2,
        smoothing_window=1,
    )

    with patch.object(SileroVADProvider, "_load_model", return_value=model):
        events = [
            provider.detect_speech([0.9] * 512, sample_rate=16000),
            provider.detect_speech([0.9] * 512, sample_rate=16000),
            provider.detect_speech([0.0] * 512, sample_rate=16000),
            provider.detect_speech([0.0] * 512, sample_rate=16000),
        ]

    assert [event.is_speech for event in events] == [False, True, True, False]
    assert [event.metadata["processed_windows"] for event in events] == [1, 1, 1, 1]
    assert model.calls == 4


def test_silero_provider_carries_partial_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_optional_deps(monkeypatch)
    model = FakeSileroModel([0.9])
    provider = SileroVADProvider(
        prob_threshold=0.4,
        db_threshold=1,
        required_hits=1,
        smoothing_window=1,
    )

    with patch.object(SileroVADProvider, "_load_model", return_value=model):
        first = provider.detect_speech([0.9] * 300, sample_rate=16000)
        second = provider.detect_speech([0.9] * 212, sample_rate=16000)

    assert first.is_speech is False
    assert first.metadata["processed_windows"] == 0
    assert first.metadata["pending_samples"] == 300
    assert second.is_speech is True
    assert second.metadata["processed_windows"] == 1
    assert second.metadata["pending_samples"] == 0
    assert model.calls == 1


def test_silero_provider_missing_optional_dependency_reports_install_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_find_spec = silero_module.importlib.util.find_spec

    def fake_find_spec(name: str, *args, **kwargs):
        if name in {"torch", "silero_vad"}:
            return None
        return original_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(silero_module.importlib.util, "find_spec", fake_find_spec)
    provider = SileroVADProvider()

    health = provider.health()

    assert health.available is False
    assert "uv add silero-vad" in str(health.reason)
    with pytest.raises(VADProviderUnavailableError) as exc_info:
        provider.detect_speech([0.9] * 512, sample_rate=16000)
    assert "uv add silero-vad" in str(exc_info.value)


@pytest.mark.asyncio
async def test_vad_service_passes_through_silero_provider_debounce(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_optional_deps(monkeypatch)
    model = FakeSileroModel([0.9, 0.9])
    service = VADService(
        VADConfigStore(
            {
                "enabled": True,
                "vad_model": "silero_vad",
                "sample_rate": 16000,
                "silero_vad": {
                    "prob_threshold": 0.4,
                    "db_threshold": 1,
                    "required_hits": 2,
                    "required_misses": 2,
                    "smoothing_window": 1,
                },
            },
            path=tmp_path / "vad_config.yaml",
        )
    )

    with patch.object(SileroVADProvider, "_load_model", return_value=model):
        first = await service.process_audio("session-a", [0.9] * 512)
        second = await service.process_audio("session-a", [0.9] * 512)

    assert first.type == VADEventType.SILENCE
    assert second.type == VADEventType.SPEECH_START
