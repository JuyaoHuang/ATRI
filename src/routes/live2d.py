"""Live2D management REST API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)

from ..models.live2d import Live2DExpressionList, Live2DModelSummary
from ..storage.live2d_storage import (
    Live2DArchiveValidationError,
    Live2DModelNotFoundError,
    Live2DStorage,
    Live2DStorageError,
)

router = APIRouter(prefix="/api/live2d/models", tags=["live2d"])


def get_live2d_storage(request: Request) -> Live2DStorage:
    """Return app-scoped Live2D storage, creating a default one if needed."""

    storage = getattr(request.app.state, "live2d_storage", None)
    if storage is None:
        storage = Live2DStorage()
        request.app.state.live2d_storage = storage
    return storage


Live2DStorageDep = Annotated[Live2DStorage, Depends(get_live2d_storage)]
ModelArchive = Annotated[UploadFile, File(...)]


def _serialize_model(record, request: Request, storage: Live2DStorage) -> Live2DModelSummary:
    return Live2DModelSummary(
        id=record.id,
        name=record.name,
        model_path=record.model_path,
        model_url=storage.build_asset_url(
            f"{record.id}/{record.model_path}", str(request.base_url)
        ),
        thumbnail_url=(
            storage.build_asset_url(f"{record.id}/{record.thumbnail_path}", str(request.base_url))
            if record.thumbnail_path
            else None
        ),
        expressions=record.expressions,
        created_at=record.created_at,
        is_default=record.is_default,
    )


def _handle_live2d_error(error: Exception) -> HTTPException:
    if isinstance(error, Live2DModelNotFoundError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, Live2DArchiveValidationError):
        return HTTPException(status_code=400, detail=str(error))
    if isinstance(error, Live2DStorageError):
        return HTTPException(status_code=400, detail=str(error))
    return HTTPException(status_code=500, detail="Live2D storage operation failed")


@router.get("", response_model=list[Live2DModelSummary])
async def list_live2d_models(
    request: Request,
    storage: Live2DStorageDep,
) -> list[Live2DModelSummary]:
    """List all stored Live2D models."""

    return [_serialize_model(record, request, storage) for record in storage.list_models()]


@router.post("", response_model=Live2DModelSummary, status_code=status.HTTP_201_CREATED)
async def upload_live2d_model(
    request: Request,
    model: ModelArchive,
    storage: Live2DStorageDep,
    name: str | None = Form(default=None),
) -> Live2DModelSummary:
    """Upload and extract a Live2D ZIP archive."""

    try:
        record = await storage.save_model(model, name=name)
    except Exception as error:
        raise _handle_live2d_error(error) from error

    return _serialize_model(record, request, storage)


@router.get("/{model_id}/expressions", response_model=Live2DExpressionList)
async def get_live2d_expressions(
    model_id: str,
    storage: Live2DStorageDep,
) -> Live2DExpressionList:
    """Return the expression list for one Live2D model."""

    try:
        expressions = storage.list_expressions(model_id)
    except Exception as error:
        raise _handle_live2d_error(error) from error

    return Live2DExpressionList(model_id=model_id, expressions=expressions)


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_live2d_model(
    model_id: str,
    storage: Live2DStorageDep,
) -> Response:
    """Delete one Live2D model directory."""

    try:
        storage.delete_model(model_id)
    except Exception as error:
        raise _handle_live2d_error(error) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)
