"""TTS configuration loading and persistence."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

_ATRI_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TTS_CONFIG_PATH = _ATRI_ROOT / "config" / "tts_config.yaml"
SENSITIVE_CONFIG_KEYS = {"api_key", "token", "secret", "password"}
DEFAULT_SILICONFLOW_MODEL = "FunAudioLLM/CosyVoice2-0.5B"
DEFAULT_SILICONFLOW_VOICE = f"{DEFAULT_SILICONFLOW_MODEL}:claire"

DEFAULT_TTS_CONFIG: dict[str, Any] = {
    "tts_model": "edge_tts",
    "enabled": False,
    "auto_play": False,
    "show_player_on_home": False,
    "volume": 1.0,
    "edge_tts": {
        "rate": "+0%",
    },
    "gpt_sovits_tts": {},
    "siliconflow_tts": {
        "default_voice": DEFAULT_SILICONFLOW_VOICE,
        "stream": False,
        "timeout_seconds": 120,
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge mappings without mutating inputs."""

    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


class TTSConfigStore:
    """Small YAML-backed configuration store for TTS settings."""

    def __init__(
        self,
        initial_config: dict[str, Any] | None = None,
        *,
        path: Path | None = None,
    ) -> None:
        self.path = path or DEFAULT_TTS_CONFIG_PATH
        raw_config = self._read_raw_config()
        source_config = raw_config if raw_config is not None else initial_config or {}
        self._persist_config = deepcopy(source_config)
        self._config = deep_merge(DEFAULT_TTS_CONFIG, source_config)
        if initial_config:
            self._config = deep_merge(self._config, initial_config)

    def read(self) -> dict[str, Any]:
        """Return a defensive copy of the current TTS config."""

        return deepcopy(self._config)

    def update(self, patch: dict[str, Any], *, persist: bool = True) -> dict[str, Any]:
        """Merge a partial config update and persist it by default."""

        if persist:
            self._refresh_from_disk()
        self._config = deep_merge(self._config, patch)
        self._persist_config = deep_merge(self._persist_config, patch)
        if persist:
            self.save()
        return self.read()

    def replace(self, config: dict[str, Any], *, persist: bool = True) -> dict[str, Any]:
        """Replace the current config after applying runtime defaults."""

        self._config = deep_merge(DEFAULT_TTS_CONFIG, config)
        self._persist_config = deepcopy(config)
        if persist:
            self.save()
        return self.read()

    def save(self) -> None:
        """Persist only explicit config values to YAML."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            yaml.safe_dump(
                self._config_for_save(self._persist_config),
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def _read_raw_config(self) -> dict[str, Any] | None:
        """Read the persisted TTS YAML without environment substitution."""

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
        latest_runtime_config = deep_merge(DEFAULT_TTS_CONFIG, raw_config)
        self._preserve_runtime_secrets(
            latest_runtime_config,
            latest_persist_config,
            self._config,
        )
        self._persist_config = latest_persist_config
        self._config = latest_runtime_config

    def _config_for_save(self, config: dict[str, Any]) -> dict[str, Any]:
        """Return config safe to persist to disk."""

        return deepcopy(config)

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
