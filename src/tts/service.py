"""TTS application service.

TTS 应用服务层。

Orchestrates configuration, provider health checks, voice listing,
provider switching, and text synthesis behind a single façade.

协调配置管理、提供商健康检查、语音列表、提供商切换和文本合成，
提供统一的门面接口。

Reference: docs/TTS模块设计文档.md
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from . import providers as _providers  # noqa: F401
from .config import TTSConfigStore
from .exceptions import TTSConfigError, TTSProviderUnavailableError, TTSSynthesisError
from .factory import TTSFactory
from .interface import TTSVoice

SENSITIVE_CONFIG_KEYS = {"api_key", "token", "secret", "password"}
SENSITIVE_CONFIG_MASK = "********"
"""Mask value used to hide sensitive fields in API responses.
用于在 API 响应中隐藏敏感字段的掩码值。
"""
PROVIDER_WRITE_ALLOWLISTS: dict[str, set[str]] = {
    "edge_tts": {"voice", "rate"},
    "gpt_sovits_tts": set(),
    "siliconflow_tts": {"default_voice", "stream"},
    "cosyvoice3_tts": {"stream", "speed"},
}
"""Per-provider set of config keys that the frontend is allowed to write.
Keys not in the allowlist are stripped before persisting.
每个提供商允许前端写入的配置键集合。不在白名单中的键会在持久化前被移除。
"""


class TTSService:
    """Coordinate TTS config, provider health, switching, voices, and synthesis.

    协调 TTS 配置、提供商健康检查、切换、语音列表和合成。

    This is the main entry point consumed by the FastAPI router layer.
    It delegates config persistence to :class:`TTSConfigStore` and provider
    instantiation to :class:`TTSFactory`.

    这是 FastAPI 路由层使用的主要入口。
    它将配置持久化委托给 :class:`TTSConfigStore`，
    将提供商实例化委托给 :class:`TTSFactory`。
    """

    def __init__(self, config_store: TTSConfigStore) -> None:
        self.config_store = config_store

    def get_config(self) -> dict[str, Any]:
        """Return persisted OLV-shaped TTS config.

        返回持久化的 OLV 格式 TTS 配置。

        Sensitive values (API keys, tokens) are masked with ``"********"``.
        敏感值（API 密钥、令牌）会被掩码为 ``"********"``。

        Returns:
            A dict safe for API responses.
            可安全用于 API 响应的字典。
        """

        return self._public_config(self.config_store.read())

    def update_config(self, patch: dict[str, Any], *, persist: bool = True) -> dict[str, Any]:
        """Merge and persist a partial OLV-shaped TTS config update.

        合并并持久化部分 OLV 格式 TTS 配置更新。

        Masked sensitive values and forbidden provider fields are stripped
        before merging.  If the patch changes ``tts_model``, the new provider
        is validated first.

        掩码的敏感值和禁止的提供商字段会在合并前被移除。
        如果补丁更改了 ``tts_model``，新提供商会被先验证。

        Args:
            patch: Partial config dict from the API request.
                   来自 API 请求的部分配置字典。
            persist: Whether to write to disk.
                     是否写入磁盘。

        Returns:
            The full config after merging (sensitive values masked).
            合并后的完整配置（敏感值已掩码）。

        Raises:
            TTSConfigError: If the target provider is not registered.
                            如果目标提供商未注册。
        """

        patch = self._strip_masked_sensitive_values(patch)
        patch = self._strip_forbidden_provider_writes(patch)
        next_model = patch.get("tts_model")
        if next_model is not None:
            self._ensure_provider_registered(str(next_model))
        return self.config_store.update(patch, persist=persist)

    def switch_provider(self, provider: str, *, persist: bool = True) -> dict[str, Any]:
        """Switch the active TTS provider.

        切换当前活跃的 TTS 提供商。

        Args:
            provider: Provider name (e.g. ``"edge_tts"``).
                      提供商名称（如 ``"edge_tts"``）。
            persist: Whether to write to disk.
                     是否写入磁盘。

        Returns:
            The full config after switching.
            切换后的完整配置。

        Raises:
            TTSConfigError: If the provider is not registered.
                            如果提供商未注册。
        """

        self._ensure_provider_registered(provider)
        return self.config_store.update({"tts_model": provider}, persist=persist)

    def list_providers(self) -> list[dict[str, Any]]:
        """Return registered provider metadata plus health/config state.

        返回已注册提供商的元数据及其健康状态和配置信息。

        Each entry contains: ``name``, ``display_name``, ``provider_type``,
        ``description``, ``active``, ``available``, ``reason``,
        ``supports_streaming``, ``media_type``, and ``config``.

        每个条目包含：``name``、``display_name``、``provider_type``、
        ``description``、``active``、``available``、``reason``、
        ``supports_streaming``、``media_type`` 和 ``config``。

        Returns:
            A list of provider info dicts.
            提供商信息字典列表。
        """

        config = self.config_store.read()
        active_provider = self._active_provider(config)
        providers: list[dict[str, Any]] = []

        for name in TTSFactory.available():
            metadata = TTSFactory.metadata(name)
            provider_config = self._provider_config(config, name)
            health = self._provider_health(name, provider_config)
            providers.append(
                {
                    "name": metadata.name,
                    "display_name": metadata.display_name,
                    "provider_type": metadata.provider_type,
                    "description": metadata.description,
                    "active": name == active_provider,
                    "available": health["available"],
                    "reason": health["reason"],
                    "supports_streaming": metadata.supports_streaming,
                    "media_type": self._provider_media_type(name, provider_config),
                    "config": self._public_config(provider_config),
                }
            )

        return providers

    def health(self) -> dict[str, Any]:
        """Return active and all-provider TTS health state.

        返回活跃提供商和所有提供商的 TTS 健康状态。

        Returns:
            A dict with ``active_provider``, ``active_available``,
            and ``providers`` keys.
            包含 ``active_provider``、``active_available`` 和 ``providers`` 键的字典。
        """

        config = self.config_store.read()
        active_provider = self._active_provider(config)
        providers = self.list_providers()
        active = next(
            (provider for provider in providers if provider["name"] == active_provider),
            None,
        )
        return {
            "active_provider": active_provider,
            "active_available": bool(active and active["available"]),
            "providers": providers,
        }

    async def get_voices(self, provider: str | None = None) -> dict[str, Any]:
        """Return voices for the active or requested TTS provider.

        返回活跃或指定 TTS 提供商的可用语音列表。

        Args:
            provider: Optional provider name; defaults to the active provider.
                      可选的提供商名称；默认为活跃提供商。

        Returns:
            A dict with ``provider`` name and ``voices`` list.
            包含 ``provider`` 名称和 ``voices`` 列表的字典。
        """

        config = self.config_store.read()
        provider_name = provider or self._active_provider(config)
        tts = self._create_provider(config, provider_name)
        voices = await tts.get_voices()
        return {
            "provider": provider_name,
            "voices": [self._voice_to_dict(voice) for voice in voices],
        }

    async def synthesize(
        self,
        text: str,
        *,
        provider: str | None = None,
        voice_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Synthesize text with the selected provider and return audio bytes.

        使用选定的提供商合成文本并返回音频字节。

        Logs timing and audio size on success; logs the traceback on failure.
        成功时记录耗时和音频大小；失败时记录完整堆栈。

        Args:
            text: The text to synthesize (must not be empty).
                  要合成的文本（不能为空）。
            provider: Optional provider name; defaults to the active provider.
                      可选的提供商名称；默认为活跃提供商。
            voice_id: Optional voice identifier.
                      可选的语音标识符。
            options: Extra keyword arguments forwarded to the provider.
                     传递给提供商的额外关键字参数。

        Returns:
            A dict with ``provider``, ``audio`` (bytes), and ``media_type``.
            包含 ``provider``、``audio``（字节）和 ``media_type`` 的字典。

        Raises:
            TTSSynthesisError: If ``text`` is empty.
                               如果 ``text`` 为空。
            TTSProviderUnavailableError: If the provider's health check fails.
                                         如果提供商的健康检查失败。
        """

        text = text.strip()
        if not text:
            raise TTSSynthesisError("TTS text must not be empty")

        config = self.config_store.read()
        provider_name = provider or self._active_provider(config)
        logger.info(
            "TTS synthesis started | provider={} | text_len={} | voice_id={}",
            provider_name,
            len(text),
            voice_id or "<default>",
        )

        started_at = time.perf_counter()
        tts = self._create_provider(config, provider_name)
        health = tts.health()
        if not health.available:
            logger.warning(
                "TTS provider unavailable during synthesis | provider={} | reason={}",
                provider_name,
                health.reason or "unknown",
            )
            raise TTSProviderUnavailableError(health.reason or f"{provider_name} is unavailable")

        try:
            audio = await tts.synthesize(text, voice_id=voice_id, **(options or {}))
        except Exception:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            logger.exception(
                "TTS synthesis failed | provider={} | text_len={} | voice_id={} | duration_ms={}",
                provider_name,
                len(text),
                voice_id or "<default>",
                duration_ms,
            )
            raise

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info(
            "TTS synthesis completed | provider={} | text_len={} | voice_id={} "
            "| duration_ms={} | audio_bytes={} | media_type={}",
            provider_name,
            len(text),
            voice_id or "<default>",
            duration_ms,
            len(audio),
            tts.media_type,
        )
        return {
            "provider": provider_name,
            "audio": audio,
            "media_type": tts.media_type,
        }

    def _create_provider(self, config: dict[str, Any], provider: str) -> Any:
        self._ensure_provider_registered(provider)
        provider_config = self._provider_config(config, provider)
        return TTSFactory.create(provider, **provider_config)

    def _provider_health(self, name: str, provider_config: dict[str, Any]) -> dict[str, Any]:
        try:
            health = TTSFactory.create(name, **provider_config).health()
        except Exception as error:  # noqa: BLE001
            return {"available": False, "reason": str(error)}
        return {"available": health.available, "reason": health.reason}

    def _provider_media_type(self, name: str, provider_config: dict[str, Any]) -> str:
        try:
            return TTSFactory.create(name, **provider_config).media_type
        except Exception:
            return TTSFactory.metadata(name).media_type

    def _active_provider(self, config: dict[str, Any]) -> str:
        provider = str(config.get("tts_model") or "edge_tts")
        self._ensure_provider_registered(provider)
        return provider

    def _provider_config(self, config: dict[str, Any], provider: str) -> dict[str, Any]:
        value = config.get(provider)
        if isinstance(value, dict):
            return dict(value)
        return {}

    def _ensure_provider_registered(self, provider: str) -> None:
        if provider not in TTSFactory.available():
            raise TTSConfigError(
                f"Unknown TTS provider: {provider!r}. Available: {TTSFactory.available()}"
            )

    def _public_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Return config safe for API responses."""

        safe: dict[str, Any] = {}
        for key, value in config.items():
            if key.lower() in SENSITIVE_CONFIG_KEYS:
                safe[key] = SENSITIVE_CONFIG_MASK if value else value
            elif isinstance(value, dict):
                safe[key] = self._public_config(value)
            else:
                safe[key] = value
        return safe

    def _strip_masked_sensitive_values(self, config: dict[str, Any]) -> dict[str, Any]:
        """Remove masked secrets from incoming API patches."""

        cleaned: dict[str, Any] = {}
        for key, value in config.items():
            if key.lower() in SENSITIVE_CONFIG_KEYS and value == SENSITIVE_CONFIG_MASK:
                continue
            if isinstance(value, dict):
                cleaned[key] = self._strip_masked_sensitive_values(value)
            else:
                cleaned[key] = value
        return cleaned

    def _strip_forbidden_provider_writes(self, config: dict[str, Any]) -> dict[str, Any]:
        """Remove provider fields that must remain backend-controlled."""

        cleaned: dict[str, Any] = {}
        for key, value in config.items():
            if not isinstance(value, dict):
                cleaned[key] = value
                continue

            allowed = PROVIDER_WRITE_ALLOWLISTS.get(key)
            if allowed is None:
                provider_config = dict(value)
            else:
                provider_config = {
                    field: field_value
                    for field, field_value in value.items()
                    if field in allowed
                }

            if provider_config:
                cleaned[key] = provider_config
        return cleaned

    def _voice_to_dict(self, voice: TTSVoice) -> dict[str, Any]:
        return {
            "id": voice.id,
            "name": voice.name,
            "language": voice.language,
            "gender": voice.gender,
            "description": voice.description,
            "preview_url": voice.preview_url,
        }
