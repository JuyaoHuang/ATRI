"""VAD application service."""

from __future__ import annotations

from typing import Any

from . import providers as _providers  # noqa: F401
from .config import VADConfigStore
from .exceptions import VADConfigError, VADProviderUnavailableError
from .factory import VADFactory
from .interface import VADEvent, VADEventType, VADState
from .session import VADSession, VADSessionConfig


class VADService:
    """Coordinate VAD configuration, provider selection, and sessions."""

    def __init__(self, config_store: VADConfigStore) -> None:
        self.config_store = config_store
        self._sessions: dict[str, VADSession] = {}

    def get_config(self) -> dict[str, Any]:
        """Return current VAD config."""

        return self.config_store.read()

    def update_config(self, patch: dict[str, Any], *, persist: bool = True) -> dict[str, Any]:
        """Merge and persist a partial VAD config update."""

        next_provider = patch.get("vad_model")
        if next_provider is not None:
            self._ensure_provider_registered(str(next_provider))
        config = self.config_store.update(patch, persist=persist)
        self._sessions.clear()
        return config

    def switch_provider(self, provider: str, *, persist: bool = True) -> dict[str, Any]:
        """Switch the active VAD provider."""

        self._ensure_provider_registered(provider)
        config = self.config_store.update({"vad_model": provider}, persist=persist)
        self._sessions.clear()
        return config

    def list_providers(self) -> list[dict[str, Any]]:
        """Return registered provider metadata plus health/config state."""

        config = self.config_store.read()
        active_provider = self._active_provider(config)
        providers: list[dict[str, Any]] = []
        for name in VADFactory.available():
            metadata = VADFactory.metadata(name)
            provider_config = self._provider_config(config, name)
            health = self._provider_health(name, provider_config)
            providers.append(
                {
                    "name": metadata.name,
                    "display_name": metadata.display_name,
                    "provider_type": metadata.provider_type,
                    "description": metadata.description,
                    "requires_model": metadata.requires_model,
                    "active": name == active_provider,
                    "available": health["available"],
                    "reason": health["reason"],
                    "config": provider_config,
                }
            )
        return providers

    def health(self) -> dict[str, Any]:
        """Return active and all-provider VAD health state."""

        config = self.config_store.read()
        enabled = bool(config.get("enabled", False))
        active_provider = self._active_provider(config)
        providers = self.list_providers()
        active = next(
            (provider for provider in providers if provider["name"] == active_provider),
            None,
        )
        return {
            "enabled": enabled,
            "active_provider": active_provider,
            "active_available": bool(enabled and active and active["available"]),
            "providers": providers,
        }

    async def process_audio(self, session_id: str, audio_chunk: Any) -> VADEvent:
        """Process a chunk through the session for the active provider."""

        config = self.config_store.read()
        if not bool(config.get("enabled", False)):
            return VADEvent(
                type=VADEventType.SILENCE,
                state=VADState.IDLE,
                is_speech=False,
                metadata={"disabled": True},
            )

        session = self._get_or_create_session(session_id, config)
        return await session.process_audio(audio_chunk)

    def reset_session(self, session_id: str) -> None:
        """Drop one VAD session."""

        self._sessions.pop(session_id, None)

    def clear_sessions(self) -> None:
        """Drop all VAD sessions."""

        self._sessions.clear()

    def _get_or_create_session(self, session_id: str, config: dict[str, Any]) -> VADSession:
        cached = self._sessions.get(session_id)
        if cached is not None:
            return cached

        provider_name = self._active_provider(config)
        provider_config = self._provider_config(config, provider_name)
        provider = VADFactory.create(provider_name, **provider_config)
        health = provider.health()
        if not health.available:
            raise VADProviderUnavailableError(
                health.reason or f"VAD provider '{provider_name}' is unavailable"
            )

        session = VADSession(
            provider,
            config=VADSessionConfig(
                sample_rate=int(config.get("sample_rate") or 16000),
                required_hits=max(1, int(config.get("required_hits") or 1)),
                required_misses=max(1, int(config.get("required_misses") or 1)),
            ),
        )
        self._sessions[session_id] = session
        return session

    def _provider_health(self, name: str, provider_config: dict[str, Any]) -> dict[str, Any]:
        try:
            health = VADFactory.create(name, **provider_config).health()
        except Exception as error:  # noqa: BLE001
            return {"available": False, "reason": str(error)}
        return {"available": health.available, "reason": health.reason}

    def _active_provider(self, config: dict[str, Any]) -> str:
        provider = str(config.get("vad_model") or "fake")
        self._ensure_provider_registered(provider)
        return provider

    def _provider_config(self, config: dict[str, Any], provider: str) -> dict[str, Any]:
        value = config.get(provider)
        if isinstance(value, dict):
            return dict(value)
        return {}

    def _ensure_provider_registered(self, provider: str) -> None:
        if provider not in VADFactory.available():
            raise VADConfigError(
                f"Unknown VAD provider: {provider!r}. Available: {VADFactory.available()}"
            )
