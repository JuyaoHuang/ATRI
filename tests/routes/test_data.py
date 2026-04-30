"""Tests for data maintenance routes."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.app import create_app
from src.memory.manager import MemoryManager
from src.utils.config_loader import load_config


def _test_config(tmp_path: Path) -> dict[str, Any]:
    config = load_config("config.yaml")
    config["memory"]["storage"]["characters_dir"] = str(tmp_path / "characters")
    config["memory"]["mem0"] = {"mode": "sdk", "sdk": {"api_key": "m0-test"}}
    config["storage"] = {"mode": "json", "json": {"base_path": str(tmp_path / "chats")}}
    config["auth"] = {"enabled": False}
    return config


def _make_memory_manager(config: dict[str, Any], chat_id: str = "chat-a") -> MemoryManager:
    return MemoryManager(
        config["memory"],
        lambda _role: AsyncMock(),
        character="atri",
        user_id="default",
        chat_id=chat_id,
        long_term=None,
    )


@pytest.mark.asyncio
async def test_clear_short_term_memory_deletes_user_scoped_file_and_hot_cache(
    tmp_path: Path,
) -> None:
    config = _test_config(tmp_path)
    app = create_app(config)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            await app.state.storage.create_chat("default", "atri", "chat-a")
            chat_id = (await app.state.storage.list_chats("default", "atri"))[0]["id"]
            manager = _make_memory_manager(config, chat_id)
            app.state.service_context._agents[("atri", "default", chat_id)] = SimpleNamespace(
                memory_manager=manager
            )
            assert manager.short_term_store is not None

            manager._state = {
                "session_id": manager.active_session_id,
                "character": "atri",
                "updated_at": "2026-01-01T00:00:00Z",
                "total_rounds": 1,
                "meta_blocks": [],
                "active_blocks": [],
                "recent_messages": [{"role": "human", "content": "old"}],
            }
            manager.short_term_store.save(manager.state)
            assert manager.short_term_store.path.is_file()

            response = await client.delete(
                f"/api/data/characters/atri/chats/{chat_id}/short-term-memory"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["target"] == "short_term_memory"
            assert data["chat_id"] == chat_id
            assert data["details"]["cache_reset"] is True
            assert not manager.short_term_store.path.exists()
            assert manager.state["total_rounds"] == 0
            assert manager.state["recent_messages"] == []


@pytest.mark.asyncio
async def test_clear_short_term_memory_migrates_legacy_file_before_delete(tmp_path: Path) -> None:
    config = _test_config(tmp_path)
    characters_root = Path(config["memory"]["storage"]["characters_dir"])
    legacy_dir = characters_root / "atri"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "short_term_memory.json").write_text(
        json.dumps(
            {
                "session_id": "legacy",
                "character": "atri",
                "total_rounds": 1,
                "meta_blocks": [],
                "active_blocks": [],
                "recent_messages": [],
            }
        ),
        encoding="utf-8",
    )

    app = create_app(config)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            await app.state.storage.create_chat("default", "atri", "chat-a")
            chat_id = (await app.state.storage.list_chats("default", "atri"))[0]["id"]
            response = await client.delete(
                f"/api/data/characters/atri/chats/{chat_id}/short-term-memory"
            )

    assert response.status_code == 200
    chat_scoped_path = (
        characters_root
        / "default"
        / "atri"
        / "chats"
        / chat_id
        / "short_term_memory.json"
    )
    assert not chat_scoped_path.exists()
    assert (legacy_dir / "short_term_memory.json").is_file()
    assert (characters_root / "default" / "atri" / ".legacy_migrated").is_file()


@pytest.mark.asyncio
async def test_clear_short_term_memory_does_not_restore_previously_migrated_legacy(
    tmp_path: Path,
) -> None:
    config = _test_config(tmp_path)
    characters_root = Path(config["memory"]["storage"]["characters_dir"])
    legacy_dir = characters_root / "atri"
    user_dir = characters_root / "default" / "atri"
    legacy_dir.mkdir(parents=True)
    user_dir.mkdir(parents=True)
    (legacy_dir / "short_term_memory.json").write_text(
        json.dumps({"session_id": "legacy"}),
        encoding="utf-8",
    )
    (user_dir / "short_term_memory.json").write_text(
        json.dumps({"session_id": "already-migrated"}),
        encoding="utf-8",
    )

    app = create_app(config)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            await app.state.storage.create_chat("default", "atri", "chat-a")
            chat_id = (await app.state.storage.list_chats("default", "atri"))[0]["id"]
            response = await client.delete(
                f"/api/data/characters/atri/chats/{chat_id}/short-term-memory"
            )
            assert response.status_code == 200

            new_manager = MemoryManager(
                config["memory"],
                lambda _role: AsyncMock(),
                character="atri",
                user_id="default",
                chat_id=chat_id,
                long_term=None,
            )

    assert new_manager.short_term_store is not None
    assert not new_manager.short_term_store.path.exists()


@pytest.mark.asyncio
async def test_clear_short_term_memory_rejects_invalid_chat_path(tmp_path: Path) -> None:
    config = _test_config(tmp_path)
    app = create_app(config)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            response = await client.delete(
                "/api/data/characters/atri/chats/nested%5Coutside/short-term-memory"
            )

    assert response.status_code == 400
    assert "Invalid" in response.json()["detail"]


@pytest.mark.asyncio
async def test_clear_long_term_memory_submits_mem0_delete(tmp_path: Path) -> None:
    config = _test_config(tmp_path)
    app = create_app(config)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            mock_long_term = AsyncMock()
            mock_long_term.delete_all.return_value = {
                "message": "Delete in progress. This may take some time.",
                "event_id": "evt-test",
            }
            mock_long_term.close = lambda: None
            app.state.service_context._long_term_memories[("atri", "default")] = mock_long_term

            response = await client.delete("/api/data/characters/atri/long-term-memory")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "submitted"
            assert data["message"] == "长期记忆删除已提交，可能稍后完成。"
            assert data["details"]["mem0"]["event_id"] == "evt-test"
            mock_long_term.delete_all.assert_awaited_once_with(user_id="default", agent_id="atri")
