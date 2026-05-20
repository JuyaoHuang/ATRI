"""Character API schemas used by Phase 7.

角色 API 数据模式（Phase 7）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CharacterSummary(BaseModel):
    """Character summary returned by list endpoints.

    列表接口返回的角色摘要。
    """

    character_id: str
    name: str
    avatar: str | None = None
    avatar_url: str | None = None
    greeting: str | None = None
    description: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    is_system: bool = True


class CharacterDetail(CharacterSummary):
    """Character detail with full system prompt.

    包含完整系统提示词的角色详情。
    """

    system_prompt: str


class CharacterCreateRequest(BaseModel):
    """Payload for creating a character.

    创建角色的请求载荷。
    """

    character_id: str | None = Field(default=None, max_length=64)
    name: str = Field(..., min_length=1, max_length=50)
    greeting: str | None = None
    description: str | None = None
    system_prompt: str = Field(..., min_length=1)


class CharacterUpdateRequest(BaseModel):
    """Payload for updating a character.

    更新角色的请求载荷。
    """

    name: str | None = Field(default=None, min_length=1, max_length=50)
    greeting: str | None = None
    description: str | None = None
    system_prompt: str | None = Field(default=None, min_length=1)


class AvatarUploadResponse(BaseModel):
    """Response payload for avatar upload.

    头像上传的响应载荷。
    """

    character_id: str
    avatar: str
    avatar_url: str
