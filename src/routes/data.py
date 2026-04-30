"""Data maintenance REST API routes."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from loguru import logger
from pydantic import BaseModel, Field

from src.auth import get_request_user_id
from src.memory.long_term import LongTermMemory
from src.service_context import ServiceContext, _safe_build_long_term

router = APIRouter(prefix="/api/data", tags=["data"])

_SHORT_TERM_FILENAME = "short_term_memory.json"


class DataCleanupResponse(BaseModel):
    """Response for data cleanup operations."""

    character_id: str
    user_id: str
    chat_id: str | None = None
    target: str
    status: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


def _service_context(request: Request) -> ServiceContext:
    context = getattr(request.app.state, "service_context", None)
    if not isinstance(context, ServiceContext):
        context = ServiceContext(getattr(request.app.state, "config", {}))
        request.app.state.service_context = context
    return context


async def _unlink_if_exists(path: Path) -> bool:
    def _delete() -> bool:
        if not path.exists():
            return False
        path.unlink()
        return True

    return await asyncio.to_thread(_delete)


async def _ensure_user_chat(
    request: Request,
    user_id: str,
    character_id: str,
    chat_id: str,
) -> dict:
    storage = request.app.state.storage
    try:
        chat = await storage.get_chat_for_user_character(user_id, character_id, chat_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if chat is None or chat.get("character_id") != character_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat '{chat_id}' not found for character '{character_id}'",
        )
    return chat


def _get_long_term_memory(request: Request, character_id: str, user_id: str) -> LongTermMemory:
    context = _service_context(request)
    cached = context.get_cached_long_term_memory(character_id, user_id)
    if cached is not None:
        return cached

    config = getattr(request.app.state, "config", {})
    long_term = _safe_build_long_term(config.get("memory", {}).get("mem0", {}))
    if long_term is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Long-term memory backend is not available",
        )
    return long_term


@router.delete(
    "/characters/{character_id}/chats/{chat_id}/short-term-memory",
    response_model=DataCleanupResponse,
)
async def clear_short_term_memory(
    character_id: str,
    chat_id: str,
    request: Request,
) -> DataCleanupResponse:
    """Clear short-term memory for current user, character, and chat."""

    user_id = get_request_user_id(request)
    await _ensure_user_chat(request, user_id, character_id, chat_id)
    context = _service_context(request)
    try:
        chat_dir = Path(context.get_character_chat_memory_dir(character_id, user_id, chat_id))
        short_term_path = chat_dir / _SHORT_TERM_FILENAME
        tmp_path = short_term_path.with_suffix(".json.tmp")
        legacy_path = (
            Path(context.get_legacy_character_memory_dir(character_id)) / _SHORT_TERM_FILENAME
        )
        character_scoped_path = (
            Path(context.get_character_memory_dir(character_id, user_id)) / _SHORT_TERM_FILENAME
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    removed_short_term = await _unlink_if_exists(short_term_path)
    removed_tmp = await _unlink_if_exists(tmp_path)
    cache_reset = context.reset_short_term_memory(character_id, user_id, chat_id)

    logger.info(
        "Short-term memory cleared | character={} | user_id={} | chat_id={} | "
        "removed={} | cache_reset={}",
        character_id,
        user_id,
        chat_id,
        removed_short_term,
        cache_reset,
    )

    return DataCleanupResponse(
        character_id=character_id,
        user_id=user_id,
        chat_id=chat_id,
        target="short_term_memory",
        status="cleared",
        message="短期记忆已清理，并已同步当前运行中的记忆状态。",
        details={
            "path": str(short_term_path),
            "character_scoped_path": str(character_scoped_path),
            "legacy_path": str(legacy_path),
            "removed_file": removed_short_term,
            "removed_tmp": removed_tmp,
            "cache_reset": cache_reset,
        },
    )


@router.delete(
    "/characters/{character_id}/long-term-memory",
    response_model=DataCleanupResponse,
)
async def clear_long_term_memory(
    character_id: str,
    request: Request,
) -> DataCleanupResponse:
    """Submit long-term memory deletion for current user and character."""

    user_id = get_request_user_id(request)
    long_term = _get_long_term_memory(request, character_id, user_id)

    try:
        result = await long_term.delete_all(user_id=user_id, agent_id=character_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Long-term memory deletion failed: {exc}",
        ) from exc

    logger.info(
        "Long-term memory delete submitted | character={} | user_id={} | result={}",
        character_id,
        user_id,
        result,
    )

    return DataCleanupResponse(
        character_id=character_id,
        user_id=user_id,
        target="long_term_memory",
        status="submitted",
        message="长期记忆删除已提交，可能稍后完成。",
        details={"mem0": result},
    )
