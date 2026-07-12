from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.utils.config_loader import load_config
from src.vad import (
    VADConfigError,
    VADConfigStore,
    VADEventType,
    VADFactory,
    VADService,
)


def test_vad_factory_registers_fake_and_silero_providers() -> None:
    assert {"fake", "silero_vad"} <= set(VADFactory.available())

    fake_metadata = VADFactory.metadata("fake")
    assert fake_metadata.requires_model is False

    silero_metadata = VADFactory.metadata("silero_vad")
    assert silero_metadata.requires_model is True


@pytest.mark.asyncio
async def test_vad_service_debounces_fake_provider_events(tmp_path: Path) -> None:
    service = VADService(
        VADConfigStore(
            {
                "enabled": True,
                "vad_model": "fake",
                "sample_rate": 16000,
                "fake": {
                    "speech_threshold": 0.5,
                    "required_hits": 2,
                    "required_misses": 2,
                },
            },
            path=tmp_path / "vad_config.yaml",
        )
    )

    events = [
        await service.process_audio("session-a", [0.0, 0.1]),
        await service.process_audio("session-a", [0.7]),
        await service.process_audio("session-a", [0.8]),
        await service.process_audio("session-a", [0.9]),
        await service.process_audio("session-a", [0.1]),
        await service.process_audio("session-a", [0.0]),
        await service.process_audio("session-a", [0.0]),
    ]

    assert [event.type for event in events] == [
        VADEventType.SILENCE,
        VADEventType.SILENCE,
        VADEventType.SPEECH_START,
        VADEventType.SPEECH_CHUNK,
        VADEventType.SPEECH_CHUNK,
        VADEventType.SPEECH_END,
        VADEventType.SILENCE,
    ]


@pytest.mark.asyncio
async def test_vad_service_disabled_returns_silence_without_provider_validation(
    tmp_path: Path,
) -> None:
    service = VADService(
        VADConfigStore(
            {
                "enabled": False,
                "vad_model": "fake",
            },
            path=tmp_path / "vad_config.yaml",
        )
    )

    event = await service.process_audio("session-a", [1.0])

    assert event.type == VADEventType.SILENCE
    assert event.metadata == {"disabled": True}


def test_vad_service_rejects_unknown_provider(tmp_path: Path) -> None:
    service = VADService(VADConfigStore(path=tmp_path / "vad_config.yaml"))

    with pytest.raises(VADConfigError):
        service.switch_provider("unknown", persist=False)


def test_vad_config_store_patches_values_without_backfilling_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "vad_config.yaml"
    store = VADConfigStore({"enabled": False, "vad_model": "fake"}, path=config_path)

    store.update({"enabled": True, "fake": {"required_hits": 3}})

    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert persisted == {
        "enabled": True,
        "vad_model": "fake",
        "fake": {"required_hits": 3},
    }


def test_root_config_loads_vad_sub_config() -> None:
    config = load_config("config.yaml")

    assert config["vad"]["enabled"] is True
    assert config["vad"]["vad_model"] == "silero_vad"
    assert config["vad"]["fake"]["required_misses"] == 10
