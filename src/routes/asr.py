"""ASR management and transcription REST API routes.

ASR 管理与转录 REST API 路由。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from src.asr import ASRConfigStore, ASRService
from src.asr.exceptions import ASRConfigError, ASRProviderUnavailableError, ASRTranscriptionError
from src.models.asr import (
    ASRConfigResponse,
    ASRHealthResponse,
    ASRProviderStatus,
    ASRProviderSwitchRequest,
    ASRTranscriptionResponse,
)

router = APIRouter(prefix="/api/asr", tags=["asr"])


def get_asr_service(request: Request) -> ASRService:
    """Return app-scoped ASR service, creating a default one if needed.

    返回应用级 ASR 服务，若不存在则创建默认实例。
    """

    service = getattr(request.app.state, "asr_service", None)
    if service is None:
        service = ASRService(ASRConfigStore(request.app.state.config.get("asr", {})))
        request.app.state.asr_service = service
    return service


ASRServiceDep = Annotated[ASRService, Depends(get_asr_service)]
AudioFile = Annotated[UploadFile, File(...)]


def _provider_status_list(raw: list[dict[str, Any]]) -> list[ASRProviderStatus]:
    return [ASRProviderStatus(**provider) for provider in raw]


def _handle_asr_error(error: Exception) -> HTTPException:
    if isinstance(error, ASRConfigError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if isinstance(error, ASRProviderUnavailableError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
    if isinstance(error, ASRTranscriptionError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="ASR operation failed",
    )


@router.get("/providers", response_model=list[ASRProviderStatus])
async def list_asr_providers(service: ASRServiceDep) -> list[ASRProviderStatus]:
    """List registered ASR providers with health and config state.

    列出已注册的 ASR 提供商及其健康状态与配置信息。
    """

    return _provider_status_list(service.list_providers())


@router.get("/config", response_model=ASRConfigResponse)
async def get_asr_config(service: ASRServiceDep) -> ASRConfigResponse:
    """Return current OLV-shaped ASR config and provider statuses.

    返回当前 OLV 格式的 ASR 配置和提供商状态。
    """

    return ASRConfigResponse(
        config=service.get_config(),
        providers=_provider_status_list(service.list_providers()),
    )


@router.put("/config", response_model=ASRConfigResponse)
async def update_asr_config(
    payload: dict[str, Any],
    service: ASRServiceDep,
) -> ASRConfigResponse:
    """Merge and persist a partial OLV-shaped ASR config update.

    合并并持久化部分 OLV 格式的 ASR 配置更新。
    """

    try:
        service.update_config(payload)
    except Exception as error:
        raise _handle_asr_error(error) from error

    return ASRConfigResponse(
        config=service.get_config(),
        providers=_provider_status_list(service.list_providers()),
    )


@router.post("/switch", response_model=ASRConfigResponse)
async def switch_asr_provider(
    payload: ASRProviderSwitchRequest,
    service: ASRServiceDep,
) -> ASRConfigResponse:
    """Switch active ASR provider.

    切换活跃的 ASR 提供商。
    """

    try:
        service.switch_provider(payload.provider)
    except Exception as error:
        raise _handle_asr_error(error) from error

    return ASRConfigResponse(
        config=service.get_config(),
        providers=_provider_status_list(service.list_providers()),
    )


@router.get("/health", response_model=ASRHealthResponse)
async def get_asr_health(service: ASRServiceDep) -> ASRHealthResponse:
    """Return active provider and all-provider health.

    返回活跃提供商及所有提供商的健康状态。
    """

    health = service.health()
    return ASRHealthResponse(
        active_provider=health["active_provider"],
        active_available=health["active_available"],
        providers=_provider_status_list(health["providers"]),
    )


@router.post("/transcribe", response_model=ASRTranscriptionResponse)
async def transcribe_audio(
    audio: AudioFile,
    service: ASRServiceDep,
    provider: str | None = None,
) -> ASRTranscriptionResponse:
    """Transcribe uploaded audio with the active or requested ASR provider.

    使用活跃或指定的 ASR 提供商转录上传的音频。
    """

    try:
        payload = await audio.read()
        result = await service.transcribe_audio(
            payload,
            filename=audio.filename,
            content_type=audio.content_type,
            provider=provider,
        )
    except Exception as error:
        raise _handle_asr_error(error) from error

    return ASRTranscriptionResponse(**result)
