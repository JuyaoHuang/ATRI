"""TTS management and synthesis REST API routes.

TTS 管理与合成 REST API 路由。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from loguru import logger

from src.models.tts import (
    TTSConfigResponse,
    TTSHealthResponse,
    TTSProviderStatus,
    TTSProviderSwitchRequest,
    TTSSynthesisRequest,
    TTSVoicesResponse,
)
from src.tts import TTSConfigStore, TTSService
from src.tts.exceptions import (
    TTSAPIError,
    TTSConfigError,
    TTSProviderUnavailableError,
    TTSRateLimitError,
    TTSSynthesisError,
)

router = APIRouter(prefix="/api/tts", tags=["tts"])


def get_tts_service(request: Request) -> TTSService:
    """Return app-scoped TTS service, creating a default one if needed.

    返回应用级 TTS 服务，若不存在则创建默认实例。
    """

    service = getattr(request.app.state, "tts_service", None)
    if service is None:
        service = TTSService(TTSConfigStore(request.app.state.config.get("tts", {})))
        request.app.state.tts_service = service
    return service


TTSServiceDep = Annotated[TTSService, Depends(get_tts_service)]


def _provider_status_list(raw: list[dict[str, Any]]) -> list[TTSProviderStatus]:
    return [TTSProviderStatus(**provider) for provider in raw]


def _handle_tts_error(error: Exception) -> HTTPException:
    if isinstance(error, TTSConfigError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if isinstance(error, TTSProviderUnavailableError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
    if isinstance(error, TTSRateLimitError):
        return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(error))
    if isinstance(error, TTSAPIError):
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error))
    if isinstance(error, TTSSynthesisError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="TTS operation failed",
    )


@router.get("/providers", response_model=list[TTSProviderStatus])
async def list_tts_providers(service: TTSServiceDep) -> list[TTSProviderStatus]:
    """List registered TTS providers with health and config state.

    列出已注册的 TTS 提供商及其健康状态与配置信息。
    """

    return _provider_status_list(service.list_providers())


@router.get("/config", response_model=TTSConfigResponse)
async def get_tts_config(service: TTSServiceDep) -> TTSConfigResponse:
    """Return current OLV-shaped TTS config and provider statuses.

    返回当前 OLV 格式的 TTS 配置和提供商状态。
    """

    return TTSConfigResponse(
        config=service.get_config(),
        providers=_provider_status_list(service.list_providers()),
    )


@router.put("/config", response_model=TTSConfigResponse)
async def update_tts_config(
    payload: dict[str, Any],
    service: TTSServiceDep,
) -> TTSConfigResponse:
    """Merge and persist a partial OLV-shaped TTS config update.

    合并并持久化部分 OLV 格式的 TTS 配置更新。
    """

    try:
        service.update_config(payload)
    except Exception as error:
        raise _handle_tts_error(error) from error

    return TTSConfigResponse(
        config=service.get_config(),
        providers=_provider_status_list(service.list_providers()),
    )


@router.post("/switch", response_model=TTSConfigResponse)
async def switch_tts_provider(
    payload: TTSProviderSwitchRequest,
    service: TTSServiceDep,
) -> TTSConfigResponse:
    """Switch active TTS provider.

    切换活跃的 TTS 提供商。
    """

    try:
        service.switch_provider(payload.provider)
    except Exception as error:
        raise _handle_tts_error(error) from error

    return TTSConfigResponse(
        config=service.get_config(),
        providers=_provider_status_list(service.list_providers()),
    )


@router.get("/health", response_model=TTSHealthResponse)
async def get_tts_health(service: TTSServiceDep) -> TTSHealthResponse:
    """Return active provider and all-provider health.

    返回活跃提供商及所有提供商的健康状态。
    """

    health = service.health()
    return TTSHealthResponse(
        active_provider=health["active_provider"],
        active_available=health["active_available"],
        providers=_provider_status_list(health["providers"]),
    )


@router.get("/voices", response_model=TTSVoicesResponse)
async def get_tts_voices(
    service: TTSServiceDep,
    provider: str | None = None,
) -> TTSVoicesResponse:
    """Return voices for active or requested TTS provider.

    返回活跃或指定 TTS 提供商的语音列表。
    """

    try:
        result = await service.get_voices(provider=provider)
    except Exception as error:
        raise _handle_tts_error(error) from error
    return TTSVoicesResponse(**result)


@router.post("/synthesize")
async def synthesize_text(
    payload: TTSSynthesisRequest,
    service: TTSServiceDep,
) -> Response:
    """Synthesize text with the active or requested TTS provider.

    使用活跃或指定的 TTS 提供商合成文本。
    """

    logger.info(
        "TTS synth request received | provider={} | text_len={} | voice_id={} | options_keys={}",
        payload.provider or "<active>",
        len(payload.text.strip()),
        payload.voice_id or "<default>",
        sorted(payload.options.keys()) if payload.options else [],
    )

    try:
        result = await service.synthesize(
            payload.text,
            provider=payload.provider,
            voice_id=payload.voice_id,
            options=payload.options,
        )
    except Exception as error:
        raise _handle_tts_error(error) from error

    return Response(
        content=result["audio"],
        media_type=result["media_type"],
        headers={"X-TTS-Provider": str(result["provider"])},
    )
