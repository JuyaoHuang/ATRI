"""Read-only Live2D catalog API schemas.

只读 Live2D 模型目录 API 数据模式。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Live2DModelSummary(BaseModel):
    """Live2D model summary derived from an installed directory.

    从已安装目录派生的 Live2D 模型摘要。
    """

    id: str
    name: str
    model_path: str
    model_url: str
    thumbnail_url: str | None = None
    expressions: list[str] = Field(default_factory=list)
    is_default: bool = False


class Live2DExpressionList(BaseModel):
    """Expression list returned for a specific model.

    针对特定模型返回的表情列表。
    """

    model_id: str
    expressions: list[str] = Field(default_factory=list)
