"""TTS API schemas.

TTS API 数据模式。

Reference: docs/TTS模块设计文档.md
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TTSProviderStatus(BaseModel):
    """Provider metadata plus runtime availability.

    提供商元数据及运行时可用性。
    """

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
    """OLV-shaped TTS config response.

    OLV 格式的 TTS 配置响应。
    """

    config: dict[str, Any]
    providers: list[TTSProviderStatus] = Field(default_factory=list)


class TTSHealthResponse(BaseModel):
    """TTS health response.

    TTS 健康检查响应。
    """

    active_provider: str
    active_available: bool
    providers: list[TTSProviderStatus] = Field(default_factory=list)


class TTSProviderSwitchRequest(BaseModel):
    """Switch active provider payload.

    切换活跃提供商的请求载荷。
    """

    provider: str = Field(..., min_length=1)


class TTSVoiceInfo(BaseModel):
    """Voice metadata for settings UI.

    用于设置界面的语音元数据。
    """

    id: str
    name: str
    language: str | None = None
    gender: str | None = None
    description: str | None = None
    preview_url: str | None = None


class TTSVoicesResponse(BaseModel):
    """Provider voices response.

    提供商语音列表响应。
    """

    provider: str
    voices: list[TTSVoiceInfo] = Field(default_factory=list)


class TTSSynthesisRequest(BaseModel):
    """Complete-text synthesis request.

    完整文本合成请求。
    """

    text: str = Field(..., min_length=1)
    provider: str | None = None
    voice_id: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
