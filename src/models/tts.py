"""TTS API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TTSProviderStatus(BaseModel):
    """Provider metadata plus runtime availability."""

    name: str
    display_name: str
    provider_type: str
    description: str
    active: bool
    available: bool
    reason: str | None = None
    supports_streaming: bool
    media_type: str
    config: dict[str, Any] = Field(default_factory=dict)


class TTSConfigResponse(BaseModel):
    """OLV-shaped TTS config response."""

    config: dict[str, Any]
    providers: list[TTSProviderStatus] = Field(default_factory=list)


class TTSHealthResponse(BaseModel):
    """TTS health response."""

    active_provider: str
    active_available: bool
    providers: list[TTSProviderStatus] = Field(default_factory=list)


class TTSProviderSwitchRequest(BaseModel):
    """Switch active provider payload."""

    provider: str = Field(..., min_length=1)


class TTSVoiceInfo(BaseModel):
    """Voice metadata for settings UI."""

    id: str
    name: str
    language: str | None = None
    gender: str | None = None
    description: str | None = None
    preview_url: str | None = None


class TTSVoicesResponse(BaseModel):
    """Provider voices response."""

    provider: str
    voices: list[TTSVoiceInfo] = Field(default_factory=list)


class TTSSynthesisRequest(BaseModel):
    """Complete-text synthesis request."""

    text: str = Field(..., min_length=1)
    provider: str | None = None
    voice_id: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
