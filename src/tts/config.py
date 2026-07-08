"""TTS configuration loading and persistence.

TTS 配置加载与持久化模块。

Provides a YAML-backed config store with deep-merge semantics, environment
variable placeholder preservation, and safe secret handling.

提供基于 YAML 的配置存储，支持深度合并语义、环境变量占位符保留和安全的密钥处理。

Reference: docs/TTS模块设计文档.md
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from src.utils.yaml_text import patch_yaml_values

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
    "streaming": {
        "enabled": False,
        "segment_method": "pysbd",
        "faster_first_response": True,
        "max_concurrent_synthesis": 2,
        "max_pending_segments": 12,
    },
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
    """Recursively merge mappings without mutating inputs.

    递归合并两个字典，不修改原始输入。

    When both ``base`` and ``override`` contain a dict value for the same key,
    the sub-dicts are merged recursively; otherwise the override value wins.

    当 ``base`` 和 ``override`` 中同一键对应的值都是字典时，递归合并子字典；
    否则以 override 的值为准。

    Args:
        base: The base mapping.
              基础字典。
        override: The mapping whose values take precedence.
                  优先级更高的覆盖字典。

    Returns:
        A new merged dict. Returns a new merged dict (deep copy).
        合并后的新字典（深拷贝）。
    """

    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


class TTSConfigStore:
    """Small YAML-backed configuration store for TTS settings.

    小型 YAML 配置存储，用于管理 TTS 设置。

    Merges on-disk YAML with runtime defaults and optional initial overrides.
    Sensitive keys (api_key, token, etc.) are preserved across disk refreshes
    so that resolved environment-variable values are not lost.

    将磁盘上的 YAML 与运行时默认值和可选的初始覆盖值合并。
    敏感键（api_key、token 等）在磁盘刷新时会被保留，
    以确保已解析的环境变量值不会丢失。
    """

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
        """Return a defensive copy of the current TTS config.

        返回当前 TTS 配置的防御性拷贝。
        """

        return deepcopy(self._config)

    def update(self, patch: dict[str, Any], *, persist: bool = True) -> dict[str, Any]:
        """Merge a partial config update and persist it by default.

        合并部分配置更新，默认会持久化到磁盘。

        When ``persist`` is true the on-disk YAML is refreshed first to avoid
        overwriting concurrent external edits.

        当 ``persist`` 为 True 时，会先从磁盘刷新配置，以避免覆盖并发的外部修改。

        Args:
            patch: Partial config dict to merge in.
                   要合并的部分配置字典。
            persist: Whether to write changes to disk.
                     是否将变更写入磁盘。

        Returns:
            The full config after the merge.
            合并后的完整配置。
        """

        had_file = self.path.is_file()
        if persist:
            self._refresh_from_disk()
        self._config = deep_merge(self._config, patch)
        self._persist_config = deep_merge(self._persist_config, patch)
        if persist:
            self._save_patch(patch if had_file else self._persist_config)
        return self.read()

    def replace(self, config: dict[str, Any], *, persist: bool = True) -> dict[str, Any]:
        """Replace the current config after applying runtime defaults.

        替换当前配置，并重新应用运行时默认值。

        Unlike :meth:`update`, this discards the previous config entirely and
        applies ``DEFAULT_TTS_CONFIG`` as the base.

        与 :meth:`update` 不同，此方法会完全丢弃之前的配置，
        并以 ``DEFAULT_TTS_CONFIG`` 作为基础。

        Args:
            config: New config dict to set.
                    要设置的新配置字典。
            persist: Whether to write changes to disk.
                     是否将变更写入磁盘。

        Returns:
            The full config after replacement.
            替换后的完整配置。
        """

        self._config = deep_merge(DEFAULT_TTS_CONFIG, config)
        self._persist_config = deepcopy(config)
        if persist:
            self._save_patch(config)
        return self.read()

    def save(self) -> None:
        """Persist explicit config values without reformatting the YAML document.

        将显式配置值持久化到磁盘，不重新格式化 YAML 文档。
        """

        self._save_patch(self._persist_config)

    def _save_patch(self, patch: Mapping[str, Any]) -> None:
        """Patch only the provided YAML keys, preserving comments and layout."""

        if not patch:
            return

        patch_yaml_values(self.path, self._config_for_save(dict(patch)))

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
