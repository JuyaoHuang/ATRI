"""ASR application service.

ASR 应用服务模块。

Orchestrates ASR configuration, provider health checks, provider
switching, and audio transcription.  Serves as the primary entry
point for API routes.

协调 ASR 配置、提供商健康检查、提供商切换和音频转录。作为 API 路由的主要入口点。

Reference: docs/ASR模块设计文档.md
"""

from __future__ import annotations

from typing import Any

from . import providers as _providers  # noqa: F401
from .config import ASRConfigStore
from .exceptions import ASRConfigError, ASRProviderUnavailableError
from .factory import ASRFactory

SENSITIVE_CONFIG_KEYS = {"api_key", "token", "secret", "password"}
SENSITIVE_CONFIG_MASK = "********"
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
        patch = self._strip_forbidden_provider_writes(patch)
        next_model = patch.get("asr_model")
        if next_model is not None:
            self._ensure_provider_registered(str(next_model))
        return self.config_store.update(patch, persist=persist)

    def switch_provider(self, provider: str, *, persist: bool = True) -> dict[str, Any]:
        """Switch the active ASR provider.

        切换当前活跃的 ASR 提供商。

        Raises ``ASRConfigError`` if *provider* is not registered.

        若 provider 未注册，则抛出 ``ASRConfigError``。
        """

        self._ensure_provider_registered(provider)
        return self.config_store.update({"asr_model": provider}, persist=persist)

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
        asr = ASRFactory.create(provider_name, **provider_config)
        health = asr.health()
        if not health.available:
            raise ASRProviderUnavailableError(health.reason or f"{provider_name} is unavailable")

        text = await asr.async_transcribe_audio(
            audio,
            filename=filename,
            content_type=content_type,
        )
        return {
            "provider": provider_name,
            "text": text,
        }

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
