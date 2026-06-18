"""JSON file-based chat storage implementation.

基于 JSON 文件的聊天存储实现。
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import Any, NamedTuple

from src.memory._io_utils import atomic_replace
from src.storage.interface import ChatStorageInterface


class _ChatLocation(NamedTuple):
    """Internal record pointing to a chat's location on disk.

    内部记录，指向聊天在磁盘上的位置。
    """

    user_id: str
    character_id: str
    chat: dict


_MESSAGE_METADATA_KEYS = {"generation_id", "interrupted", "interrupt_reason"}


def _validate_path_component(label: str, value: str) -> str:
    """Validate a string as a safe single-path component.

    校验字符串是否为安全的单级路径分量。
    """
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    clean = value.strip()
    path = PurePath(clean)
    if (
        not clean
        or clean in {".", ".."}
        or path.is_absolute()
        or len(path.parts) != 1
        or "/" in clean
        or "\\" in clean
    ):
        raise ValueError(f"Invalid {label}: {value!r}")
    return clean


def _clean_message_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}

    clean: dict[str, Any] = {}
    generation_id = metadata.get("generation_id")
    if isinstance(generation_id, str) and generation_id.strip():
        clean["generation_id"] = generation_id.strip()

    if metadata.get("interrupted") is True:
        clean["interrupted"] = True

    interrupt_reason = metadata.get("interrupt_reason")
    if isinstance(interrupt_reason, str) and interrupt_reason.strip():
        clean["interrupt_reason"] = interrupt_reason.strip()

    return {key: value for key, value in clean.items() if key in _MESSAGE_METADATA_KEYS}


class JSONChatStorage(ChatStorageInterface):
    """JSON file-based chat storage with file system persistence.

    基于 JSON 文件的聊天存储，使用文件系统进行持久化。
    """

    def __init__(self, base_path: str):
        """Initialize the storage with a base directory path.

        使用指定的根目录路径初始化存储。
        """
        self.base_path = Path(base_path)

    def _get_user_dir(self, user_id: str, character_id: str) -> Path:
        """Get user-character directory path.

        获取用户-角色目录路径。
        """
        safe_user_id = _validate_path_component("user_id", user_id)
        safe_character_id = _validate_path_component("character_id", character_id)
        return self.base_path / safe_user_id / safe_character_id

    def _get_index_path(self, user_id: str, character_id: str) -> Path:
        """Get index.json path.

        获取 index.json 文件路径。
        """
        return self._get_user_dir(user_id, character_id) / "index.json"

    def _get_session_path(self, user_id: str, character_id: str, chat_id: str) -> Path:
        """Get session file path.

        获取会话文件路径。
        """
        safe_chat_id = _validate_path_component("chat_id", chat_id)
        return self._get_user_dir(user_id, character_id) / "sessions" / f"{safe_chat_id}.json"

    async def _read_json(self, path: Path) -> dict | list | None:
        """Read JSON file asynchronously.

        异步读取 JSON 文件。
        """

        def _read():
            if not path.exists():
                return None
            with open(path, encoding="utf-8") as f:
                return json.load(f)

        return await asyncio.to_thread(_read)

    async def _write_json(self, path: Path, data: dict | list) -> None:
        """Write JSON file atomically.

        原子写入 JSON 文件。
        """

        def _write():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            atomic_replace(tmp, path)

        await asyncio.to_thread(_write)

    async def _load_index(self, user_id: str, character_id: str) -> dict:
        """Load index.json or return empty structure.

        加载 index.json，若不存在则返回空结构。
        """
        index_path = self._get_index_path(user_id, character_id)
        data = await self._read_json(index_path)
        if isinstance(data, dict):
            return data
        return {"chats": []}

    async def _save_index(self, user_id: str, character_id: str, index: dict) -> None:
        """Save index.json atomically.

        原子保存 index.json。
        """
        index_path = self._get_index_path(user_id, character_id)
        await self._write_json(index_path, index)

    def _generate_chat_id(self) -> str:
        """Generate chat ID in format: YYYYMMDD_uuid8.

        生成聊天 ID，格式为 YYYYMMDD_uuid8。
        """
        date_str = datetime.now(UTC).strftime("%Y%m%d")
        uuid_str = str(uuid.uuid4())[:8]
        return f"{date_str}_{uuid_str}"

    async def _find_chat_location(
        self,
        chat_id: str,
        user_id: str | None = None,
        character_id: str | None = None,
    ) -> _ChatLocation | None:
        """Find a chat location, optionally scoped to one user/character.

        查找聊天位置，可限定到特定用户/角色。
        """
        safe_chat_id = _validate_path_component("chat_id", chat_id)
        safe_user_id = _validate_path_component("user_id", user_id) if user_id is not None else None
        safe_character_id = (
            _validate_path_component("character_id", character_id)
            if character_id is not None
            else None
        )
        if not self.base_path.is_dir():
            return None

        user_dirs = (
            [self.base_path / safe_user_id]
            if safe_user_id is not None
            else list(self.base_path.iterdir())
        )
        for user_dir in user_dirs:
            if not user_dir.is_dir():
                continue
            char_dirs = (
                [user_dir / safe_character_id]
                if safe_character_id is not None
                else list(user_dir.iterdir())
            )
            for char_dir in char_dirs:
                if not char_dir.is_dir():
                    continue
                index = await self._load_index(user_dir.name, char_dir.name)
                for chat in index["chats"]:
                    if chat["id"] == safe_chat_id:
                        return _ChatLocation(user_dir.name, char_dir.name, chat)
        return None

    async def create_chat(self, user_id: str, character_id: str, title: str) -> dict:
        """Create a new chat session.

        创建新的聊天会话。
        """
        chat_id = self._generate_chat_id()
        now = datetime.now(UTC).isoformat()

        chat_meta = {
            "id": chat_id,
            "title": title,
            "character_id": character_id,
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
        }

        # Update index
        index = await self._load_index(user_id, character_id)
        index["chats"].append(chat_meta)
        await self._save_index(user_id, character_id, index)

        # Create empty session file
        session_path = self._get_session_path(user_id, character_id, chat_id)
        await self._write_json(session_path, {"messages": []})

        return chat_meta

    async def list_chats(self, user_id: str, character_id: str | None = None) -> list[dict]:
        """List user's chat sessions, sorted by updated_at descending.

        列出用户的聊天会话，按 updated_at 降序排列。
        """
        if character_id:
            index = await self._load_index(user_id, character_id)
            chats = index["chats"]
        else:
            # Aggregate across all characters
            chats = []
            safe_user_id = _validate_path_component("user_id", user_id)
            user_dir = self.base_path / safe_user_id
            if user_dir.exists():
                for char_dir in user_dir.iterdir():
                    if char_dir.is_dir():
                        index = await self._load_index(safe_user_id, char_dir.name)
                        chats.extend(index["chats"])

        # Sort by updated_at descending
        chats.sort(key=lambda c: c["updated_at"], reverse=True)
        return chats

    async def get_chat(self, chat_id: str) -> dict | None:
        """Get chat metadata by ID (requires scanning all user directories).

        根据 ID 获取聊天元数据（需要扫描所有用户目录）。
        """
        location = await self._find_chat_location(chat_id)
        return location.chat if location else None

    async def get_chat_for_user(self, user_id: str, chat_id: str) -> dict | None:
        """Get chat metadata by ID, scoped to a user.

        根据 ID 获取聊天元数据，限定到特定用户。
        """
        location = await self._find_chat_location(chat_id, user_id=user_id)
        return location.chat if location else None

    async def get_chat_for_user_character(
        self, user_id: str, character_id: str, chat_id: str
    ) -> dict | None:
        """Get chat metadata by ID, scoped to one user-character index.

        根据 ID 获取聊天元数据，限定到特定用户-角色索引。
        """
        location = await self._find_chat_location(
            chat_id,
            user_id=user_id,
            character_id=character_id,
        )
        return location.chat if location else None

    async def update_chat(self, chat_id: str, **kwargs: str) -> dict:
        """Update chat metadata (title, etc.).

        更新聊天元数据（如标题等）。
        """
        location = await self._find_chat_location(chat_id)
        if not location:
            raise ValueError(f"Chat {chat_id} not found")
        return await self.update_chat_for_user(location.user_id, chat_id, **kwargs)

    async def update_chat_for_user(self, user_id: str, chat_id: str, **kwargs: str) -> dict:
        """Update chat metadata for a specific user.

        更新特定用户的聊天元数据。
        """
        location = await self._find_chat_location(chat_id, user_id=user_id)
        if not location:
            raise ValueError(f"Chat {chat_id} not found")

        index = await self._load_index(user_id, location.character_id)
        for chat in index["chats"]:
            if chat["id"] == chat_id:
                chat.update(kwargs)
                chat["updated_at"] = datetime.now(UTC).isoformat()
                await self._save_index(user_id, location.character_id, index)
                return chat
        raise ValueError(f"Chat {chat_id} not found")

    async def delete_chat(self, chat_id: str) -> None:
        """Delete chat session.

        删除聊天会话。
        """
        location = await self._find_chat_location(chat_id)
        if not location:
            raise ValueError(f"Chat {chat_id} not found")
        await self.delete_chat_for_user(location.user_id, chat_id)

    async def delete_chat_for_user(self, user_id: str, chat_id: str) -> None:
        """Delete chat session for a specific user.

        删除特定用户的聊天会话。
        """
        location = await self._find_chat_location(chat_id, user_id=user_id)
        if not location:
            raise ValueError(f"Chat {chat_id} not found")

        index = await self._load_index(user_id, location.character_id)
        for i, chat in enumerate(index["chats"]):
            if chat["id"] == chat_id:
                index["chats"].pop(i)
                await self._save_index(user_id, location.character_id, index)

                session_path = self._get_session_path(user_id, location.character_id, chat_id)

                def _delete(path=session_path):
                    if path.exists():
                        path.unlink()

                await asyncio.to_thread(_delete)
                return
        raise ValueError(f"Chat {chat_id} not found")

    async def append_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """Append message to chat session.

        向聊天会话追加消息。
        """
        location = await self._find_chat_location(chat_id)
        if not location:
            raise ValueError(f"Chat {chat_id} not found")
        return await self.append_message_for_user(
            location.user_id,
            chat_id,
            role,
            content,
            name=name,
            metadata=metadata,
        )

    async def append_message_for_user(
        self,
        user_id: str,
        chat_id: str,
        role: str,
        content: str,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """Append message to a user-scoped chat session.

        向用户范围的聊天会话追加消息。
        """
        location = await self._find_chat_location(chat_id, user_id=user_id)
        if not location:
            raise ValueError(f"Chat {chat_id} not found")

        session_path = self._get_session_path(user_id, location.character_id, chat_id)
        session_data = await self._read_json(session_path)
        if not isinstance(session_data, dict):
            session_data = {"messages": []}

        # Append message
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if name:
            message["name"] = name
        message.update(_clean_message_metadata(metadata))

        session_data["messages"].append(message)
        await self._write_json(session_path, session_data)

        # Update index metadata
        index = await self._load_index(user_id, location.character_id)
        for chat in index["chats"]:
            if chat["id"] == chat_id:
                chat["message_count"] = len(session_data["messages"])
                chat["updated_at"] = message["timestamp"]
                break
        await self._save_index(user_id, location.character_id, index)

        return message

    async def get_messages(
        self,
        chat_id: str,
        limit: int | None = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Get chat message history with pagination.

        分页获取聊天消息历史。
        """
        location = await self._find_chat_location(chat_id)
        if not location:
            raise ValueError(f"Chat {chat_id} not found")
        return await self.get_messages_for_user(
            location.user_id,
            chat_id,
            limit=limit,
            offset=offset,
        )

    async def get_messages_for_user(
        self,
        user_id: str,
        chat_id: str,
        limit: int | None = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Get user-scoped chat message history with pagination.

        分页获取用户范围的聊天消息历史。
        """
        location = await self._find_chat_location(chat_id, user_id=user_id)
        if not location:
            raise ValueError(f"Chat {chat_id} not found")

        session_path = self._get_session_path(user_id, location.character_id, chat_id)
        session_data = await self._read_json(session_path)
        if not isinstance(session_data, dict):
            return []

        messages = session_data.get("messages", [])
        if limit is None:
            return messages[offset:]
        return messages[offset : offset + limit]
