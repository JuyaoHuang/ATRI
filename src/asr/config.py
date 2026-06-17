"""ASR configuration loading and persistence.

ASR 配置加载与持久化模块。

Provides a YAML-backed configuration store with deep-merge semantics,
environment-variable placeholder handling, and sensitive-key protection.

提供基于 YAML 的配置存储，支持深度合并语义、环境变量占位符处理和敏感字段保护。

Reference: docs/ASR模块设计文档.md
"""

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
    "sherpa_onnx_asr": {
        "model_type": "sense_voice",
        "sense_voice": "models/asr-models/sherpa-onnx-sense-voice/model.int8.onnx",
        "tokens": "models/asr-models/sherpa-onnx-sense-voice/tokens.txt",
        "num_threads": 4,
        "use_itn": True,
        "provider": "cpu",
        "debug": False,
    },
    "whisper_cpp": {
        "model_name": "small",
        "print_realtime": False,  # 是否实时打印
        "print_progress": False,  # 是否打印进度
        "language": "auto",  # 语言，en、zh、auto
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
    """Recursively merge mapping values without mutating inputs.

    递归合并字典值，不修改原始输入。

    Nested dicts are merged key-by-key; all other values are deep-copied
    from *override*.  Neither *base* nor *override* is modified.

    嵌套字典按键逐一合并；其余值从 override 深拷贝。base 和 override 均不会被修改。
    """

    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


class ASRConfigStore:
    """Small YAML-backed configuration store for ASR settings.

    轻量级 YAML 配置存储，用于管理 ASR 设置。

    Reads the YAML file on construction, merges with built-in defaults,
    and supports incremental ``update`` / full ``replace`` with optional
    persistence.  Environment-variable placeholders (``${VAR}``) in
    sensitive keys are preserved on disk while resolved values stay in
    memory.

    构造时读取 YAML 文件，与内置默认值合并，支持增量 update / 全量 replace
    以及可选的持久化。敏感键中的环境变量占位符（``${VAR}``）在磁盘上保留，
    而解析后的值保留在内存中。
    """

    def __init__(
        self,
        initial_config: dict[str, Any] | None = None,
        *,
        path: Path | None = None,
    ) -> None:
        """Initialise the config store.

        初始化配置存储。

        Reads the YAML file at *path* (or the default location) and merges
        it with ``DEFAULT_ASR_CONFIG``.  If *initial_config* is provided it
        takes highest priority.

        读取 path 指定的 YAML 文件（或默认位置），与 DEFAULT_ASR_CONFIG 合并。
        若提供 initial_config，则其优先级最高。
        """
        self.path = path or DEFAULT_ASR_CONFIG_PATH
        raw_config = self._read_raw_config()
        source_config = raw_config if raw_config is not None else initial_config or {}
        self._persist_config = deepcopy(source_config)
        self._config = deep_merge(DEFAULT_ASR_CONFIG, source_config)
        if initial_config:
            self._config = deep_merge(self._config, initial_config)

    def read(self) -> dict[str, Any]:
        """Return a defensive copy of the current ASR config.

        返回当前 ASR 配置的防御性副本。
        """

        return deepcopy(self._config)

    def update(self, patch: dict[str, Any], *, persist: bool = True) -> dict[str, Any]:
        """Merge a partial config update and persist it by default.

        合并部分配置更新，默认持久化到磁盘。

        Refreshes from disk first (when *persist* is ``True``) to avoid
        overwriting concurrent edits, then deep-merges *patch* into both
        the runtime and persisted config layers.

        当 persist 为 True 时先从磁盘刷新以避免覆盖并发编辑，
        然后将 patch 深度合并到运行时和持久化配置层。
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
        """Replace the current config after applying defaults.

        应用默认值后替换当前配置。

        Unlike ``update``, this discards all existing keys and starts
        fresh from ``DEFAULT_ASR_CONFIG`` merged with *config*.

        与 update 不同，此方法丢弃所有现有键，以 DEFAULT_ASR_CONFIG
        与 config 合并后的结果作为全新配置。
        """

        self._config = deep_merge(DEFAULT_ASR_CONFIG, config)
        self._persist_config = deepcopy(config)
        if persist:
            self._save_patch(config)
        return self.read()

    def save(self) -> None:
        """Persist current values without reformatting the YAML document.

        持久化当前配置值，不重新格式化 YAML 文档。
        """

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
