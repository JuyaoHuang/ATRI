"""Read-only Live2D catalog REST API routes.

只读 Live2D 模型目录 REST API 路由。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from ..models.live2d import Live2DExpressionList, Live2DModelSummary
from ..storage.live2d_storage import (
    Live2DModelNotFoundError,
    Live2DModelRecord,
    Live2DStorage,
    Live2DStorageError,
)

router = APIRouter(prefix="/api/live2d/models", tags=["live2d"])


def get_live2d_storage(request: Request) -> Live2DStorage:
    """Return app-scoped Live2D storage, creating a default one if needed.

    返回应用级 Live2D 存储，若不存在则创建默认实例。
    """

    storage = getattr(request.app.state, "live2d_storage", None)
    if storage is None:
        config = getattr(request.app.state, "config", {})
        live2d_config = config.get("live2d", {}) if isinstance(config, dict) else {}
        default_model_id = (
            live2d_config.get("default_model") if isinstance(live2d_config, dict) else None
        )
        storage = Live2DStorage(
            default_model_id=default_model_id if isinstance(default_model_id, str) else None
        )
        request.app.state.live2d_storage = storage
    return storage


Live2DStorageDep = Annotated[Live2DStorage, Depends(get_live2d_storage)]


def _serialize_model(
    record: Live2DModelRecord,
    request: Request,
    storage: Live2DStorage,
) -> Live2DModelSummary:
    thumbnail_url = None
    if record.thumbnail_path:
        thumbnail_url = storage.build_asset_url(
            f"{record.id}/{record.thumbnail_path}", str(request.base_url)
        )
        thumbnail_url = f"{thumbnail_url}?preview=1"

    return Live2DModelSummary(
        id=record.id,
        name=record.name,
        model_path=record.model_path,
        model_url=storage.build_asset_url(
            f"{record.id}/{record.model_path}", str(request.base_url)
        ),
        thumbnail_url=thumbnail_url,
        expressions=record.expressions,
        is_default=record.is_default,
    )


def _handle_live2d_error(error: Exception) -> HTTPException:
    if isinstance(error, Live2DModelNotFoundError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, Live2DStorageError):
        return HTTPException(status_code=400, detail=str(error))
    return HTTPException(status_code=500, detail="Live2D storage operation failed")


@router.get("", response_model=list[Live2DModelSummary])
async def list_live2d_models(
    request: Request,
    storage: Live2DStorageDep,
) -> list[Live2DModelSummary]:
    """List all stored Live2D models.

    列出所有存储的 Live2D 模型。
    """

    records = await storage.list_models()
    return [_serialize_model(record, request, storage) for record in records]


@router.get("/{model_id}/expressions", response_model=Live2DExpressionList)
async def get_live2d_expressions(
    model_id: str,
    storage: Live2DStorageDep,
) -> Live2DExpressionList:
    """Return the expression list for one Live2D model.

    返回单个 Live2D 模型的表情列表。
    """

    try:
        expressions = await storage.list_expressions(model_id)
    except Exception as error:
        raise _handle_live2d_error(error) from error

    return Live2DExpressionList(model_id=model_id, expressions=expressions)
