"""VAD configuration loading and persistence."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from src.utils.yaml_text import patch_yaml_values

_ATRI_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VAD_CONFIG_PATH = _ATRI_ROOT / "config" / "vad_config.yaml"

DEFAULT_VAD_CONFIG: dict[str, Any] = {
    "enabled": False,
    "vad_model": "fake",
    "sample_rate": 16000,
    "required_hits": 2,
    "required_misses": 3,
    "fake": {
        "speech_threshold": 0.5,
    },
    "silero_vad": {
        "sample_rate": 16000,
        "prob_threshold": 0.5,
        "db_threshold": 60,
        "required_hits": 3,
        "required_misses": 24,
        "smoothing_window": 5,
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge mapping values without mutating inputs."""

    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


class VADConfigStore:
    """Small YAML-backed configuration store for VAD settings."""

    def __init__(
        self,
        initial_config: dict[str, Any] | None = None,
        *,
        path: Path | None = None,
    ) -> None:
        self.path = path or DEFAULT_VAD_CONFIG_PATH
        raw_config = self._read_raw_config()
        source_config = raw_config if raw_config is not None else initial_config or {}
        self._persist_config = deepcopy(source_config)
        self._config = deep_merge(DEFAULT_VAD_CONFIG, source_config)
        if initial_config:
            self._config = deep_merge(self._config, initial_config)

    def read(self) -> dict[str, Any]:
        """Return a defensive copy of the current VAD config."""

        return deepcopy(self._config)

    def update(self, patch: dict[str, Any], *, persist: bool = True) -> dict[str, Any]:
        """Merge a partial config update and persist it by default."""

        had_file = self.path.is_file()
        if persist:
            self._refresh_from_disk()
        self._config = deep_merge(self._config, patch)
        self._persist_config = deep_merge(self._persist_config, patch)
        if persist:
            self._save_patch(patch if had_file else self._persist_config)
        return self.read()

    def replace(self, config: dict[str, Any], *, persist: bool = True) -> dict[str, Any]:
        """Replace the current config after applying defaults."""

        self._config = deep_merge(DEFAULT_VAD_CONFIG, config)
        self._persist_config = deepcopy(config)
        if persist:
            self._save_patch(config)
        return self.read()

    def save(self) -> None:
        """Persist current explicit values without reformatting the YAML document."""

        self._save_patch(self._persist_config)

    def _save_patch(self, patch: dict[str, Any]) -> None:
        """Patch only provided YAML values, preserving comments and layout."""

        if not patch:
            return
        patch_yaml_values(self.path, patch)

    def _read_raw_config(self) -> dict[str, Any] | None:
        """Read the persisted VAD YAML."""

        if not self.path.is_file():
            return None
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        return raw if isinstance(raw, dict) else {}

    def _refresh_from_disk(self) -> None:
        """Merge the latest on-disk YAML before saving a runtime patch."""

        raw_config = self._read_raw_config()
        if raw_config is None:
            return

        self._persist_config = deepcopy(raw_config)
        self._config = deep_merge(DEFAULT_VAD_CONFIG, raw_config)
