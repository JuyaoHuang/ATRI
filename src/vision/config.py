"""Visual configuration loading, validation, and persistence.

视觉配置加载、校验与持久化。
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from src.utils.yaml_text import patch_yaml_values

from .exceptions import VisionConfigError

_ATRI_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VISION_CONFIG_PATH = _ATRI_ROOT / "config" / "vision_config.yaml"

MAX_LONG_EDGE_LIMIT = 8192
MAX_DECODED_BYTES_LIMIT = 64 * 1024 * 1024
MAX_CAPTURE_TIMEOUT_MS = 60_000
MAX_WEBSOCKET_MESSAGE_BYTES = 128 * 1024 * 1024
MIN_WEBSOCKET_ENVELOPE_HEADROOM_BYTES = 64 * 1024

DEFAULT_VISION_CONFIG: dict[str, Any] = {
    "enabled": False,
    "source": "screen",
    "capture": {
        "media_type": "image/jpeg",
        "jpeg_quality": 0.82,
        "max_long_edge": 1920,
        "max_decoded_bytes": 4 * 1024 * 1024,
        "timeout_ms": 1500,
    },
    "provider": {"detail": "auto"},
    "transport": {"websocket_max_message_bytes": 8 * 1024 * 1024},
}

_ROOT_FIELDS = {"enabled", "source", "capture", "provider", "transport"}
_CAPTURE_FIELDS = {
    "media_type",
    "jpeg_quality",
    "max_long_edge",
    "max_decoded_bytes",
    "timeout_ms",
}
_PROVIDER_FIELDS = {"detail"}
_TRANSPORT_FIELDS = {"websocket_max_message_bytes"}


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise VisionConfigError(f"{path} must be a mapping")
    return dict(value)


def _reject_unknown_fields(value: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise VisionConfigError(f"Unsupported {path} fields: {', '.join(unknown)}")


def _strict_bool(value: Any, path: str) -> bool:
    if type(value) is not bool:
        raise VisionConfigError(f"{path} must be a boolean")
    return value


def _bounded_int(value: Any, path: str, *, maximum: int) -> int:
    if type(value) is not int or value <= 0 or value > maximum:
        raise VisionConfigError(f"{path} must be an integer between 1 and {maximum}")
    return value


def validate_vision_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize the complete visual configuration."""

    root = _mapping(config, "vision config")
    _reject_unknown_fields(root, _ROOT_FIELDS, "vision config")

    capture = _mapping(root.get("capture"), "vision.capture")
    provider = _mapping(root.get("provider"), "vision.provider")
    transport = _mapping(root.get("transport"), "vision.transport")
    _reject_unknown_fields(capture, _CAPTURE_FIELDS, "vision.capture")
    _reject_unknown_fields(provider, _PROVIDER_FIELDS, "vision.provider")
    _reject_unknown_fields(transport, _TRANSPORT_FIELDS, "vision.transport")

    source = root.get("source")
    if source != "screen":
        raise VisionConfigError("vision.source must be 'screen'")

    media_type = capture.get("media_type")
    if media_type != "image/jpeg":
        raise VisionConfigError("vision.capture.media_type must be 'image/jpeg'")

    quality_value = capture.get("jpeg_quality")
    if isinstance(quality_value, bool) or not isinstance(quality_value, int | float):
        raise VisionConfigError("vision.capture.jpeg_quality must be a number")
    jpeg_quality = float(quality_value)
    if not 0 < jpeg_quality <= 1:
        raise VisionConfigError("vision.capture.jpeg_quality must be greater than 0 and at most 1")

    max_long_edge = _bounded_int(
        capture.get("max_long_edge"),
        "vision.capture.max_long_edge",
        maximum=MAX_LONG_EDGE_LIMIT,
    )
    max_decoded_bytes = _bounded_int(
        capture.get("max_decoded_bytes"),
        "vision.capture.max_decoded_bytes",
        maximum=MAX_DECODED_BYTES_LIMIT,
    )
    timeout_ms = _bounded_int(
        capture.get("timeout_ms"),
        "vision.capture.timeout_ms",
        maximum=MAX_CAPTURE_TIMEOUT_MS,
    )

    detail = provider.get("detail")
    if detail not in {"auto", "low", "high"}:
        raise VisionConfigError("vision.provider.detail must be one of: auto, low, high")

    websocket_max_message_bytes = _bounded_int(
        transport.get("websocket_max_message_bytes"),
        "vision.transport.websocket_max_message_bytes",
        maximum=MAX_WEBSOCKET_MESSAGE_BYTES,
    )
    max_base64_length = 4 * ((max_decoded_bytes + 2) // 3)
    minimum_message_bytes = max_base64_length + MIN_WEBSOCKET_ENVELOPE_HEADROOM_BYTES
    if websocket_max_message_bytes < minimum_message_bytes:
        raise VisionConfigError(
            "vision.transport.websocket_max_message_bytes must include Base64 and envelope headroom"
        )

    return {
        "enabled": _strict_bool(root.get("enabled"), "vision.enabled"),
        "source": source,
        "capture": {
            "media_type": media_type,
            "jpeg_quality": jpeg_quality,
            "max_long_edge": max_long_edge,
            "max_decoded_bytes": max_decoded_bytes,
            "timeout_ms": timeout_ms,
        },
        "provider": {"detail": detail},
        "transport": {"websocket_max_message_bytes": websocket_max_message_bytes},
    }


class VisionConfigStore:
    """YAML-backed store for the validated visual configuration."""

    def __init__(
        self,
        initial_config: dict[str, Any] | None = None,
        *,
        path: Path | None = None,
    ) -> None:
        self.path = path or DEFAULT_VISION_CONFIG_PATH
        raw_config = self._read_raw_config()
        source_config = raw_config if raw_config is not None else {}
        merged = _deep_merge(DEFAULT_VISION_CONFIG, source_config)
        if initial_config:
            merged = _deep_merge(merged, initial_config)
        self._config = validate_vision_config(merged)

    def read(self) -> dict[str, Any]:
        """Return a defensive copy of the current configuration."""

        return deepcopy(self._config)

    def update_enabled(self, enabled: bool, *, persist: bool = True) -> dict[str, Any]:
        """Update only the persistent module availability switch."""

        _strict_bool(enabled, "vision.enabled")
        if persist:
            self._refresh_from_disk()
        updated = _deep_merge(self._config, {"enabled": enabled})
        self._config = validate_vision_config(updated)
        if persist:
            patch_yaml_values(self.path, {"enabled": enabled})
        return self.read()

    def _read_raw_config(self) -> dict[str, Any] | None:
        if not self.path.is_file():
            return None
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise VisionConfigError("Vision config file must contain a mapping")
        return raw

    def _refresh_from_disk(self) -> None:
        raw_config = self._read_raw_config()
        if raw_config is None:
            return
        self._config = validate_vision_config(_deep_merge(DEFAULT_VISION_CONFIG, raw_config))
