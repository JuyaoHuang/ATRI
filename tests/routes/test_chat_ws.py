"""Executable tests for WebSocket chat endpoint."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from src.app import create_app
from src.routes.chat_ws import (
    WebSocketVADState,
    _handle_audio_chunk,
    _handle_audio_end,
    _handle_text_input,
    _send_asr_transcript,
    _send_json,
    _start_tracked_chat_task,
)
from src.vad import VADConfigStore, VADService

_TEST_VAD_CONFIG_PATH = Path(__file__).with_name("__test_vad_config.yaml")


class CapturingWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


class LockedCapturingWebSocket(CapturingWebSocket):
    def __init__(self) -> None:
        super().__init__()
        self.state = MagicMock()
        self.state.send_lock = asyncio.Lock()


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


async def _mock_delayed_chat_stream(chunks: list[str], delay_seconds: float) -> AsyncIterator[str]:
    await asyncio.sleep(delay_seconds)
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
        app.state.vad_service = VADService(
            VADConfigStore(config.get("vad", {}), path=_TEST_VAD_CONFIG_PATH)
        )
        return app


def _vad_enabled_config(base_config: dict) -> dict:
    return {
        **base_config,
        "vad": {
            "enabled": True,
            "vad_model": "fake",
            "sample_rate": 16000,
            "required_hits": 2,
            "required_misses": 2,
            "fake": {"speech_threshold": 0.5},
        },
    }


@pytest.mark.asyncio
async def test_websocket_vad_state_buffers_and_clears_audio(tmp_path) -> None:
    vad_service = VADService(
        VADConfigStore(
            _vad_enabled_config({})["vad"],
            path=tmp_path / "vad_config.yaml",
        )
    )
    vad_state = WebSocketVADState(session_id="test-session")
    websocket = CapturingWebSocket()

    await _handle_audio_chunk(
        websocket,
        {
            "data": {
                "chat_id": "test_chat_123",
                "character_id": "atri",
                "audio": [0.7, -0.2],
                "seq": 1,
            }
        },
        vad_service,
        vad_state,
    )
    await _handle_audio_chunk(
        websocket,
        {
            "data": {
                "chat_id": "test_chat_123",
                "character_id": "atri",
                "audio": [0.9],
                "seq": 2,
            }
        },
        vad_service,
        vad_state,
    )

    assert vad_state.audio_buffer == [0.7, -0.2, 0.9]

    await _handle_audio_end(
        websocket,
        {
            "data": {
                "chat_id": "test_chat_123",
                "character_id": "atri",
            }
        },
        vad_service,
        vad_state,
    )

    assert vad_state.audio_buffer == []


@pytest.mark.asyncio
async def test_send_json_uses_connection_send_lock() -> None:
    websocket = LockedCapturingWebSocket()

    async with websocket.state.send_lock:
        send_task = asyncio.create_task(_send_json(websocket, {"type": "locked"}))
        await asyncio.sleep(0)
        assert websocket.messages == []

    await send_task

    assert websocket.messages == [{"type": "locked"}]


@pytest.mark.asyncio
async def test_send_asr_transcript_uses_reserved_protocol() -> None:
    websocket = CapturingWebSocket()

    await _send_asr_transcript(
        websocket,
        chat_id="test_chat_123",
        character_id="atri",
        text="你好",
        generation_id="gen-123",
        is_final=True,
        seq=3,
    )

    assert websocket.messages == [
        {
            "type": "output:asr:transcript",
            "data": {
                "chat_id": "test_chat_123",
                "character_id": "atri",
                "text": "你好",
                "generation_id": "gen-123",
                "is_final": True,
                "seq": 3,
            },
        }
    ]


@pytest.mark.asyncio
async def test_start_tracked_chat_task_sets_and_clears_current_task() -> None:
    vad_state = WebSocketVADState(session_id="test-session")
    observed_task: asyncio.Task[None] | None = None

    async def chat_handler() -> None:
        nonlocal observed_task
        observed_task = vad_state.current_chat_task

    started = _start_tracked_chat_task(vad_state, "gen-123", chat_handler())
    task = vad_state.current_chat_task
    assert started is True
    assert task is not None
    assert vad_state.current_generation_id == "gen-123"
    await task
    await asyncio.sleep(0)

    assert isinstance(observed_task, asyncio.Task)
    assert vad_state.current_chat_task is None
    assert vad_state.current_generation_id == "gen-123"


@pytest.mark.asyncio
async def test_start_tracked_chat_task_rejects_concurrent_generation() -> None:
    vad_state = WebSocketVADState(session_id="test-session")
    stop_event = asyncio.Event()

    async def chat_handler() -> None:
        await stop_event.wait()

    first_started = _start_tracked_chat_task(vad_state, "gen-1", chat_handler())
    first_task = vad_state.current_chat_task
    assert first_started is True
    assert first_task is not None
    assert vad_state.current_generation_id == "gen-1"

    second_started = _start_tracked_chat_task(vad_state, "gen-2", chat_handler())
    assert second_started is False
    assert vad_state.current_chat_task is first_task
    assert vad_state.current_generation_id == "gen-1"

    stop_event.set()
    await first_task
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_stale_chat_generation_does_not_complete_or_persist(
    mock_service_context: tuple[MagicMock, MagicMock],
    mock_storage: AsyncMock,
) -> None:
    mock_context, mock_agent = mock_service_context
    websocket = CapturingWebSocket()
    vad_state = WebSocketVADState(session_id="test-session")
    generation_id = "gen-stale"
    vad_state.activate_generation(generation_id)

    async def stream_then_invalidate() -> AsyncIterator[str]:
        yield "旧回复"
        vad_state.invalidate_current_generation()

    mock_agent.chat = MagicMock(side_effect=lambda text: stream_then_invalidate())

    await _handle_text_input(
        websocket,
        {
            "type": "input:text",
            "data": {
                "text": "你好",
                "chat_id": "test_chat_123",
                "character_id": "atri",
            },
        },
        mock_context,
        mock_storage,
        "default",
        vad_state,
        generation_id,
    )

    assert websocket.messages == [
        {
            "type": "output:chat:chunk",
            "data": {
                "chunk": "旧回复",
                "chat_id": "test_chat_123",
                "character_id": "atri",
                "generation_id": generation_id,
            },
        }
    ]
    mock_storage.append_message_for_user.assert_not_called()


@pytest.mark.asyncio
async def test_audio_speech_start_invalidates_current_generation(tmp_path) -> None:
    vad_service = VADService(
        VADConfigStore(
            _vad_enabled_config({})["vad"],
            path=tmp_path / "vad_config.yaml",
        )
    )
    vad_state = WebSocketVADState(session_id="test-session")
    vad_state.activate_generation("gen-old")
    websocket = CapturingWebSocket()

    for seq, audio in ((1, [0.8]), (2, [0.9])):
        await _handle_audio_chunk(
            websocket,
            {
                "data": {
                    "chat_id": "test_chat_123",
                    "character_id": "atri",
                    "audio": audio,
                    "seq": seq,
                }
            },
            vad_service,
            vad_state,
        )

    assert vad_state.current_generation_id is None
    assert websocket.messages[-1]["type"] == "control:interrupt"
    assert websocket.messages[-1]["data"]["reason"] == "speech_start"


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

        generation_id = None
        for chunk in chunks:
            response = websocket.receive_json()
            assert response["type"] == "output:chat:chunk"
            assert response["data"]["chunk"] == chunk
            assert response["data"]["generation_id"]
            generation_id = generation_id or response["data"]["generation_id"]
            assert response["data"]["generation_id"] == generation_id

        complete_response = websocket.receive_json()
        assert complete_response["type"] == "output:chat:complete"
        assert complete_response["data"]["full_reply"] == "".join(chunks)
        assert complete_response["data"]["generation_id"] == generation_id

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
async def test_websocket_handles_audio_while_chat_task_runs(
    mock_config: dict,
    mock_service_context: tuple[MagicMock, MagicMock],
    mock_storage: AsyncMock,
) -> None:
    mock_context, mock_agent = mock_service_context
    mock_agent.chat = MagicMock(side_effect=lambda text: _mock_delayed_chat_stream(["稍后"], 0.2))
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
        websocket.send_json(
            {
                "type": "input:audio:chunk",
                "data": {
                    "chat_id": "test_chat_123",
                    "character_id": "atri",
                    "audio": [0.1],
                    "seq": 9,
                },
            }
        )

        listen_state = websocket.receive_json()
        assert listen_state["type"] == "control:listen-state"
        assert listen_state["data"]["state"] == "silence"
        assert listen_state["data"]["seq"] == 9

        chunk = websocket.receive_json()
        assert chunk["type"] == "output:chat:chunk"
        assert chunk["data"]["chunk"] == "稍后"
        generation_id = chunk["data"]["generation_id"]

        complete = websocket.receive_json()
        assert complete["type"] == "output:chat:complete"
        assert complete["data"]["full_reply"] == "稍后"
        assert complete["data"]["generation_id"] == generation_id


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


@pytest.mark.asyncio
async def test_websocket_audio_chunk_returns_disabled_listen_state(
    mock_config: dict,
    mock_service_context: tuple[MagicMock, MagicMock],
    mock_storage: AsyncMock,
) -> None:
    mock_context, _mock_agent = mock_service_context
    app = _make_app(mock_config, mock_context, mock_storage)

    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json(
            {
                "type": "input:audio:chunk",
                "data": {
                    "chat_id": "test_chat_123",
                    "character_id": "atri",
                    "audio": [0.9, -0.4],
                    "seq": 7,
                },
            }
        )

        response = websocket.receive_json()
        assert response["type"] == "control:listen-state"
        assert response["data"] == {
            "chat_id": "test_chat_123",
            "character_id": "atri",
            "state": "silence",
            "is_speech": False,
            "seq": 7,
            "disabled": True,
        }


@pytest.mark.asyncio
async def test_websocket_audio_chunk_processes_fake_vad_speech_start(
    mock_config: dict,
    mock_service_context: tuple[MagicMock, MagicMock],
    mock_storage: AsyncMock,
) -> None:
    mock_context, _mock_agent = mock_service_context
    app = _make_app(_vad_enabled_config(mock_config), mock_context, mock_storage)

    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json(
            {
                "type": "input:audio:chunk",
                "data": {
                    "chat_id": "test_chat_123",
                    "character_id": "atri",
                    "audio": [0.8],
                    "seq": 1,
                },
            }
        )
        first = websocket.receive_json()

        websocket.send_json(
            {
                "type": "input:audio:chunk",
                "data": {
                    "chat_id": "test_chat_123",
                    "character_id": "atri",
                    "audio": [0.9],
                    "seq": 2,
                },
            }
        )
        second = websocket.receive_json()
        interrupt = websocket.receive_json()

        assert first["type"] == "control:listen-state"
        assert first["data"]["state"] == "silence"
        assert first["data"]["is_speech"] is True
        assert first["data"]["seq"] == 1

        assert second["type"] == "control:listen-state"
        assert second["data"]["state"] == "speech_start"
        assert second["data"]["is_speech"] is True
        assert second["data"]["seq"] == 2
        assert second["data"]["probability"] == 1.0
        assert second["data"]["energy"] == 0.9

        assert interrupt["type"] == "control:interrupt"
        assert interrupt["data"] == {
            "chat_id": "test_chat_123",
            "character_id": "atri",
            "reason": "speech_start",
        }


@pytest.mark.asyncio
async def test_websocket_audio_chunk_sends_interrupt_once_per_speech_turn(
    mock_config: dict,
    mock_service_context: tuple[MagicMock, MagicMock],
    mock_storage: AsyncMock,
) -> None:
    mock_context, _mock_agent = mock_service_context
    app = _make_app(_vad_enabled_config(mock_config), mock_context, mock_storage)

    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        for seq in (1, 2, 3):
            websocket.send_json(
                {
                    "type": "input:audio:chunk",
                    "data": {
                        "chat_id": "test_chat_123",
                        "character_id": "atri",
                        "audio": [0.9],
                        "seq": seq,
                    },
                }
            )
            listen_state = websocket.receive_json()
            assert listen_state["type"] == "control:listen-state"
            assert listen_state["data"]["seq"] == seq
            if seq == 2:
                interrupt = websocket.receive_json()
                assert interrupt["type"] == "control:interrupt"
                assert interrupt["data"]["reason"] == "speech_start"

        websocket.send_json(
            {
                "type": "input:audio:end",
                "data": {
                    "chat_id": "test_chat_123",
                    "character_id": "atri",
                },
            }
        )
        ended = websocket.receive_json()
        assert ended["type"] == "control:listen-state"
        assert ended["data"]["state"] == "speech_end"


@pytest.mark.asyncio
async def test_websocket_audio_end_resets_vad_session(
    mock_config: dict,
    mock_service_context: tuple[MagicMock, MagicMock],
    mock_storage: AsyncMock,
) -> None:
    mock_context, _mock_agent = mock_service_context
    app = _make_app(_vad_enabled_config(mock_config), mock_context, mock_storage)

    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        for seq in (1, 2):
            websocket.send_json(
                {
                    "type": "input:audio:chunk",
                    "data": {
                        "chat_id": "test_chat_123",
                        "character_id": "atri",
                        "audio": [0.9],
                        "seq": seq,
                    },
                }
            )
            response = websocket.receive_json()
            if response["data"]["state"] == "speech_start":
                websocket.receive_json()

        websocket.send_json(
            {
                "type": "input:audio:end",
                "data": {
                    "chat_id": "test_chat_123",
                    "character_id": "atri",
                },
            }
        )
        ended = websocket.receive_json()

        websocket.send_json(
            {
                "type": "input:audio:chunk",
                "data": {
                    "chat_id": "test_chat_123",
                    "character_id": "atri",
                    "audio": [0.9],
                    "seq": 3,
                },
            }
        )
        after_reset = websocket.receive_json()

        assert ended["type"] == "control:listen-state"
        assert ended["data"]["state"] == "speech_end"
        assert ended["data"]["is_speech"] is False

        assert after_reset["type"] == "control:listen-state"
        assert after_reset["data"]["state"] == "silence"
        assert after_reset["data"]["is_speech"] is True
        assert after_reset["data"]["seq"] == 3


@pytest.mark.asyncio
async def test_websocket_audio_chunk_rejects_invalid_audio(
    mock_config: dict,
    mock_service_context: tuple[MagicMock, MagicMock],
    mock_storage: AsyncMock,
) -> None:
    mock_context, _mock_agent = mock_service_context
    app = _make_app(_vad_enabled_config(mock_config), mock_context, mock_storage)

    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json(
            {
                "type": "input:audio:chunk",
                "data": {
                    "chat_id": "test_chat_123",
                    "character_id": "atri",
                    "audio": [],
                },
            }
        )

        response = websocket.receive_json()
        assert response["type"] == "error"
        assert response["data"]["chat_id"] == "test_chat_123"
        assert "Invalid 'audio' field" in response["data"]["message"]
