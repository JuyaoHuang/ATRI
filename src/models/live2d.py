"""Live2D API schemas used by Phase 8."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Live2DModelSummary(BaseModel):
    """Live2D model summary returned by management endpoints."""

    id: str
    name: str
    model_path: str
    model_url: str
    thumbnail_url: str | None = None
    expressions: list[str] = Field(default_factory=list)
    created_at: str
    is_default: bool = False


class Live2DExpressionList(BaseModel):
    """Expression list returned for a specific model."""

    model_id: str
    expressions: list[str] = Field(default_factory=list)
