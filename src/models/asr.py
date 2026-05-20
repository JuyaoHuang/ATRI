"""ASR API schemas.

ASR API 数据模式。

Reference: docs/ASR模块设计文档.md
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ASRProviderStatus(BaseModel):
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
    supports_backend_transcription: bool
    supports_browser_streaming: bool
    config: dict[str, Any] = Field(default_factory=dict)


class ASRConfigResponse(BaseModel):
    """OLV-shaped ASR config response.

    OLV 格式的 ASR 配置响应。
    """

    config: dict[str, Any]
    providers: list[ASRProviderStatus] = Field(default_factory=list)


class ASRHealthResponse(BaseModel):
    """ASR health response.

    ASR 健康检查响应。
    """

    active_provider: str
    active_available: bool
    providers: list[ASRProviderStatus] = Field(default_factory=list)


class ASRProviderSwitchRequest(BaseModel):
    """Switch active provider payload.

    切换活跃提供商的请求载荷。
    """

    provider: str = Field(..., min_length=1)


class ASRTranscriptionResponse(BaseModel):
    """Transcription result response.

    转录结果响应。
    """

    provider: str
    text: str
