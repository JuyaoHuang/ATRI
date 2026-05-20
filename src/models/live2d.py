"""Live2D API schemas used by Phase 8.

Live2D API 数据模式（Phase 8）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Live2DModelSummary(BaseModel):
    """Live2D model summary returned by management endpoints.

    管理接口返回的 Live2D 模型摘要。
    """

    id: str
    name: str
    model_path: str
    model_url: str
    thumbnail_url: str | None = None
    expressions: list[str] = Field(default_factory=list)
    created_at: str
    is_default: bool = False


class Live2DExpressionList(BaseModel):
    """Expression list returned for a specific model.

    针对特定模型返回的表情列表。
    """

    model_id: str
    expressions: list[str] = Field(default_factory=list)


class Live2DModelUpdateRequest(BaseModel):
    """Payload for updating one Live2D model.

    更新单个 Live2D 模型的请求载荷。
    """

    name: str = Field(..., min_length=1, max_length=120)
