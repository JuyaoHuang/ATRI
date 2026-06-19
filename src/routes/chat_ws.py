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
     "character_id": "...", "generation_id": "..."}}
  - {"type": "output:chat:complete", "data": {"full_reply": "...",
      "chat_id": "...", "character_id": "...", "generation_id": "..."}}
  - {"type": "output:chat:interrupted", "data": {"partial_reply": "...",
     "chat_id": "...", "character_id": "...", "generation_id": "...",
     "interrupted": true, "reason": "vad_speech_start"}}
  - {"type": "output:asr:transcript", "data": {"text": "...",
     "chat_id": "...", "character_id": "...", "generation_id": "...",
     "is_final": true}}
  - {"type": "error", "data": {"message": "...", "chat_id": "..."}}
  - {"type": "pong"}

Reference: docs/Phase5_执行规格.md §US-SRV-006, docs/OLV架构文档.md
"""

import asyncio
import io
import json
import uuid
import wave
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger
from starlette.websockets import WebSocketState

from src.asr.exceptions import ASRConfigError, ASRProviderUnavailableError, ASRTranscriptionError
from src.auth import get_websocket_user_id
from src.llm.exceptions import LLMError
from src.vad import VADEvent, VADEventType, VADService, VADState
from src.vad.exceptions import VADConfigError, VADProcessingError, VADProviderUnavailableError


@dataclass(frozen=True)
class InterruptedGenerationSnapshot:
    """Already emitted text for a generation that VAD interrupted."""

    generation_id: str
    chat_id: str
    character_id: str
    user_text: str
    partial_reply: str
    reason: str


@dataclass
class WebSocketVADState:
    """Per-connection VAD state reserved for realtime audio control."""

    session_id: str
    interrupt_sent: bool = False
    current_chat_task: asyncio.Task[None] | None = None
    current_generation_id: str | None = None
    current_generation_chat_id: str | None = None
    current_generation_character_id: str | None = None
    current_generation_user_text: str | None = None
    current_generation_reply_chunks: list[str] = field(default_factory=list)
    audio_buffer: list[float] = field(default_factory=list)
    pre_buffer: list[float] = field(default_factory=list)
    last_chat_id: str | None = None
    last_character_id: str | None = None

    def activate_generation(self, generation_id: str) -> None:
        """Mark a chat generation as the only valid one for this connection."""

        self.current_generation_id = generation_id
        self.current_generation_chat_id = None
        self.current_generation_character_id = None
        self.current_generation_user_text = None
        self.current_generation_reply_chunks.clear()

    def set_generation_context(
        self,
        generation_id: str,
        *,
        chat_id: str,
        character_id: str,
        user_text: str,
    ) -> None:
        """Attach routing and user text metadata to the active generation."""

        if not self.is_generation_active(generation_id):
            return
        self.current_generation_chat_id = chat_id
        self.current_generation_character_id = character_id
        self.current_generation_user_text = user_text

    def append_generation_reply(self, generation_id: str, chunk: str) -> None:
        """Record a chunk only after it has been sent to the frontend."""

        if not self.is_generation_active(generation_id):
            return
        self.current_generation_reply_chunks.append(chunk)

    def is_generation_active(self, generation_id: str) -> bool:
        """Return whether a chat generation can still emit side effects."""

        return self.current_generation_id == generation_id

    def get_interrupted_generation(
        self,
        *,
        reason: str,
    ) -> InterruptedGenerationSnapshot | None:
        """Return the current generation's emitted partial reply, if any."""

        generation_id = self.current_generation_id
        chat_id = self.current_generation_chat_id
        character_id = self.current_generation_character_id
        user_text = self.current_generation_user_text
        partial_reply = "".join(self.current_generation_reply_chunks)
        if not generation_id or not chat_id or not character_id or not user_text:
            return None
        if not partial_reply.strip():
            return None
        return InterruptedGenerationSnapshot(
            generation_id=generation_id,
            chat_id=chat_id,
            character_id=character_id,
            user_text=user_text,
            partial_reply=partial_reply,
            reason=reason,
        )

    def invalidate_current_generation(self) -> str | None:
        """Mark the current generation invalid and return its previous id."""

        generation_id = self.current_generation_id
        self.current_generation_id = None
        self.current_generation_chat_id = None
        self.current_generation_character_id = None
        self.current_generation_user_text = None
        self.current_generation_reply_chunks.clear()
        return generation_id

    def complete_generation(self, generation_id: str) -> None:
        """Release partial-reply tracking for a normally completed generation."""

        if self.is_generation_active(generation_id):
            self.invalidate_current_generation()

    def cancel_current_chat_task(self) -> bool:
        """Cancel the active chat task if it is still running."""

        task = self.current_chat_task
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def append_audio(self, audio: list[float]) -> None:
        """Append a valid speech-like audio chunk to this connection buffer."""

        self.audio_buffer.extend(audio)

    def append_pre_buffer(
        self,
        audio: list[float],
        *,
        sample_rate: int,
        pre_buffer_ms: int,
    ) -> None:
        """Keep a bounded rolling audio buffer before speech_start."""

        if pre_buffer_ms <= 0:
            self.pre_buffer.clear()
            return

        self.pre_buffer.extend(audio)
        max_samples = max(1, int(sample_rate * pre_buffer_ms / 1000))
        overflow = len(self.pre_buffer) - max_samples
        if overflow > 0:
            del self.pre_buffer[:overflow]

    def start_audio_buffer_from_pre_buffer(self, fallback_audio: list[float]) -> None:
        """Begin a speech segment with pre-buffered audio or the current chunk."""

        if self.pre_buffer:
            self.audio_buffer.extend(self.pre_buffer)
        else:
            self.audio_buffer.extend(fallback_audio)
        self.clear_pre_buffer()

    def clear_pre_buffer(self) -> None:
        """Release pre-speech audio for the current connection turn."""

        self.pre_buffer.clear()

    def clear_audio_buffer(self) -> None:
        """Release buffered audio for the current connection turn."""

        self.audio_buffer.clear()

    def consume_audio_buffer(self) -> list[float]:
        """Return and clear the buffered speech audio for this connection."""

        audio = list(self.audio_buffer)
        self.clear_audio_buffer()
        return audio

    def release(self) -> None:
        """Release lightweight per-connection references."""

        self.clear_audio_buffer()
        self.clear_pre_buffer()
        self.current_chat_task = None
        self.invalidate_current_generation()


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
    websocket.state.send_lock = asyncio.Lock()
    logger.info("WebSocket connection established")

    # Access app state (ServiceContext + Storage)
    # 访问 app state（ServiceContext + Storage）
    service_context = websocket.app.state.service_context
    storage = websocket.app.state.storage
    vad_service = websocket.app.state.vad_service
    asr_service = websocket.app.state.asr_service
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
                generation_id = uuid.uuid4().hex
                started = _start_tracked_chat_task(
                    vad_state,
                    generation_id,
                    _handle_text_input(
                        websocket,
                        message,
                        service_context,
                        storage,
                        user_id,
                        vad_state,
                        generation_id,
                    ),
                )
                if not started:
                    await _send_error(
                        websocket,
                        "Chat task already running",
                        chat_id=message.get("data", {}).get("chat_id"),
                    )
            elif msg_type == "input:audio:chunk":
                await _handle_audio_chunk(
                    websocket,
                    message,
                    vad_service,
                    vad_state,
                    asr_service,
                    service_context=service_context,
                    storage=storage,
                    user_id=user_id,
                )
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
    await _send_json(websocket, {"type": "pong"})


async def _send_json(websocket: Any, message: dict[str, Any]) -> None:
    """Serialize WebSocket writes for concurrent chat and control tasks."""

    send_lock = _get_send_lock(websocket)
    if send_lock is None:
        await websocket.send_json(message)
        return

    async with send_lock:
        await websocket.send_json(message)


def _get_send_lock(websocket: Any) -> Any | None:
    """Return the per-connection send lock when the websocket provides one."""

    websocket_state = getattr(websocket, "state", None)
    return getattr(websocket_state, "send_lock", None)


async def _send_generation_chunk(
    websocket: Any,
    vad_state: WebSocketVADState,
    generation_id: str,
    message: dict[str, Any],
    chunk: str,
) -> bool:
    """Send a chunk only if its generation is still active at send time."""

    send_lock = _get_send_lock(websocket)
    if send_lock is None:
        if not vad_state.is_generation_active(generation_id):
            return False
        await websocket.send_json(message)
        vad_state.append_generation_reply(generation_id, chunk)
        return True

    async with send_lock:
        if not vad_state.is_generation_active(generation_id):
            return False
        await websocket.send_json(message)
        vad_state.append_generation_reply(generation_id, chunk)
        return True


async def _send_generation_complete(
    websocket: Any,
    vad_state: WebSocketVADState,
    generation_id: str,
    message: dict[str, Any],
) -> bool:
    """Send a completion only if its generation is still active."""

    send_lock = _get_send_lock(websocket)
    if send_lock is None:
        if not vad_state.is_generation_active(generation_id):
            return False
        await websocket.send_json(message)
        return True

    async with send_lock:
        if not vad_state.is_generation_active(generation_id):
            return False
        await websocket.send_json(message)
        return True


async def _send_speech_start_interrupt(
    websocket: Any,
    vad_state: WebSocketVADState,
    *,
    chat_id: str,
    character_id: str,
) -> tuple[InterruptedGenerationSnapshot | None, str | None, bool]:
    """Atomically invalidate the active generation and send interrupt control."""

    send_lock = _get_send_lock(websocket)
    if send_lock is None:
        return await _send_speech_start_interrupt_unlocked(
            websocket,
            vad_state,
            chat_id=chat_id,
            character_id=character_id,
        )

    async with send_lock:
        return await _send_speech_start_interrupt_unlocked(
            websocket,
            vad_state,
            chat_id=chat_id,
            character_id=character_id,
        )


async def _send_speech_start_interrupt_unlocked(
    websocket: Any,
    vad_state: WebSocketVADState,
    *,
    chat_id: str,
    character_id: str,
) -> tuple[InterruptedGenerationSnapshot | None, str | None, bool]:
    interrupted_snapshot = vad_state.get_interrupted_generation(reason="vad_speech_start")
    stale_generation_id = vad_state.invalidate_current_generation()
    cancelled = vad_state.cancel_current_chat_task()

    data: dict[str, Any] = {
        "chat_id": chat_id,
        "character_id": character_id,
        "reason": "speech_start",
    }
    if stale_generation_id is not None:
        data["generation_id"] = stale_generation_id

    await websocket.send_json(
        {
            "type": "control:interrupt",
            "data": data,
        }
    )
    return interrupted_snapshot, stale_generation_id, cancelled


def _start_tracked_chat_task(
    vad_state: WebSocketVADState,
    generation_id: str,
    chat_coro: Coroutine[Any, Any, None],
) -> bool:
    """Start one chat coroutine while exposing its task on the connection state."""

    current_task = vad_state.current_chat_task
    if current_task is not None and not current_task.done():
        chat_coro.close()
        return False
    vad_state.activate_generation(generation_id)
    task = asyncio.create_task(chat_coro)
    vad_state.current_chat_task = task
    task.add_done_callback(lambda completed: _finalize_tracked_chat_task(vad_state, completed))
    return True


def _finalize_tracked_chat_task(
    vad_state: WebSocketVADState,
    task: asyncio.Task[None],
) -> None:
    """Clear a completed chat task reference and consume terminal exceptions."""

    if vad_state.current_chat_task is task:
        vad_state.current_chat_task = None
    try:
        task.result()
    except asyncio.CancelledError:
        logger.debug("Tracked chat task cancelled")
    except Exception as exc:
        logger.error(f"Tracked chat task failed: {exc}")


def _discard_generation_if_active(vad_state: WebSocketVADState, generation_id: str) -> None:
    """Invalidate a generation only if it is still the connection's active one."""

    if vad_state.is_generation_active(generation_id):
        vad_state.invalidate_current_generation()


def _interrupted_metadata(snapshot: InterruptedGenerationSnapshot) -> dict[str, Any]:
    return {
        "generation_id": snapshot.generation_id,
        "interrupted": True,
        "interrupt_reason": snapshot.reason,
    }


async def _persist_interrupted_generation(
    snapshot: InterruptedGenerationSnapshot,
    *,
    service_context: Any | None,
    storage: Any | None,
    user_id: str | None,
) -> None:
    """Persist an interrupted partial reply for display and memory audit."""

    if user_id is None:
        return

    metadata = _interrupted_metadata(snapshot)
    if storage is not None:
        try:
            await storage.append_message_for_user(
                user_id,
                snapshot.chat_id,
                "human",
                snapshot.user_text,
                name=user_id,
            )
            await storage.append_message_for_user(
                user_id,
                snapshot.chat_id,
                "ai",
                snapshot.partial_reply,
                name=snapshot.character_id,
                metadata=metadata,
            )
        except Exception as exc:
            logger.warning(
                "Failed to persist interrupted chat message | chat_id={} | "
                "generation_id={} | error={!r}",
                snapshot.chat_id,
                snapshot.generation_id,
                exc,
            )

    if service_context is None:
        return

    try:
        agent = service_context.get_or_create_agent(
            snapshot.character_id,
            user_id,
            snapshot.chat_id,
        )
        ai_name = snapshot.character_id
        persona_name = getattr(getattr(agent, "persona", None), "name", None)
        if isinstance(persona_name, str) and persona_name.strip():
            ai_name = persona_name
        await agent.memory_manager.on_round_complete(
            {"role": "human", "content": snapshot.user_text, "name": user_id},
            {
                "role": "ai",
                "content": snapshot.partial_reply,
                "name": ai_name,
                **metadata,
            },
        )
    except Exception as exc:
        logger.warning(
            "Failed to persist interrupted memory history | chat_id={} | "
            "generation_id={} | error={!r}",
            snapshot.chat_id,
            snapshot.generation_id,
            exc,
        )


async def _handle_text_input(
    websocket: WebSocket,
    message: dict[str, Any],
    service_context: Any,
    storage: Any,
    user_id: str,
    vad_state: WebSocketVADState,
    generation_id: str,
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
        _discard_generation_if_active(vad_state, generation_id)
        return
    if not chat_id:
        await _send_error(websocket, "Missing 'chat_id' field", chat_id=None)
        _discard_generation_if_active(vad_state, generation_id)
        return
    if not character_id:
        await _send_error(websocket, "Missing 'character_id' field", chat_id=chat_id)
        _discard_generation_if_active(vad_state, generation_id)
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
        _discard_generation_if_active(vad_state, generation_id)
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
        _discard_generation_if_active(vad_state, generation_id)
        return

    vad_state.set_generation_context(
        generation_id,
        chat_id=str(chat_id),
        character_id=str(character_id),
        user_text=str(text),
    )

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
        _discard_generation_if_active(vad_state, generation_id)
        return

    # Stream ChatAgent response
    # 流式传输 ChatAgent 响应
    chunks = []
    try:
        chat_stream = (
            agent.chat(text, runtime_context=client_context, commit_round=False)
            if client_context
            else agent.chat(text, commit_round=False)
        )
        async for chunk in chat_stream:
            if not vad_state.is_generation_active(generation_id):
                logger.info(
                    "Discarding stale chat chunk | chat_id={} | generation_id={}",
                    chat_id,
                    generation_id,
                )
                return
            chunks.append(chunk)
            # Send chunk to client
            # 发送 chunk 给客户端
            sent = await _send_generation_chunk(
                websocket,
                vad_state,
                generation_id,
                {
                    "type": "output:chat:chunk",
                    "data": {
                        "chunk": chunk,
                        "chat_id": chat_id,
                        "character_id": character_id,
                        "generation_id": generation_id,
                    },
                },
                chunk,
            )
            if not sent:
                logger.info(
                    "Discarding stale chat chunk before send | chat_id={} | generation_id={}",
                    chat_id,
                    generation_id,
                )
                return

        if not vad_state.is_generation_active(generation_id):
            logger.info(
                "Discarding stale chat completion | chat_id={} | generation_id={}",
                chat_id,
                generation_id,
            )
            return

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
            if not vad_state.is_generation_active(generation_id):
                logger.info(
                    "Discarding stale chat completion after human persistence | "
                    "chat_id={} | generation_id={}",
                    chat_id,
                    generation_id,
                )
                return
            await storage.append_message_for_user(
                user_id,
                chat_id,
                "ai",
                full_reply,
                name=character_id,
            )
            if not vad_state.is_generation_active(generation_id):
                logger.info(
                    "Discarding stale chat completion after ai persistence | "
                    "chat_id={} | generation_id={}",
                    chat_id,
                    generation_id,
                )
                return
            logger.debug(f"Messages persisted | chat_id={chat_id}")
        except ValueError as e:
            # Chat not found (client may have deleted it)
            # 聊天不存在（客户端可能已删除）
            logger.warning(f"Failed to persist messages: {e}")
        except Exception as e:
            logger.error(f"Unexpected error persisting messages: {e}")

        ai_name = character_id
        persona_name = getattr(getattr(agent, "persona", None), "name", None)
        if isinstance(persona_name, str) and persona_name.strip():
            ai_name = persona_name
        await agent.memory_manager.on_round_complete(
            {"role": "human", "content": str(text), "name": user_id},
            {"role": "ai", "content": full_reply, "name": ai_name},
        )
        if not vad_state.is_generation_active(generation_id):
            logger.info(
                "Discarding stale chat completion after memory commit | "
                "chat_id={} | generation_id={}",
                chat_id,
                generation_id,
            )
            return

        # Now send complete event
        # 现在发送完成事件
        sent = await _send_generation_complete(
            websocket,
            vad_state,
            generation_id,
            {
                "type": "output:chat:complete",
                "data": {
                    "full_reply": full_reply,
                    "chat_id": chat_id,
                    "character_id": character_id,
                    "generation_id": generation_id,
                },
            },
        )
        if not sent:
            logger.info(
                "Discarding stale chat completion before send | chat_id={} | generation_id={}",
                chat_id,
                generation_id,
            )
            return
        vad_state.complete_generation(generation_id)

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
        _discard_generation_if_active(vad_state, generation_id)
    except Exception as e:
        logger.error(f"Unexpected error during chat: {e}")
        await _send_error(
            websocket,
            f"Chat processing failed: {e}",
            chat_id=chat_id,
        )
        _discard_generation_if_active(vad_state, generation_id)


async def _handle_audio_chunk(
    websocket: WebSocket,
    message: dict[str, Any],
    vad_service: VADService,
    vad_state: WebSocketVADState,
    asr_service: Any | None = None,
    service_context: Any | None = None,
    storage: Any | None = None,
    user_id: str | None = None,
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

    sample_rate = _get_vad_sample_rate(vad_service)
    vad_state.append_pre_buffer(
        audio_samples,
        sample_rate=sample_rate,
        pre_buffer_ms=_get_vad_pre_buffer_ms(vad_service),
    )

    try:
        event = await vad_service.process_audio(vad_state.session_id, audio_samples)
    except (VADProviderUnavailableError, VADConfigError, VADProcessingError) as exc:
        await _handle_vad_audio_error(
            websocket,
            vad_service,
            vad_state,
            exc,
            chat_id=str(chat_id),
            character_id=str(character_id),
            seq=data.get("seq"),
        )
        return
    except Exception as exc:
        logger.exception("Unexpected VAD processing error during realtime audio handling")
        await _handle_vad_audio_error(
            websocket,
            vad_service,
            vad_state,
            exc,
            chat_id=str(chat_id),
            character_id=str(character_id),
            seq=data.get("seq"),
        )
        return
    speech_audio: list[float] | None = None
    if event.metadata.get("disabled") is True:
        vad_state.clear_pre_buffer()
    elif event.type is VADEventType.SPEECH_START:
        vad_state.start_audio_buffer_from_pre_buffer(audio_samples)
    elif event.type is VADEventType.SPEECH_CHUNK:
        vad_state.append_audio(audio_samples)
    elif event.type is VADEventType.SPEECH_END:
        vad_state.clear_pre_buffer()

    if event.type is VADEventType.SPEECH_END:
        vad_state.interrupt_sent = False
        speech_audio = vad_state.consume_audio_buffer()
    await _send_listen_state(
        websocket,
        event,
        chat_id=str(chat_id),
        character_id=str(character_id),
        seq=data.get("seq"),
    )
    if event.type is VADEventType.SPEECH_START and not vad_state.interrupt_sent:
        vad_state.interrupt_sent = True
        (
            interrupted_snapshot,
            stale_generation_id,
            cancelled_chat_task,
        ) = await _send_speech_start_interrupt(
            websocket,
            vad_state,
            chat_id=str(chat_id),
            character_id=str(character_id),
        )
        if stale_generation_id is not None:
            logger.info(
                "Invalidated chat generation on speech_start | chat_id={} | generation_id={}",
                chat_id,
                stale_generation_id,
            )
        if cancelled_chat_task:
            logger.info("Cancelled chat task on speech_start | chat_id={}", chat_id)
        if interrupted_snapshot is not None:
            await _persist_interrupted_generation(
                interrupted_snapshot,
                service_context=service_context,
                storage=storage,
                user_id=user_id,
            )
            await _send_chat_interrupted(websocket, interrupted_snapshot)
    if event.type is VADEventType.SPEECH_END and speech_audio is not None:
        asr_result = await _handle_speech_end_asr(
            websocket,
            asr_service,
            speech_audio,
            chat_id=str(chat_id),
            character_id=str(character_id),
            sample_rate=sample_rate,
            min_speech_ms=_get_min_speech_ms(vad_service),
            seq=data.get("seq"),
        )
        if asr_result is not None:
            await _start_asr_chat_task(
                websocket,
                vad_state,
                service_context,
                storage,
                user_id,
                chat_id=str(chat_id),
                character_id=str(character_id),
                text=asr_result["text"],
                generation_id=asr_result["generation_id"],
            )


async def _handle_vad_audio_error(
    websocket: WebSocket,
    vad_service: VADService,
    vad_state: WebSocketVADState,
    error: Exception,
    *,
    chat_id: str,
    character_id: str,
    seq: Any | None = None,
) -> None:
    """Report VAD processing errors without closing the chat WebSocket."""

    if isinstance(error, VADProviderUnavailableError):
        code = "vad_provider_unavailable"
        message = str(error) or "VAD provider is unavailable."
    elif isinstance(error, VADConfigError):
        code = "vad_config_error"
        message = str(error) or "VAD configuration is invalid."
    elif isinstance(error, VADProcessingError):
        code = "vad_processing_failed"
        message = str(error) or "VAD processing failed."
    else:
        code = "vad_processing_failed"
        message = "VAD processing failed."

    logger.warning(
        "VAD audio processing failed | chat_id={} | character_id={} | code={} | error={}",
        chat_id,
        character_id,
        code,
        error,
    )

    vad_state.interrupt_sent = False
    vad_state.clear_audio_buffer()
    vad_state.clear_pre_buffer()
    try:
        vad_service.reset_session(vad_state.session_id)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"VAD session reset skipped after processing error: {exc}")

    await _send_listen_error(
        websocket,
        chat_id=chat_id,
        character_id=character_id,
        code=code,
        message=message,
        seq=seq,
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
    vad_state.clear_pre_buffer()
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


def _float_audio_to_wav_bytes(audio: list[float], *, sample_rate: int = 16000) -> bytes:
    """Encode mono float PCM samples as 16-bit WAV bytes for ASR providers."""

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        pcm = bytearray()
        for sample in audio:
            clipped = max(-1.0, min(1.0, float(sample)))
            pcm_value = int(clipped * 32767)
            pcm.extend(pcm_value.to_bytes(2, byteorder="little", signed=True))
        wav.writeframes(bytes(pcm))
    return buffer.getvalue()


def _get_vad_sample_rate(vad_service: VADService) -> int:
    try:
        return int(vad_service.get_config().get("sample_rate") or 16000)
    except Exception:
        return 16000


def _get_vad_pre_buffer_ms(vad_service: VADService) -> int:
    try:
        return max(0, int(vad_service.get_config().get("pre_buffer_ms") or 0))
    except Exception:
        return 0


def _get_min_speech_ms(vad_service: VADService) -> int:
    try:
        return max(0, int(vad_service.get_config().get("min_speech_ms") or 0))
    except Exception:
        return 0


def _is_speech_audio_too_short(
    audio: list[float],
    *,
    sample_rate: int,
    min_speech_ms: int,
) -> bool:
    if min_speech_ms <= 0:
        return False
    min_samples = int(sample_rate * min_speech_ms / 1000)
    return len(audio) < max(1, min_samples)


def _normalize_asr_transcript(value: Any) -> str | None:
    transcript = str(value or "").strip()
    if not transcript:
        return None
    if not any(character.isalnum() for character in transcript):
        return None
    return transcript


async def _handle_speech_end_asr(
    websocket: WebSocket,
    asr_service: Any | None,
    audio: list[float],
    *,
    chat_id: str,
    character_id: str,
    sample_rate: int = 16000,
    min_speech_ms: int = 0,
    seq: Any | None = None,
) -> dict[str, str] | None:
    """转录完成的VAD语音片段并通知前端。"""

    if asr_service is None:
        await _send_listen_error(
            websocket,
            chat_id=chat_id,
            character_id=character_id,
            code="backend_asr_unavailable",
            message="VAD auto-submit requires a backend ASR service.",
            seq=seq,
        )
        return None
    if not audio:
        await _send_listen_error(
            websocket,
            chat_id=chat_id,
            character_id=character_id,
            code="empty_speech_audio",
            message="VAD speech segment is empty.",
            seq=seq,
        )
        return None
    if _is_speech_audio_too_short(audio, sample_rate=sample_rate, min_speech_ms=min_speech_ms):
        await _send_listen_error(
            websocket,
            chat_id=chat_id,
            character_id=character_id,
            code="speech_too_short",
            message="VAD speech segment is too short for ASR auto-submit.",
            seq=seq,
        )
        return None

    generation_id = uuid.uuid4().hex
    try:
        result = await asr_service.transcribe_audio(
            _float_audio_to_wav_bytes(audio, sample_rate=sample_rate),
            filename="realtime-vad.wav",
            content_type="audio/wav",
        )
    except ASRProviderUnavailableError as exc:
        await _send_listen_error(
            websocket,
            chat_id=chat_id,
            character_id=character_id,
            code="backend_asr_unavailable",
            message=str(exc),
            seq=seq,
        )
        return None
    except (ASRConfigError, ASRTranscriptionError) as exc:
        await _send_listen_error(
            websocket,
            chat_id=chat_id,
            character_id=character_id,
            code="asr_transcription_failed",
            message=str(exc),
            seq=seq,
        )
        return None
    except Exception as exc:
        logger.error(f"Unexpected ASR error during realtime speech handoff: {exc}")
        await _send_listen_error(
            websocket,
            chat_id=chat_id,
            character_id=character_id,
            code="asr_transcription_failed",
            message="VAD ASR transcription failed.",
            seq=seq,
        )
        return None

    transcript = _normalize_asr_transcript(result.get("text")) if isinstance(result, dict) else None
    if transcript is None:
        await _send_listen_error(
            websocket,
            chat_id=chat_id,
            character_id=character_id,
            code="empty_asr_transcript",
            message="VAD ASR returned empty transcript.",
            seq=seq,
        )
        return None

    await _send_asr_transcript(
        websocket,
        chat_id=chat_id,
        character_id=character_id,
        text=transcript,
        generation_id=generation_id,
        is_final=True,
        seq=seq,
    )
    return {"text": transcript, "generation_id": generation_id}


async def _start_asr_chat_task(
    websocket: WebSocket,
    vad_state: WebSocketVADState,
    service_context: Any | None,
    storage: Any | None,
    user_id: str | None,
    *,
    chat_id: str,
    character_id: str,
    text: str,
    generation_id: str,
) -> None:
    """Start a backend-owned chat turn from a completed ASR transcript."""

    if service_context is None or storage is None or user_id is None:
        return

    current_task = vad_state.current_chat_task
    if current_task is not None and current_task.cancelling():
        try:
            await current_task
        except asyncio.CancelledError:
            pass

    message = {
        "type": "input:text",
        "data": {
            "text": text,
            "chat_id": chat_id,
            "character_id": character_id,
        },
    }
    started = _start_tracked_chat_task(
        vad_state,
        generation_id,
        _handle_text_input(
            websocket,
            message,
            service_context,
            storage,
            user_id,
            vad_state,
            generation_id,
        ),
    )
    if not started:
        await _send_error(websocket, "Chat task already running", chat_id=chat_id)


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

    await _send_json(websocket, {"type": "control:listen-state", "data": data})


async def _send_listen_error(
    websocket: WebSocket,
    *,
    chat_id: str,
    character_id: str,
    code: str,
    message: str,
    seq: Any | None = None,
) -> None:
    """Send a control:listen-state error message to the frontend."""

    data: dict[str, Any] = {
        "chat_id": chat_id,
        "character_id": character_id,
        "state": VADEventType.ERROR.value,
        "code": code,
        "message": message,
    }
    if isinstance(seq, int) and not isinstance(seq, bool):
        data["seq"] = seq
    await _send_json(websocket, {"type": "control:listen-state", "data": data})


async def _send_chat_interrupted(
    websocket: WebSocket,
    snapshot: InterruptedGenerationSnapshot,
) -> None:
    """Send an output:chat:interrupted message for a persisted partial reply."""

    await _send_json(
        websocket,
        {
            "type": "output:chat:interrupted",
            "data": {
                "chat_id": snapshot.chat_id,
                "character_id": snapshot.character_id,
                "generation_id": snapshot.generation_id,
                "partial_reply": snapshot.partial_reply,
                "interrupted": True,
                "reason": snapshot.reason,
            },
        },
    )


async def _send_asr_transcript(
    websocket: WebSocket,
    *,
    chat_id: str,
    character_id: str,
    text: str,
    generation_id: str | None = None,
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
    if generation_id is not None:
        data["generation_id"] = generation_id
    if isinstance(seq, int) and not isinstance(seq, bool):
        data["seq"] = seq

    await _send_json(websocket, {"type": "output:asr:transcript", "data": data})


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

    await _send_json(websocket, {"type": "error", "data": error_data})
