"""Executable tests for WebSocket chat endpoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from src.app import create_app


@pytest.fixture
def mock_config() -> dict:
    return {
        "server": {
            "cors": {
                "enabled": True,
                "allow_origins": ["*"],
                "allow_methods": ["*"],
                "allow_credentials": True,
            }
        },
        "storage": {"mode": "json", "json": {"base_path": "data/chats"}},
        "auth": {"enabled": False},
        "llm": {},
        "memory": {},
    }


@pytest.fixture
def mock_service_context() -> tuple[MagicMock, MagicMock]:
    mock_agent = MagicMock()
    mock_context = MagicMock()
    mock_context.get_or_create_agent.return_value = mock_agent
    return mock_context, mock_agent


@pytest.fixture
def mock_storage() -> AsyncMock:
    storage = AsyncMock()
    storage.get_chat_for_user_character = AsyncMock(
        return_value={"id": "test_chat_123", "character_id": "atri"}
    )
    storage.append_message_for_user = AsyncMock()
    return storage


async def _mock_chat_stream(chunks: list[str]) -> AsyncIterator[str]:
    for chunk in chunks:
        yield chunk


def _make_app(config: dict, service_context: MagicMock, storage: AsyncMock):
    with (
        patch("src.app.ServiceContext", return_value=service_context),
        patch("src.app.create_chat_storage", return_value=storage),
    ):
        app = create_app(config)
        app.state.service_context = service_context
        app.state.storage = storage
        return app


@pytest.mark.asyncio
async def test_websocket_text_input_streaming(
    mock_config: dict,
    mock_service_context: tuple[MagicMock, MagicMock],
    mock_storage: AsyncMock,
) -> None:
    mock_context, mock_agent = mock_service_context
    chunks = ["你好", "，", "主人", "！"]
    mock_agent.chat = MagicMock(side_effect=lambda text: _mock_chat_stream(chunks))
    app = _make_app(mock_config, mock_context, mock_storage)

    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json(
            {
                "type": "input:text",
                "data": {
                    "text": "你好",
                    "chat_id": "test_chat_123",
                    "character_id": "atri",
                },
            }
        )

        for chunk in chunks:
            response = websocket.receive_json()
            assert response["type"] == "output:chat:chunk"
            assert response["data"]["chunk"] == chunk

        complete_response = websocket.receive_json()
        assert complete_response["type"] == "output:chat:complete"
        assert complete_response["data"]["full_reply"] == "".join(chunks)

    mock_storage.get_chat_for_user_character.assert_awaited_once_with(
        "default", "atri", "test_chat_123"
    )
    mock_context.get_or_create_agent.assert_called_once_with("atri", "default", "test_chat_123")
    mock_storage.append_message_for_user.assert_any_call(
        "default", "test_chat_123", "human", "你好", name="default"
    )
    mock_storage.append_message_for_user.assert_any_call(
        "default", "test_chat_123", "ai", "你好，主人！", name="atri"
    )


@pytest.mark.asyncio
async def test_websocket_rejects_missing_chat(
    mock_config: dict,
    mock_service_context: tuple[MagicMock, MagicMock],
    mock_storage: AsyncMock,
) -> None:
    mock_context, _mock_agent = mock_service_context
    mock_storage.get_chat_for_user_character.return_value = None
    app = _make_app(mock_config, mock_context, mock_storage)

    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json(
            {
                "type": "input:text",
                "data": {
                    "text": "hello",
                    "chat_id": "../outside",
                    "character_id": "atri",
                },
            }
        )

        response = websocket.receive_json()
        assert response["type"] == "error"
        assert "not found" in response["data"]["message"]

    mock_storage.get_chat_for_user_character.assert_awaited_once_with(
        "default", "atri", "../outside"
    )
    mock_context.get_or_create_agent.assert_not_called()
    mock_storage.append_message_for_user.assert_not_called()


@pytest.mark.asyncio
async def test_websocket_rejects_invalid_chat_path(
    mock_config: dict,
    mock_service_context: tuple[MagicMock, MagicMock],
    mock_storage: AsyncMock,
) -> None:
    mock_context, _mock_agent = mock_service_context
    mock_storage.get_chat_for_user_character.side_effect = ValueError(
        "Invalid chat_id: '../outside'"
    )
    app = _make_app(mock_config, mock_context, mock_storage)

    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json(
            {
                "type": "input:text",
                "data": {
                    "text": "hello",
                    "chat_id": "../outside",
                    "character_id": "atri",
                },
            }
        )

        response = websocket.receive_json()
        assert response["type"] == "error"
        assert "Invalid chat request" in response["data"]["message"]

    mock_context.get_or_create_agent.assert_not_called()
    mock_storage.append_message_for_user.assert_not_called()


@pytest.mark.asyncio
async def test_websocket_rejects_character_mismatch(
    mock_config: dict,
    mock_service_context: tuple[MagicMock, MagicMock],
    mock_storage: AsyncMock,
) -> None:
    mock_context, _mock_agent = mock_service_context
    mock_storage.get_chat_for_user_character.return_value = {
        "id": "test_chat_123",
        "character_id": "bilibili",
    }
    app = _make_app(mock_config, mock_context, mock_storage)

    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json(
            {
                "type": "input:text",
                "data": {
                    "text": "hello",
                    "chat_id": "test_chat_123",
                    "character_id": "atri",
                },
            }
        )

        response = websocket.receive_json()
        assert response["type"] == "error"
        assert "not found" in response["data"]["message"]

    mock_context.get_or_create_agent.assert_not_called()
    mock_storage.append_message_for_user.assert_not_called()
