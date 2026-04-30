"""JSON file-based chat storage implementation."""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import NamedTuple

from src.memory._io_utils import atomic_replace
from src.storage.interface import ChatStorageInterface


class _ChatLocation(NamedTuple):
    user_id: str
    character_id: str
    chat: dict


def _validate_path_component(label: str, value: str) -> str:
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


class JSONChatStorage(ChatStorageInterface):
    """JSON file-based chat storage with file system persistence."""

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)

    def _get_user_dir(self, user_id: str, character_id: str) -> Path:
        """Get user-character directory path."""
        safe_user_id = _validate_path_component("user_id", user_id)
        safe_character_id = _validate_path_component("character_id", character_id)
        return self.base_path / safe_user_id / safe_character_id

    def _get_index_path(self, user_id: str, character_id: str) -> Path:
        """Get index.json path."""
        return self._get_user_dir(user_id, character_id) / "index.json"

    def _get_session_path(self, user_id: str, character_id: str, chat_id: str) -> Path:
        """Get session file path."""
        safe_chat_id = _validate_path_component("chat_id", chat_id)
        return self._get_user_dir(user_id, character_id) / "sessions" / f"{safe_chat_id}.json"

    async def _read_json(self, path: Path) -> dict | list | None:
        """Read JSON file asynchronously."""

        def _read():
            if not path.exists():
                return None
            with open(path, encoding="utf-8") as f:
                return json.load(f)

        return await asyncio.to_thread(_read)

    async def _write_json(self, path: Path, data: dict | list) -> None:
        """Write JSON file atomically."""

        def _write():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            atomic_replace(tmp, path)

        await asyncio.to_thread(_write)

    async def _load_index(self, user_id: str, character_id: str) -> dict:
        """Load index.json or return empty structure."""
        index_path = self._get_index_path(user_id, character_id)
        data = await self._read_json(index_path)
        if isinstance(data, dict):
            return data
        return {"chats": []}

    async def _save_index(self, user_id: str, character_id: str, index: dict) -> None:
        """Save index.json atomically."""
        index_path = self._get_index_path(user_id, character_id)
        await self._write_json(index_path, index)

    def _generate_chat_id(self) -> str:
        """Generate chat ID in format: YYYYMMDD_uuid8."""
        date_str = datetime.now(UTC).strftime("%Y%m%d")
        uuid_str = str(uuid.uuid4())[:8]
        return f"{date_str}_{uuid_str}"

    async def _find_chat_location(
        self,
        chat_id: str,
        user_id: str | None = None,
        character_id: str | None = None,
    ) -> _ChatLocation | None:
        """Find a chat location, optionally scoped to one user/character."""
        safe_chat_id = _validate_path_component("chat_id", chat_id)
        safe_user_id = (
            _validate_path_component("user_id", user_id) if user_id is not None else None
        )
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
        """Create a new chat session."""
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
        """List user's chat sessions, sorted by updated_at descending."""
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
        """Get chat metadata by ID (requires scanning all user directories)."""
        location = await self._find_chat_location(chat_id)
        return location.chat if location else None

    async def get_chat_for_user(self, user_id: str, chat_id: str) -> dict | None:
        """Get chat metadata by ID, scoped to a user."""
        location = await self._find_chat_location(chat_id, user_id=user_id)
        return location.chat if location else None

    async def get_chat_for_user_character(
        self, user_id: str, character_id: str, chat_id: str
    ) -> dict | None:
        """Get chat metadata by ID, scoped to one user-character index."""
        location = await self._find_chat_location(
            chat_id,
            user_id=user_id,
            character_id=character_id,
        )
        return location.chat if location else None

    async def update_chat(self, chat_id: str, **kwargs: str) -> dict:
        """Update chat metadata (title, etc.)."""
        location = await self._find_chat_location(chat_id)
        if not location:
            raise ValueError(f"Chat {chat_id} not found")
        return await self.update_chat_for_user(location.user_id, chat_id, **kwargs)

    async def update_chat_for_user(self, user_id: str, chat_id: str, **kwargs: str) -> dict:
        """Update chat metadata for a specific user."""
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
        """Delete chat session."""
        location = await self._find_chat_location(chat_id)
        if not location:
            raise ValueError(f"Chat {chat_id} not found")
        await self.delete_chat_for_user(location.user_id, chat_id)

    async def delete_chat_for_user(self, user_id: str, chat_id: str) -> None:
        """Delete chat session for a specific user."""
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
        self, chat_id: str, role: str, content: str, name: str | None = None
    ) -> dict:
        """Append message to chat session."""
        location = await self._find_chat_location(chat_id)
        if not location:
            raise ValueError(f"Chat {chat_id} not found")
        return await self.append_message_for_user(
            location.user_id,
            chat_id,
            role,
            content,
            name=name,
        )

    async def append_message_for_user(
        self, user_id: str, chat_id: str, role: str, content: str, name: str | None = None
    ) -> dict:
        """Append message to a user-scoped chat session."""
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
        """Get chat message history with pagination."""
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
        """Get user-scoped chat message history with pagination."""
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
