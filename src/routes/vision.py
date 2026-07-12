"""Visual configuration REST API routes.

视觉配置 REST API 路由。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError

from src.models.vision import VisionConfigResponse, VisionConfigUpdateRequest
from src.vision import VisionConfigError, VisionConfigStore, VisionService

router = APIRouter(prefix="/api/vision", tags=["vision"])


def get_vision_service(request: Request) -> VisionService:
    """Return the application-scoped visual configuration service."""

    service = getattr(request.app.state, "vision_service", None)
    if service is None:
        service = VisionService(VisionConfigStore(request.app.state.config.get("vision", {})))
        request.app.state.vision_service = service
    return service


VisionServiceDep = Annotated[VisionService, Depends(get_vision_service)]


@router.get("/config", response_model=VisionConfigResponse)
async def get_vision_config(service: VisionServiceDep) -> VisionConfigResponse:
    """Return the complete safe visual configuration."""

    return VisionConfigResponse.model_validate(service.get_config())


@router.put("/config", response_model=VisionConfigResponse)
async def update_vision_config(
    payload: dict[str, Any],
    service: VisionServiceDep,
) -> VisionConfigResponse:
    """Persist only the visual module ``enabled`` switch."""

    try:
        request_model = VisionConfigUpdateRequest.model_validate(payload)
        config = await service.update_config(request_model.model_dump())
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vision config update must contain only a boolean 'enabled' field",
        ) from error
    except VisionConfigError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    return VisionConfigResponse.model_validate(config)
