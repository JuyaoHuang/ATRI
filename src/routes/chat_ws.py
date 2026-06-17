"""WebSocket endpoint for real-time chat streaming.
WebSocket 实时聊天流式端点。

Bridges ChatAgent streaming output to frontend via WebSocket protocol.
通过 WebSocket 协议桥接 ChatAgent 流式输出到前端。

Message Protocol (参考 airi 事件命名):
消息协议（参考 airi 事件命名）：

Client → Server:
  - {"type": "input:text", "data": {"text": "...", "chat_id": "...",
     "character_id": "..."}}
  - {"type": "ping"}

Server → Client:
  - {"type": "output:chat:chunk", "data": {"chunk": "...", "chat_id": "...",
     "character_id": "..."}}
  - {"type": "output:chat:complete", "data": {"full_reply": "...",
     "chat_id": "...", "character_id": "..."}}
  - {"type": "output:asr:transcript", "data": {"text": "...",
     "chat_id": "...", "character_id": "...", "is_final": true}}
  - {"type": "error", "data": {"message": "...", "chat_id": "..."}}
  - {"type": "pong"}

Reference: docs/Phase5_执行规格.md §US-SRV-006, docs/OLV架构文档.md
"""

import asyncio
import json
import uuid
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger
from starlette.websockets import WebSocketState

from src.auth import get_websocket_user_id
from src.llm.exceptions import LLMError
from src.vad import VADEvent, VADEventType, VADService, VADState


@dataclass
class WebSocketVADState:
    """Per-connection VAD state reserved for realtime audio control."""

    session_id: str
    interrupt_sent: bool = False
    current_chat_task: asyncio.Task[None] | None = None
    audio_buffer: list[float] = field(default_factory=list)
    last_chat_id: str | None = None
    last_character_id: str | None = None

    def append_audio(self, audio: list[float]) -> None:
        """Append a valid speech-like audio chunk to this connection buffer."""

        self.audio_buffer.extend(audio)

    def clear_audio_buffer(self) -> None:
        """Release buffered audio for the current connection turn."""

        self.audio_buffer.clear()

    def release(self) -> None:
        """Release lightweight per-connection references."""

        self.clear_audio_buffer()
        self.current_chat_task = None


async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint handler for chat streaming.
    WebSocket 聊天流式端点处理器。

    Args:
        websocket: FastAPI WebSocket connection.
                   FastAPI WebSocket 连接。
    """
    try:
        user_id = get_websocket_user_id(websocket)
    except Exception as exc:
        logger.warning(f"WebSocket authentication failed: {exc}")
        await websocket.close(code=1008)
        return

    await websocket.accept()
    logger.info("WebSocket connection established")

    # Access app state (ServiceContext + Storage)
    # 访问 app state（ServiceContext + Storage）
    service_context = websocket.app.state.service_context
    storage = websocket.app.state.storage
    vad_service = websocket.app.state.vad_service
    vad_state = WebSocketVADState(session_id=f"ws:{uuid.uuid4().hex}")

    try:
        while True:
            # Receive message from client
            # 接收客户端消息
            raw_message = await websocket.receive_text()

            # Parse JSON
            # 解析 JSON
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON received: {e}")
                await _send_error(websocket, "Invalid JSON format", chat_id=None)
                continue

            # Extract message type
            # 提取消息类型
            msg_type = message.get("type")
            if not msg_type:
                logger.warning("Message missing 'type' field")
                await _send_error(websocket, "Message missing 'type' field", chat_id=None)
                continue

            # Route message by type
            # 按类型路由消息
            if msg_type == "ping":
                await _handle_ping(websocket)
            elif msg_type == "input:text":
                await _run_tracked_chat_task(
                    vad_state,
                    _handle_text_input(websocket, message, service_context, storage, user_id),
                )
            elif msg_type == "input:audio:chunk":
                await _handle_audio_chunk(websocket, message, vad_service, vad_state)
            elif msg_type == "input:audio:end":
                await _handle_audio_end(websocket, message, vad_service, vad_state)
            else:
                logger.warning(f"Unknown message type: {msg_type}")
                await _send_error(
                    websocket,
                    f"Unknown message type: {msg_type}",
                    chat_id=message.get("data", {}).get("chat_id"),
                )

    except WebSocketDisconnect:
        logger.info("WebSocket connection closed by client")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await _send_error(websocket, f"Internal server error: {e}", chat_id=None)
        except Exception:
            pass  # Connection already closed
    finally:
        vad_state.release()
        vad_service.reset_session(vad_state.session_id)
        logger.info("WebSocket connection cleanup complete")


async def _handle_ping(websocket: WebSocket) -> None:
    """Handle ping message (heartbeat).
    处理 ping 消息（心跳）。

    Args:
        websocket: WebSocket connection.
                   WebSocket 连接。
    """
    await websocket.send_json({"type": "pong"})


async def _run_tracked_chat_task(
    vad_state: WebSocketVADState,
    chat_coro: Coroutine[Any, Any, None],
) -> None:
    """Run one chat coroutine while exposing its task on the connection state."""

    task = asyncio.create_task(chat_coro)
    vad_state.current_chat_task = task
    try:
        await task
    finally:
        if vad_state.current_chat_task is task:
            vad_state.current_chat_task = None


async def _handle_text_input(
    websocket: WebSocket,
    message: dict[str, Any],
    service_context: Any,
    storage: Any,
    user_id: str,
) -> None:
    """Handle text input message and stream ChatAgent response.
    处理文本输入消息并流式传输 ChatAgent 响应。

    Args:
        websocket: WebSocket connection.
                   WebSocket 连接。
        message: Parsed message dict with 'data' field.
                 解析后的消息字典，含 'data' 字段。
        service_context: ServiceContext instance from app.state.
                         来自 app.state 的 ServiceContext 实例。
        storage: ChatStorage instance from app.state.
                 来自 app.state 的 ChatStorage 实例。
    """
    data = message.get("data", {})
    text = data.get("text")
    chat_id = data.get("chat_id")
    character_id = data.get("character_id")
    client_context = data.get("client_context")
    if not isinstance(client_context, dict):
        client_context = None

    # Validate required fields
    # 验证必填字段
    if not text:
        await _send_error(websocket, "Missing 'text' field", chat_id=chat_id)
        return
    if not chat_id:
        await _send_error(websocket, "Missing 'chat_id' field", chat_id=None)
        return
    if not character_id:
        await _send_error(websocket, "Missing 'character_id' field", chat_id=chat_id)
        return

    logger.info(f"Received text input | chat_id={chat_id} | character_id={character_id}")

    try:
        chat = await storage.get_chat_for_user_character(user_id, character_id, chat_id)
    except ValueError as exc:
        logger.warning(
            "Rejected invalid chat input | user_id={} | chat_id={} | character_id={} | error={!r}",
            user_id,
            chat_id,
            character_id,
            exc,
        )
        await _send_error(websocket, f"Invalid chat request: {exc}", chat_id=chat_id)
        return

    if chat is None or chat.get("character_id") != character_id:
        logger.warning(
            "Rejected chat input for mismatched chat | user_id={} | chat_id={} | character_id={}",
            user_id,
            chat_id,
            character_id,
        )
        await _send_error(
            websocket,
            f"Chat '{chat_id}' not found for character '{character_id}'",
            chat_id=chat_id,
        )
        return

    # Get or create ChatAgent for this character/user/chat.
    # 获取或创建此 character/user/chat 的 ChatAgent。
    try:
        agent = service_context.get_or_create_agent(character_id, user_id, chat_id)
    except Exception as e:
        logger.error(f"Failed to get ChatAgent: {e}")
        await _send_error(
            websocket,
            f"Failed to initialize character '{character_id}': {e}",
            chat_id=chat_id,
        )
        return

    # Stream ChatAgent response
    # 流式传输 ChatAgent 响应
    chunks = []
    try:
        chat_stream = (
            agent.chat(text, runtime_context=client_context) if client_context else agent.chat(text)
        )
        async for chunk in chat_stream:
            chunks.append(chunk)
            # Send chunk to client
            # 发送 chunk 给客户端
            await websocket.send_json(
                {
                    "type": "output:chat:chunk",
                    "data": {
                        "chunk": chunk,
                        "chat_id": chat_id,
                        "character_id": character_id,
                    },
                }
            )

        # Stream complete
        # 流式传输完成
        full_reply = "".join(chunks)

        # Persist messages to storage BEFORE sending complete event
        # 在发送完成事件之前持久化消息到存储
        # This ensures messages are saved before client closes connection
        # 这确保在客户端关闭连接前消息已保存
        try:
            logger.debug(f"Starting message persistence | chat_id={chat_id}")
            await storage.append_message_for_user(user_id, chat_id, "human", text, name=user_id)
            await storage.append_message_for_user(
                user_id,
                chat_id,
                "ai",
                full_reply,
                name=character_id,
            )
            logger.debug(f"Messages persisted | chat_id={chat_id}")
        except ValueError as e:
            # Chat not found (client may have deleted it)
            # 聊天不存在（客户端可能已删除）
            logger.warning(f"Failed to persist messages: {e}")
        except Exception as e:
            logger.error(f"Unexpected error persisting messages: {e}")

        # Now send complete event
        # 现在发送完成事件
        await websocket.send_json(
            {
                "type": "output:chat:complete",
                "data": {
                    "full_reply": full_reply,
                    "chat_id": chat_id,
                    "character_id": character_id,
                },
            }
        )

        logger.info(f"Chat complete | chat_id={chat_id} | reply_length={len(full_reply)}")

    except LLMError as e:
        # LLM error path (already handled by ChatAgent, but catch here for safety)
        # LLM 错误路径（ChatAgent 已处理，但此处捕获以确保安全）
        logger.error(f"LLM error during chat: {e}")
        await _send_error(
            websocket,
            f"LLM call failed: {e}",
            chat_id=chat_id,
        )
    except Exception as e:
        logger.error(f"Unexpected error during chat: {e}")
        await _send_error(
            websocket,
            f"Chat processing failed: {e}",
            chat_id=chat_id,
        )


async def _handle_audio_chunk(
    websocket: WebSocket,
    message: dict[str, Any],
    vad_service: VADService,
    vad_state: WebSocketVADState,
) -> None:
    """Handle realtime microphone audio chunks for backend VAD."""

    data = message.get("data", {})
    if not isinstance(data, dict):
        await _send_error(websocket, "Message 'data' must be an object", chat_id=None)
        return

    chat_id = data.get("chat_id")
    character_id = data.get("character_id")
    if not chat_id:
        await _send_error(websocket, "Missing 'chat_id' field", chat_id=None)
        return
    if not character_id:
        await _send_error(websocket, "Missing 'character_id' field", chat_id=chat_id)
        return

    audio_samples = _coerce_audio_array(data.get("audio"))
    if audio_samples is None:
        await _send_error(
            websocket,
            "Invalid 'audio' field; expected a non-empty number[]",
            chat_id=chat_id,
        )
        return

    vad_state.last_chat_id = str(chat_id)
    vad_state.last_character_id = str(character_id)

    event = await vad_service.process_audio(vad_state.session_id, audio_samples)
    if event.is_speech and event.metadata.get("disabled") is not True:
        vad_state.append_audio(audio_samples)
    if event.type is VADEventType.SPEECH_END:
        vad_state.interrupt_sent = False
        vad_state.clear_audio_buffer()
    await _send_listen_state(
        websocket,
        event,
        chat_id=str(chat_id),
        character_id=str(character_id),
        seq=data.get("seq"),
    )
    if event.type is VADEventType.SPEECH_START and not vad_state.interrupt_sent:
        vad_state.interrupt_sent = True
        await _send_interrupt(
            websocket,
            chat_id=str(chat_id),
            character_id=str(character_id),
            reason="speech_start",
        )


async def _handle_audio_end(
    websocket: WebSocket,
    message: dict[str, Any],
    vad_service: VADService,
    vad_state: WebSocketVADState,
) -> None:
    """Handle the end of one realtime microphone input turn."""

    data = message.get("data", {})
    if not isinstance(data, dict):
        await _send_error(websocket, "Message 'data' must be an object", chat_id=None)
        return

    chat_id = data.get("chat_id") or vad_state.last_chat_id
    character_id = data.get("character_id") or vad_state.last_character_id
    if not chat_id:
        await _send_error(websocket, "Missing 'chat_id' field", chat_id=None)
        return
    if not character_id:
        await _send_error(websocket, "Missing 'character_id' field", chat_id=str(chat_id))
        return

    vad_service.reset_session(vad_state.session_id)
    vad_state.interrupt_sent = False
    vad_state.clear_audio_buffer()
    vad_state.last_chat_id = str(chat_id)
    vad_state.last_character_id = str(character_id)

    await _send_listen_state(
        websocket,
        VADEvent(
            type=VADEventType.SPEECH_END,
            state=VADState.IDLE,
            is_speech=False,
        ),
        chat_id=str(chat_id),
        character_id=str(character_id),
        seq=data.get("seq"),
    )


def _coerce_audio_array(audio: Any) -> list[float] | None:
    if not isinstance(audio, list) or not audio:
        return None

    samples: list[float] = []
    for sample in audio:
        if not isinstance(sample, int | float) or isinstance(sample, bool):
            return None
        samples.append(float(sample))
    return samples


async def _send_listen_state(
    websocket: WebSocket,
    event: VADEvent,
    *,
    chat_id: str,
    character_id: str,
    seq: Any | None = None,
) -> None:
    """Send a control:listen-state message to the frontend."""

    data: dict[str, Any] = {
        "chat_id": chat_id,
        "character_id": character_id,
        "state": event.type.value,
        "is_speech": event.is_speech,
    }
    if isinstance(seq, int) and not isinstance(seq, bool):
        data["seq"] = seq
    if event.probability is not None:
        data["probability"] = event.probability
    if event.energy is not None:
        data["energy"] = event.energy
    if event.metadata.get("disabled") is True:
        data["disabled"] = True
    if event.type is VADEventType.ERROR and event.metadata.get("reason"):
        data["reason"] = str(event.metadata["reason"])

    await websocket.send_json({"type": "control:listen-state", "data": data})


async def _send_interrupt(
    websocket: WebSocket,
    *,
    chat_id: str,
    character_id: str,
    reason: str,
) -> None:
    """Send a control:interrupt message to the frontend."""

    await websocket.send_json(
        {
            "type": "control:interrupt",
            "data": {
                "chat_id": chat_id,
                "character_id": character_id,
                "reason": reason,
            },
        }
    )


async def _send_asr_transcript(
    websocket: WebSocket,
    *,
    chat_id: str,
    character_id: str,
    text: str,
    is_final: bool = True,
    seq: Any | None = None,
) -> None:
    """Send an output:asr:transcript message reserved for M4 ASR handoff."""

    data: dict[str, Any] = {
        "chat_id": chat_id,
        "character_id": character_id,
        "text": text,
        "is_final": is_final,
    }
    if isinstance(seq, int) and not isinstance(seq, bool):
        data["seq"] = seq

    await websocket.send_json({"type": "output:asr:transcript", "data": data})


async def _send_error(websocket: WebSocket, message: str, chat_id: str | None) -> None:
    """Send error message to client.
    向客户端发送错误消息。

    Args:
        websocket: WebSocket connection.
                   WebSocket 连接。
        message: Error message.
                 错误消息。
        chat_id: Optional chat ID for context.
                 可选的聊天 ID（用于上下文）。
    """
    error_data: dict[str, Any] = {"message": message}
    if chat_id:
        error_data["chat_id"] = chat_id

    await websocket.send_json({"type": "error", "data": error_data})
