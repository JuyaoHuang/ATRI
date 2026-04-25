"""ASR configuration loading and persistence."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from src.utils.yaml_text import patch_yaml_values

_ATRI_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ASR_CONFIG_PATH = _ATRI_ROOT / "config" / "asr_config.yaml"
SENSITIVE_CONFIG_KEYS = {"api_key", "token", "secret", "password"}

DEFAULT_ASR_CONFIG: dict[str, Any] = {
    "asr_model": "web_speech_api",
    "auto_send": {
        "enabled": False,
    },
    "web_speech_api": {
        "language": "zh-CN",
        "continuous": True,
        "interim_results": True,
        "max_alternatives": 1,
    },
    "faster_whisper": {
        "language": "auto",
    },
    "whisper_cpp": {
        "model_name": "small",
        "print_realtime": False, # 是否实时打印
        "print_progress": False,  # 是否打印进度
        "language": "auto", # 语言，en、zh、auto
    },
    "whisper": {
        "name": "medium",
    },
    "openai_whisper": {
        "model": "whisper-1",
        "language": "",
        "api_key": "${OPENAI_API_KEY}",
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


class ASRConfigStore:
    """Small YAML-backed configuration store for ASR settings."""

    def __init__(
        self,
        initial_config: dict[str, Any] | None = None,
        *,
        path: Path | None = None,
    ) -> None:
        self.path = path or DEFAULT_ASR_CONFIG_PATH
        raw_config = self._read_raw_config()
        source_config = raw_config if raw_config is not None else initial_config or {}
        self._persist_config = deepcopy(source_config)
        self._config = deep_merge(DEFAULT_ASR_CONFIG, source_config)
        if initial_config:
            self._config = deep_merge(self._config, initial_config)

    def read(self) -> dict[str, Any]:
        """Return a defensive copy of the current ASR config."""

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

        self._config = deep_merge(DEFAULT_ASR_CONFIG, config)
        self._persist_config = deepcopy(config)
        if persist:
            self._save_patch(config)
        return self.read()

    def save(self) -> None:
        """Persist current values without reformatting the YAML document."""

        self._save_patch(self._persist_config)

    def _save_patch(self, patch: dict[str, Any]) -> None:
        """Patch only provided YAML values, preserving comments and layout."""

        patch_yaml_values(self.path, self._config_for_save(patch, DEFAULT_ASR_CONFIG))

    def _read_raw_config(self) -> dict[str, Any] | None:
        """Read the persisted ASR YAML without environment substitution."""

        if not self.path.is_file():
            return None
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        return raw if isinstance(raw, dict) else {}

    def _refresh_from_disk(self) -> None:
        """Merge the latest on-disk YAML before saving a runtime patch."""

        raw_config = self._read_raw_config()
        if raw_config is None:
            return

        latest_persist_config = deepcopy(raw_config)
        latest_runtime_config = deep_merge(DEFAULT_ASR_CONFIG, raw_config)
        self._preserve_runtime_secrets(
            latest_runtime_config,
            latest_persist_config,
            self._config,
        )
        self._persist_config = latest_persist_config
        self._config = latest_runtime_config

    def _config_for_save(
        self,
        config: dict[str, Any],
        defaults: dict[str, Any],
    ) -> dict[str, Any]:
        """Return config safe to persist to disk."""

        safe = deepcopy(config)
        for key, value in safe.items():
            default_value = defaults.get(key)
            if isinstance(value, dict) and isinstance(default_value, dict):
                safe[key] = self._config_for_save(value, default_value)
            elif key.lower() in SENSITIVE_CONFIG_KEYS and self._is_env_placeholder(default_value):
                safe[key] = default_value
        return safe

    def _is_env_placeholder(self, value: Any) -> bool:
        return isinstance(value, str) and value.startswith("${") and value.endswith("}")

    def _preserve_runtime_secrets(
        self,
        runtime_config: dict[str, Any],
        persist_config: dict[str, Any],
        previous_runtime_config: dict[str, Any],
    ) -> None:
        """Keep resolved env secrets in memory while preserving placeholders on disk."""

        for key, value in list(persist_config.items()):
            previous_value = previous_runtime_config.get(key)
            if isinstance(value, dict) and isinstance(runtime_config.get(key), dict):
                previous_mapping = previous_value if isinstance(previous_value, dict) else {}
                self._preserve_runtime_secrets(
                    runtime_config[key],
                    value,
                    previous_mapping,
                )
            elif (
                key.lower() in SENSITIVE_CONFIG_KEYS
                and self._is_env_placeholder(value)
                and previous_value
                and not self._is_env_placeholder(previous_value)
            ):
                runtime_config[key] = previous_value
