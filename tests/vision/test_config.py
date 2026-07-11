"""Tests for visual configuration validation and persistence."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from src.utils.config_loader import load_config
from src.vision import DEFAULT_VISION_CONFIG, VisionConfigError, VisionConfigStore, VisionService


def _config_with(path: tuple[str, ...], value: object) -> dict[str, object]:
    config = deepcopy(DEFAULT_VISION_CONFIG)
    target = config
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    return config


def test_default_config_is_complete_and_defensive(tmp_path: Path) -> None:
    store = VisionConfigStore(path=tmp_path / "missing.yaml")

    first = store.read()
    first["capture"]["timeout_ms"] = 1

    assert store.read() == DEFAULT_VISION_CONFIG


def test_root_config_loads_vision_without_double_nesting() -> None:
    config = load_config("config.yaml")

    assert config["vision"]["enabled"] is False
    assert config["vision"]["source"] == "screen"
    assert "vision" not in config["vision"]


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("enabled",), 1),
        (("source",), "camera"),
        (("capture", "media_type"), "image/png"),
        (("capture", "jpeg_quality"), 0),
        (("capture", "jpeg_quality"), 1.1),
        (("capture", "max_long_edge"), 0),
        (("capture", "max_decoded_bytes"), -1),
        (("capture", "timeout_ms"), 0),
        (("provider", "detail"), "original"),
        (("transport", "websocket_max_message_bytes"), 1),
    ],
)
def test_invalid_config_is_rejected(path: tuple[str, ...], value: object, tmp_path: Path) -> None:
    with pytest.raises(VisionConfigError):
        VisionConfigStore(_config_with(path, value), path=tmp_path / "missing.yaml")


def test_unknown_config_field_is_rejected(tmp_path: Path) -> None:
    config = deepcopy(DEFAULT_VISION_CONFIG)
    config["unexpected"] = True

    with pytest.raises(VisionConfigError, match="unexpected"):
        VisionConfigStore(config, path=tmp_path / "missing.yaml")


def test_update_enabled_preserves_yaml_layout_and_external_values(tmp_path: Path) -> None:
    path = tmp_path / "vision_config.yaml"
    path.write_text(
        "\n".join(
            [
                "# keep visual config header",
                "enabled: false # writable",
                "source: screen",
                "capture:",
                "  media_type: image/jpeg",
                "  jpeg_quality: 0.82",
                "  max_long_edge: 1600",
                "  max_decoded_bytes: 4194304",
                "  timeout_ms: 1500",
                "provider:",
                "  detail: auto",
                "transport:",
                "  websocket_max_message_bytes: 8388608",
                "",
            ]
        ),
        encoding="utf-8",
    )
    store = VisionConfigStore(path=path)

    store.update_enabled(True)

    text = path.read_text(encoding="utf-8")
    assert "# keep visual config header" in text
    assert "enabled: true # writable" in text
    assert "  max_long_edge: 1600" in text
    assert store.read()["capture"]["max_long_edge"] == 1600


@pytest.mark.asyncio
async def test_service_allows_only_boolean_enabled(tmp_path: Path) -> None:
    service = VisionService(VisionConfigStore(path=tmp_path / "vision.yaml"))

    updated = await service.update_config({"enabled": True}, persist=False)
    assert updated["enabled"] is True

    with pytest.raises(VisionConfigError, match="Unsupported"):
        await service.update_config({"source": "screen"}, persist=False)
    with pytest.raises(VisionConfigError, match="exactly"):
        await service.update_config({}, persist=False)
    with pytest.raises(VisionConfigError, match="boolean"):
        await service.update_config({"enabled": 1}, persist=False)


@pytest.mark.asyncio
async def test_service_persists_only_enabled_field(tmp_path: Path) -> None:
    path = tmp_path / "vision.yaml"
    service = VisionService(VisionConfigStore(path=path))

    await service.update_config({"enabled": True})

    assert yaml.safe_load(path.read_text(encoding="utf-8")) == {"enabled": True}
