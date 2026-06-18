"""ASR application service.

ASR 应用服务模块。

Orchestrates ASR configuration, provider health checks, provider
switching, and audio transcription.  Serves as the primary entry
point for API routes.

协调 ASR 配置、提供商健康检查、提供商切换和音频转录。作为 API 路由的主要入口点。

Reference: docs/ASR模块设计文档.md
"""

from __future__ import annotations

import asyncio
from typing import Any

from . import providers as _providers  # noqa: F401
from .config import ASRConfigStore
from .exceptions import ASRConfigError, ASRProviderUnavailableError
from .factory import ASRFactory
from .interface import ASRAudioUploadMetadata, ASRInterface

SENSITIVE_CONFIG_KEYS = {"api_key", "token", "secret", "password"}
SENSITIVE_CONFIG_MASK = "********"
# 后端私有根配置只允许 YAML 控制，避免前端配置 API 覆盖运行策略。
BACKEND_ONLY_ROOT_CONFIG_KEYS = {"persistent_provider", "preload_provider"}
PROVIDER_WRITE_ALLOWLISTS: dict[str, set[str]] = {
    "web_speech_api": {"language", "continuous", "interim_results", "max_alternatives"},
    "faster_whisper": {"language"},
    "sherpa_onnx_asr": {"num_threads", "use_itn", "provider", "debug"},
    "whisper_cpp": set(),
    "openai_whisper": set(),
}


class ASRService:
    """Coordinate ASR config, provider health, switching, and transcription.

    协调 ASR 配置、提供商健康检查、切换和转录。

    This is the top-level facade consumed by API route handlers.
    It delegates configuration persistence to ``ASRConfigStore`` and
    provider instantiation to ``ASRFactory``.

    这是 API 路由处理器使用的顶层门面。它将配置持久化委托给 ``ASRConfigStore``,
    将提供商实例化委托给 ``ASRFactory``。
    """

    def __init__(self, config_store: ASRConfigStore) -> None:
        self.config_store = config_store
        # 本地 ASR 模型加载成本较高，常驻模式下按 provider 名称复用实例。
        self._provider_cache: dict[str, ASRInterface] = {}
        # 多个请求复用同一个本地 recognizer 时串行转写，避免线程安全问题。
        self._provider_locks: dict[str, asyncio.Lock] = {}
        # 首次创建 provider 时加全局锁，防止并发请求重复加载模型。
        self._cache_lock = asyncio.Lock()

    def get_config(self) -> dict[str, Any]:
        """Return persisted OLV-shaped ASR config.

        返回持久化的 OLV 格式 ASR 配置。

        Sensitive values (API keys, tokens) are masked before being
        returned to the caller.

        敏感值（API 密钥、令牌）在返回给调用方之前会被掩码处理。
        """

        return self._public_config(self.config_store.read())

    def update_config(self, patch: dict[str, Any], *, persist: bool = True) -> dict[str, Any]:
        """Merge and persist a partial OLV-shaped ASR config update.

        合并并持久化部分 OLV 格式 ASR 配置更新。

        Masked sensitive values and read-only provider fields are
        stripped before the patch is applied.  If the patch changes
        ``asr_model``, the new provider is validated first.

        在应用补丁之前，会剥离掩码的敏感值和只读提供商字段。
        若补丁更改了 ``asr_model``，会先验证新提供商。
        """

        patch = self._strip_masked_sensitive_values(patch)
        # persistent/preload 只能由后端配置文件决定，前端 patch 会被忽略。
        patch = self._strip_backend_only_root_fields(patch)
        patch = self._strip_forbidden_provider_writes(patch)
        if not patch:
            return self.config_store.read()
        next_model = patch.get("asr_model")
        if next_model is not None:
            self._ensure_provider_registered(str(next_model))
        config = self.config_store.update(patch, persist=persist)
        # provider 参数变化后必须丢弃旧实例，否则会继续使用旧模型配置。
        self.clear_provider_cache()
        return config

    def switch_provider(self, provider: str, *, persist: bool = True) -> dict[str, Any]:
        """Switch the active ASR provider.

        切换当前活跃的 ASR 提供商。

        Raises ``ASRConfigError`` if *provider* is not registered.

        若 provider 未注册，则抛出 ``ASRConfigError``。
        """

        self._ensure_provider_registered(provider)
        config = self.config_store.update({"asr_model": provider}, persist=persist)
        # 切换 provider 后清空缓存，下一次请求按新 provider 重新创建实例。
        self.clear_provider_cache()
        return config

    def list_providers(self) -> list[dict[str, Any]]:
        """Return registered provider metadata plus health/config state.

        返回已注册提供商的元数据及其健康状态和配置信息。

        Each entry includes display name, type, description, capability
        flags, health status, active flag, and masked config.

        每个条目包含显示名称、类型、描述、能力标志、健康状态、活跃标志和掩码配置。
        """

        config = self.config_store.read()
        active_provider = self._active_provider(config)
        providers: list[dict[str, Any]] = []

        for name in ASRFactory.available():
            metadata = ASRFactory.metadata(name)
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
                    "supports_backend_transcription": metadata.supports_backend_transcription,
                    "supports_browser_streaming": metadata.supports_browser_streaming,
                    "config": self._public_config(provider_config),
                }
            )

        return providers

    def health(self) -> dict[str, Any]:
        """Return active and all-provider ASR health state.

        返回当前活跃提供商和所有提供商的 ASR 健康状态。

        The response includes the active provider name, whether it is
        available, and the full provider list with individual health
        information.

        响应包含活跃提供商名称、其是否可用，以及带有各提供商健康信息的完整列表。
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

    async def transcribe_audio(
        self,
        audio: bytes,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        upload_metadata: ASRAudioUploadMetadata | None = None,
        provider: str | None = None,
    ) -> dict[str, Any]:
        """Transcribe uploaded audio with the selected backend-capable provider.

        使用选定的后端转录提供商转录上传的音频。

        Validates that the chosen provider supports backend transcription
        and is healthy before delegating.  Returns a dict containing
        the provider name and transcribed text.

        在委托之前验证所选提供商支持后端转录且健康状态正常。
        返回包含提供商名称和转录文本的字典。
        """

        config = self.config_store.read()
        provider_name = provider or self._active_provider(config)
        self._ensure_provider_registered(provider_name)
        metadata = ASRFactory.metadata(provider_name)
        if not metadata.supports_backend_transcription:
            raise ASRProviderUnavailableError(
                f"ASR provider '{provider_name}' does not support backend transcription"
            )

        provider_config = self._provider_config(config, provider_name)
        if self._should_cache_provider(config, provider_name, metadata):
            # 本地后端 ASR 走常驻实例；单 provider 内部转写串行，减少并发风险。
            asr, provider_lock = await self._get_or_create_cached_provider(
                provider_name,
                provider_config,
            )
            async with provider_lock:
                text = await self._transcribe_with_provider(
                    asr,
                    audio,
                    provider_name=provider_name,
                    filename=filename,
                    content_type=content_type,
                    upload_metadata=upload_metadata,
                )
        else:
            asr = ASRFactory.create(provider_name, **provider_config)
            text = await self._transcribe_with_provider(
                asr,
                audio,
                provider_name=provider_name,
                filename=filename,
                content_type=content_type,
                upload_metadata=upload_metadata,
            )

        return {
            "provider": provider_name,
            "text": text,
        }

    async def preload_active_provider(self) -> None:
        """Preload the active persistent local ASR provider when enabled.

        仅在 preload_provider=true 且当前 provider 可后端转写时提前加载。
        """

        config = self.config_store.read()
        if not bool(config.get("preload_provider", False)):
            return

        provider_name = self._active_provider(config)
        metadata = ASRFactory.metadata(provider_name)
        if not self._should_cache_provider(config, provider_name, metadata):
            return

        provider_config = self._provider_config(config, provider_name)
        asr, provider_lock = await self._get_or_create_cached_provider(
            provider_name,
            provider_config,
        )
        async with provider_lock:
            await asr.async_preload()

    def clear_provider_cache(self) -> None:
        """Drop cached provider instances and locks.

        清理缓存后，本地 ASR 模型会在下一次请求或预加载时重新初始化。
        """

        self._provider_cache.clear()
        self._provider_locks.clear()

    async def _transcribe_with_provider(
        self,
        asr: ASRInterface,
        audio: bytes,
        *,
        provider_name: str,
        filename: str | None,
        content_type: str | None,
        upload_metadata: ASRAudioUploadMetadata | None,
    ) -> str:
        health = asr.health()
        if not health.available:
            raise ASRProviderUnavailableError(health.reason or f"{provider_name} is unavailable")
        return await asr.async_transcribe_audio(
            audio,
            filename=filename,
            content_type=content_type,
            upload_metadata=upload_metadata,
        )

    async def _get_or_create_cached_provider(
        self,
        provider_name: str,
        provider_config: dict[str, Any],
    ) -> tuple[ASRInterface, asyncio.Lock]:
        async with self._cache_lock:
            provider = self._provider_cache.get(provider_name)
            if provider is None:
                # 创建 provider 可能触发模型加载；必须只创建一次再放入缓存。
                provider = ASRFactory.create(provider_name, **provider_config)
                self._provider_cache[provider_name] = provider
                self._provider_locks[provider_name] = asyncio.Lock()
            return provider, self._provider_locks[provider_name]

    def _should_cache_provider(
        self,
        config: dict[str, Any],
        provider_name: str,
        metadata: Any,
    ) -> bool:
        # 只缓存本地、后端可转写的 provider；浏览器 ASR 和云 API 不应常驻。
        return (
            bool(config.get("persistent_provider", False))
            and metadata.provider_type == "local"
            and bool(metadata.supports_backend_transcription)
            and provider_name != "web_speech_api"
        )

    def _provider_health(self, name: str, provider_config: dict[str, Any]) -> dict[str, Any]:
        try:
            health = ASRFactory.create(name, **provider_config).health()
        except Exception as error:  # noqa: BLE001
            return {"available": False, "reason": str(error)}
        return {"available": health.available, "reason": health.reason}

    def _active_provider(self, config: dict[str, Any]) -> str:
        provider = str(config.get("asr_model") or "web_speech_api")
        self._ensure_provider_registered(provider)
        return provider

    def _provider_config(self, config: dict[str, Any], provider: str) -> dict[str, Any]:
        value = config.get(provider)
        if isinstance(value, dict):
            return dict(value)
        return {}

    def _ensure_provider_registered(self, provider: str) -> None:
        if provider not in ASRFactory.available():
            raise ASRConfigError(
                f"Unknown ASR provider: {provider!r}. Available: {ASRFactory.available()}"
            )

    def _public_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Return config safe for API responses."""

        safe: dict[str, Any] = {}
        for key, value in config.items():
            if key in BACKEND_ONLY_ROOT_CONFIG_KEYS:
                # 后端运行策略不暴露给前端，避免被配置页读写。
                continue
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

    def _strip_backend_only_root_fields(self, config: dict[str, Any]) -> dict[str, Any]:
        """Remove backend-owned root config fields from API patches."""

        return {
            key: value for key, value in config.items() if key not in BACKEND_ONLY_ROOT_CONFIG_KEYS
        }

    def _strip_forbidden_provider_writes(self, config: dict[str, Any]) -> dict[str, Any]:
        """Remove provider fields that are read-only from API updates."""

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
                    field: field_value for field, field_value in value.items() if field in allowed
                }

            if provider_config:
                cleaned[key] = provider_config
        return cleaned
