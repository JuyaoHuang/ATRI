"""Visual configuration REST API schemas.

视觉配置 REST API 数据模式。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class VisionCaptureConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_type: Literal["image/jpeg"]
    jpeg_quality: float = Field(gt=0, le=1)
    max_long_edge: int = Field(gt=0)
    max_decoded_bytes: int = Field(gt=0)
    timeout_ms: int = Field(gt=0)


class VisionProviderConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: Literal["auto", "low", "high"]


class VisionTransportConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    websocket_max_message_bytes: int = Field(gt=0)


class VisionConfigResponse(BaseModel):
    """Complete safe visual configuration returned to the frontend."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    source: Literal["screen"]
    capture: VisionCaptureConfigResponse
    provider: VisionProviderConfigResponse
    transport: VisionTransportConfigResponse


class VisionConfigUpdateRequest(BaseModel):
    """Only persistent visual field writable by the first settings page."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool
