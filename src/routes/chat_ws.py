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
import base64
import io
import json
import uuid
import wave
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger
from starlette.websockets import WebSocketState

from src.asr.exceptions import ASRConfigError, ASRProviderUnavailableError, ASRTranscriptionError
from src.auth import get_websocket_user_id
from src.llm.exceptions import LLMError
from src.tts.segment_manager import (
    TTSAudioComplete,
    TTSAudioError,
    TTSAudioSegment,
    TTSSegmentManager,
)
from src.vad import VADEvent, VADEventType, VADService, VADState
from src.vad.exceptions import VADConfigError, VADProcessingError, VADProviderUnavailableError
from src.vision import (
    InputImage,
    InputInform,
    InputText,
    VisionCaptureCoordinator,
    VisionService,
    validate_input_image,
    websocket_message_size_bytes,
    websocket_message_within_limit,
)

_TTS_FINISH_TASKS: set[asyncio.Task[None]] = set()
_CHAT_GENERATION_FAILURE_MESSAGE = "本轮回复生成失败，请稍后重试。"


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
class WebSocketVisionState:
    """Runtime-only screen sharing state for one WebSocket connection."""

    enabled: bool = False
    source: Literal["screen"] = "screen"
    capture_coordinator: VisionCaptureCoordinator = field(default_factory=VisionCaptureCoordinator)

    def is_active(self, vision_service: VisionService) -> bool:
        """Return whether this connection may attach a screen frame."""

        return self.enabled and vision_service.is_enabled()

    def set_enabled(self, enabled: bool) -> None:
        """Update the connection projection and unblock pending turns on stop."""

        self.enabled = enabled
        if not enabled:
            for generation_id in self.capture_coordinator.pending_generation_ids:
                self.capture_coordinator.resolve(generation_id, None)

    def release(self) -> None:
        """Cancel pending capture waits when the connection is destroyed."""

        self.enabled = False
        self.capture_coordinator.cancel_all()


@dataclass
class WebSocketVADState:
    """Per-connection VAD state reserved for realtime audio control."""

    session_id: str
    interrupt_sent: bool = False
    current_chat_task: asyncio.Task[None] | None = None
    current_generation_id: str | None = None
    current_generation_committing: bool = False
    current_generation_chat_id: str | None = None
    current_generation_character_id: str | None = None
    current_generation_user_text: str | None = None
    current_generation_reply_chunks: list[str] = field(default_factory=list)
    current_tts_generation_id: str | None = None
    current_tts_manager: TTSSegmentManager | None = None
    audio_buffer: list[float] = field(default_factory=list)
    pre_buffer: list[float] = field(default_factory=list)
    last_chat_id: str | None = None
    last_character_id: str | None = None

    def activate_generation(self, generation_id: str) -> None:
        """Mark a chat generation as the only valid one for this connection."""

        self.current_generation_id = generation_id
        self.current_generation_committing = False
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

    def begin_generation_commit(self, generation_id: str) -> bool:
        """Claim durable success for the active generation exactly once."""

        if not self.is_generation_active(generation_id) or self.current_generation_committing:
            return False
        self.current_generation_committing = True
        return True

    def is_generation_committing(self, generation_id: str | None = None) -> bool:
        """Return whether durable success is already owned by this generation."""

        if not self.current_generation_committing:
            return False
        return generation_id is None or self.current_generation_id == generation_id

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
        self.current_generation_committing = False
        self.current_generation_chat_id = None
        self.current_generation_character_id = None
        self.current_generation_user_text = None
        self.current_generation_reply_chunks.clear()
        return generation_id

    def complete_generation(self, generation_id: str) -> None:
        """Release partial-reply tracking for a normally completed generation."""

        if self.is_generation_active(generation_id):
            self.invalidate_current_generation()

    def is_tts_generation_active(self, generation_id: str) -> bool:
        """Return whether a TTS generation can still emit audio events."""

        return self.current_tts_generation_id == generation_id

    async def set_tts_manager(
        self,
        generation_id: str,
        manager: TTSSegmentManager,
    ) -> None:
        """Track the active segmented TTS manager for this connection."""

        await self.interrupt_tts_generation()
        self.current_tts_generation_id = generation_id
        self.current_tts_manager = manager

    async def feed_tts_text(self, generation_id: str, chunk: str) -> None:
        """Forward emitted chat text to the active TTS manager."""

        manager = self.current_tts_manager
        if manager is None or not self.is_tts_generation_active(generation_id):
            return
        await manager.feed_text(chunk)

    async def finish_tts_generation(self, generation_id: str) -> None:
        """Flush and complete the active TTS manager for a normal generation."""

        manager = self.current_tts_manager
        if manager is None or not self.is_tts_generation_active(generation_id):
            return
        await manager.finish()

    async def interrupt_tts_generation(self, generation_id: str | None = None) -> str | None:
        """Interrupt the active TTS manager and return its generation id."""

        if generation_id is not None and not self.is_tts_generation_active(generation_id):
            return None

        manager = self.current_tts_manager
        interrupted_generation_id = self.current_tts_generation_id
        self.current_tts_generation_id = None
        self.current_tts_manager = None
        if manager is not None:
            await manager.interrupt()
        return interrupted_generation_id

    def complete_tts_generation(self, generation_id: str) -> None:
        """Release TTS manager tracking after output:audio:complete."""

        if self.is_tts_generation_active(generation_id):
            self.current_tts_generation_id = None
            self.current_tts_manager = None

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
        self.current_tts_generation_id = None
        self.current_tts_manager = None


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
    tts_service = getattr(websocket.app.state, "tts_service", None)
    vision_service = websocket.app.state.vision_service
    vad_state = WebSocketVADState(session_id=f"ws:{uuid.uuid4().hex}")
    vision_state = WebSocketVisionState()

    try:
        while True:
            # Receive message from client
            # 接收客户端消息
            raw_message = await websocket.receive_text()

            vision_config = vision_service.get_config()
            max_message_bytes = vision_config["transport"]["websocket_max_message_bytes"]
            if not websocket_message_within_limit(raw_message, max_message_bytes):
                logger.warning(
                    "Rejected oversized WebSocket text frame | size_bytes={} | limit_bytes={}",
                    websocket_message_size_bytes(raw_message),
                    max_message_bytes,
                )
                await _send_error(
                    websocket,
                    "WebSocket message exceeds the configured size limit",
                    chat_id=None,
                )
                continue

            # Parse JSON
            # 解析 JSON
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Invalid WebSocket JSON | line={} | column={}",
                    exc.lineno,
                    exc.colno,
                )
                await _send_error(websocket, "Invalid JSON format", chat_id=None)
                continue

            if not isinstance(message, dict):
                logger.warning("WebSocket message root must be an object")
                await _send_error(websocket, "Message must be an object", chat_id=None)
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
                        tts_service=tts_service,
                        vision_state=vision_state,
                        vision_service=vision_service,
                    ),
                )
                if not started:
                    await _send_error(
                        websocket,
                        "Chat task already running",
                        chat_id=_message_chat_id(message),
                        character_id=_message_character_id(message),
                        request_id=_message_request_id(message),
                        generation_id=generation_id,
                    )
            elif msg_type == "input:vision:state":
                await _handle_vision_state(
                    websocket,
                    message,
                    vision_state,
                    vision_service,
                )
            elif msg_type == "input:vision:capture-result":
                await _handle_vision_capture_result(
                    websocket,
                    message,
                    vad_state,
                    vision_state,
                    vision_service,
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
                    tts_service=tts_service,
                    vision_state=vision_state,
                    vision_service=vision_service,
                )
            elif msg_type == "input:audio:end":
                await _handle_audio_end(websocket, message, vad_service, vad_state)
            else:
                logger.warning("Unknown WebSocket message type")
                await _send_error(
                    websocket,
                    "Unknown message type",
                    chat_id=_message_chat_id(message),
                )

    except WebSocketDisconnect:
        logger.info("WebSocket connection closed by client")
    except Exception as exc:
        logger.error("WebSocket connection failed | error_type={}", type(exc).__name__)
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await _send_error(websocket, "Internal server error", chat_id=None)
        except Exception:
            pass  # Connection already closed
    finally:
        vision_state.release()
        await vad_state.interrupt_tts_generation()
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


def _message_chat_id(message: dict[str, Any]) -> str | None:
    """Extract a safe chat identifier without assuming a valid data object."""

    data = message.get("data")
    if not isinstance(data, dict):
        return None
    chat_id = data.get("chat_id")
    return chat_id if isinstance(chat_id, str) and chat_id else None


def _message_character_id(message: dict[str, Any]) -> str | None:
    """Extract a safe character identifier from a message data object."""

    data = message.get("data")
    if not isinstance(data, dict):
        return None
    character_id = data.get("character_id")
    return character_id if isinstance(character_id, str) and character_id else None


def _message_request_id(message: dict[str, Any]) -> str | None:
    """Extract the bounded client correlation id used for input rejection."""

    data = message.get("data")
    if not isinstance(data, dict):
        return None
    request_id = data.get("request_id")
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        return None
    return request_id


async def _handle_vision_state(
    websocket: WebSocket,
    message: dict[str, Any],
    vision_state: WebSocketVisionState,
    vision_service: VisionService,
) -> None:
    """Project the current browser screen-sharing state onto this connection."""

    data = message.get("data")
    if not isinstance(data, dict):
        await _send_error(websocket, "Message 'data' must be an object", chat_id=None)
        return

    enabled = data.get("enabled")
    source = data.get("source")
    if type(enabled) is not bool:
        await _send_error(
            websocket,
            "Vision state 'enabled' must be a boolean",
            chat_id=None,
        )
        return
    if source != "screen":
        await _send_error(
            websocket,
            "Vision state 'source' must be 'screen'",
            chat_id=None,
        )
        return

    vision_state.set_enabled(enabled)
    logger.info(
        "WebSocket vision state updated | enabled={} | module_enabled={} | source=screen",
        enabled,
        vision_service.is_enabled(),
    )


async def _handle_vision_capture_result(
    websocket: WebSocket,
    message: dict[str, Any],
    vad_state: WebSocketVADState,
    vision_state: WebSocketVisionState,
    vision_service: VisionService,
) -> None:
    """Resolve one generation-keyed browser capture without blocking receives."""

    data = message.get("data")
    if not isinstance(data, dict):
        await _send_error(websocket, "Message 'data' must be an object", chat_id=None)
        return

    generation_id = data.get("generation_id")
    if not isinstance(generation_id, str) or not generation_id:
        await _send_error(
            websocket,
            "Vision capture result requires 'generation_id'",
            chat_id=None,
        )
        return

    coordinator = vision_state.capture_coordinator
    if generation_id not in coordinator.pending_generation_ids:
        logger.debug(
            "Discarding unknown or stale vision capture result | generation_id={}",
            generation_id,
        )
        return
    if not vad_state.is_generation_active(generation_id) or not vision_state.is_active(
        vision_service
    ):
        coordinator.resolve(generation_id, None)
        logger.debug(
            "Discarding inactive vision capture result | generation_id={}",
            generation_id,
        )
        return

    status = data.get("status")
    if status in {"unavailable", "failed"}:
        coordinator.resolve(generation_id, None)
        logger.debug(
            "Vision capture unavailable | generation_id={} | status={}",
            generation_id,
            status,
        )
        return
    if status != "captured":
        coordinator.resolve(generation_id, None)
        await _send_error(
            websocket,
            "Vision capture result has invalid 'status'",
            chat_id=None,
            generation_id=generation_id,
        )
        return

    config = vision_service.get_config()
    validation = validate_input_image(
        data.get("image"),
        max_decoded_bytes=config["capture"]["max_decoded_bytes"],
    )
    coordinator.resolve(generation_id, validation.image if validation.is_valid else None)
    if not validation.is_valid:
        logger.warning(
            "Discarded invalid vision capture | generation_id={} | code={} | "
            "encoded_length={} | decoded_length={}",
            generation_id,
            validation.code,
            validation.encoded_length,
            validation.decoded_length,
        )


def _validated_message_image(
    data: dict[str, Any],
    *,
    chat_id: str,
    generation_id: str,
    vision_state: WebSocketVisionState | None,
    vision_service: VisionService | None,
) -> InputImage | None:
    """Validate an optional direct-submit image only when vision is active."""

    if vision_state is None or vision_service is None or not vision_state.is_active(vision_service):
        return None

    config = vision_service.get_config()
    validation = validate_input_image(
        data.get("image"),
        max_decoded_bytes=config["capture"]["max_decoded_bytes"],
    )
    if validation.is_valid:
        return validation.image
    if validation.code != "missing":
        logger.warning(
            "Discarded invalid input image | chat_id={} | generation_id={} | code={} | "
            "encoded_length={} | decoded_length={}",
            chat_id,
            generation_id,
            validation.code,
            validation.encoded_length,
            validation.decoded_length,
        )
    return None


async def _capture_image_for_generation(
    websocket: WebSocket,
    vad_state: WebSocketVADState,
    vision_state: WebSocketVisionState,
    vision_service: VisionService,
    *,
    generation_id: str,
    chat_id: str,
    character_id: str,
) -> InputImage | None:
    """Request one browser frame for a VAD turn and silently fall back."""

    if not vision_state.is_active(vision_service):
        return None

    coordinator = vision_state.capture_coordinator
    try:
        future = coordinator.register(generation_id)
    except ValueError:
        logger.warning(
            "Vision capture registration failed | generation_id={} | error_type=ValueError",
            generation_id,
        )
        return None

    request = {
        "type": "control:vision:capture-request",
        "data": {
            "generation_id": generation_id,
            "chat_id": chat_id,
            "character_id": character_id,
            "source": "screen",
        },
    }
    try:
        sent = await _send_generation_event(
            websocket,
            vad_state,
            generation_id,
            request,
        )
    except asyncio.CancelledError:
        coordinator.cancel(generation_id)
        raise
    except Exception as exc:
        coordinator.cancel(generation_id)
        logger.warning(
            "Vision capture request failed | generation_id={} | error_type={}",
            generation_id,
            type(exc).__name__,
        )
        return None

    if not sent:
        coordinator.cancel(generation_id)
        return None

    config = vision_service.get_config()
    image = await coordinator.wait(
        generation_id,
        future,
        timeout_ms=config["capture"]["timeout_ms"],
    )
    if not vad_state.is_generation_active(generation_id):
        return None
    if not vision_state.is_active(vision_service):
        return None
    return image


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


async def _send_generation_event(
    websocket: Any,
    vad_state: WebSocketVADState,
    generation_id: str,
    message: dict[str, Any],
) -> bool:
    """Send a non-terminal generation event only while it remains active."""

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


async def _claim_generation_commit(
    websocket: Any,
    vad_state: WebSocketVADState,
    generation_id: str,
) -> bool:
    """Atomically claim durable success before persistence starts."""

    send_lock = _get_send_lock(websocket)
    if send_lock is None:
        return vad_state.begin_generation_commit(generation_id)

    async with send_lock:
        return vad_state.begin_generation_commit(generation_id)


async def _send_generation_complete(
    websocket: Any,
    vad_state: WebSocketVADState,
    generation_id: str,
    message: dict[str, Any],
) -> bool:
    """Atomically send and invalidate a successfully completed generation."""

    send_lock = _get_send_lock(websocket)
    if send_lock is None:
        if not vad_state.is_generation_active(generation_id):
            return False
        await websocket.send_json(message)
        vad_state.invalidate_current_generation()
        return True

    async with send_lock:
        if not vad_state.is_generation_active(generation_id):
            return False
        await websocket.send_json(message)
        vad_state.invalidate_current_generation()
        return True


async def _send_generation_failure(
    websocket: Any,
    vad_state: WebSocketVADState,
    *,
    chat_id: str,
    character_id: str,
    generation_id: str,
) -> bool:
    """Commit one safe pre-success failure if the generation is still active."""

    message = {
        "type": "output:chat:error",
        "data": {
            "message": _CHAT_GENERATION_FAILURE_MESSAGE,
            "chat_id": chat_id,
            "character_id": character_id,
            "generation_id": generation_id,
        },
    }
    send_lock = _get_send_lock(websocket)
    if send_lock is None:
        if not vad_state.is_generation_active(generation_id):
            return False
        await websocket.send_json(message)
        vad_state.invalidate_current_generation()
    else:
        async with send_lock:
            if not vad_state.is_generation_active(generation_id):
                return False
            await websocket.send_json(message)
            vad_state.invalidate_current_generation()

    try:
        await vad_state.interrupt_tts_generation(generation_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to clean up TTS after chat failure | generation_id={} | error_type={}",
            generation_id,
            type(exc).__name__,
        )
    return True


async def _send_tts_audio_segment(
    websocket: Any,
    vad_state: WebSocketVADState,
    segment: TTSAudioSegment,
) -> None:
    """Send one TTS audio segment if its generation is still active."""

    message = {
        "type": "output:audio:segment",
        "data": {
            "chat_id": segment.chat_id,
            "character_id": segment.character_id,
            "generation_id": segment.generation_id,
            "segment_id": segment.segment_id,
            "sequence": segment.sequence,
            "audio": base64.b64encode(segment.audio).decode("ascii"),
            "media_type": segment.media_type,
            "display_text": segment.display_text,
            "tts_text": segment.tts_text,
        },
    }
    await _send_tts_generation_event(websocket, vad_state, segment.generation_id, message)


async def _send_tts_audio_complete(
    websocket: Any,
    vad_state: WebSocketVADState,
    complete: TTSAudioComplete,
) -> None:
    """Send TTS audio completion if its generation is still active."""

    message = {
        "type": "output:audio:complete",
        "data": {
            "chat_id": complete.chat_id,
            "character_id": complete.character_id,
            "generation_id": complete.generation_id,
            "last_sequence": complete.last_sequence,
        },
    }
    await _send_tts_generation_event(websocket, vad_state, complete.generation_id, message)
    vad_state.complete_tts_generation(complete.generation_id)


async def _send_tts_audio_error(
    websocket: Any,
    vad_state: WebSocketVADState,
    error: TTSAudioError,
) -> None:
    """Send a per-segment TTS error if its generation is still active."""

    message = {
        "type": "output:audio:error",
        "data": {
            "chat_id": error.chat_id,
            "character_id": error.character_id,
            "generation_id": error.generation_id,
            "segment_id": error.segment_id,
            "sequence": error.sequence,
            "code": error.code,
            "message": error.message,
        },
    }
    await _send_tts_generation_event(websocket, vad_state, error.generation_id, message)


async def _send_tts_generation_event(
    websocket: Any,
    vad_state: WebSocketVADState,
    generation_id: str,
    message: dict[str, Any],
) -> None:
    """Send a TTS event with a stale-generation check under the send lock."""

    send_lock = _get_send_lock(websocket)
    if send_lock is None:
        if vad_state.is_tts_generation_active(generation_id):
            await websocket.send_json(message)
        return

    async with send_lock:
        if vad_state.is_tts_generation_active(generation_id):
            await websocket.send_json(message)


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
    if vad_state.is_generation_committing():
        committing_generation_id = vad_state.current_generation_id
        interrupted_tts_generation_id = await vad_state.interrupt_tts_generation()
        control_generation_id = committing_generation_id or interrupted_tts_generation_id
        data: dict[str, Any] = {
            "chat_id": chat_id,
            "character_id": character_id,
            "reason": "speech_start",
            "preserve_chat_generation": True,
        }
        if control_generation_id is not None:
            data["generation_id"] = control_generation_id
        await websocket.send_json({"type": "control:interrupt", "data": data})
        return None, control_generation_id, False

    interrupted_snapshot = vad_state.get_interrupted_generation(reason="vad_speech_start")
    stale_generation_id = vad_state.invalidate_current_generation()
    cancelled = vad_state.cancel_current_chat_task()
    interrupted_tts_generation_id = await vad_state.interrupt_tts_generation()
    control_generation_id = stale_generation_id or interrupted_tts_generation_id

    data: dict[str, Any] = {
        "chat_id": chat_id,
        "character_id": character_id,
        "reason": "speech_start",
    }
    if control_generation_id is not None:
        data["generation_id"] = control_generation_id

    await websocket.send_json(
        {
            "type": "control:interrupt",
            "data": data,
        }
    )
    return interrupted_snapshot, control_generation_id, cancelled


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
        logger.error("Tracked chat task failed | error_type={}", type(exc).__name__)


def _start_tts_finish_task(vad_state: WebSocketVADState, generation_id: str) -> None:
    """Finish TTS after chat completion without holding the chat task open."""

    task = asyncio.create_task(_finish_tts_generation_safely(vad_state, generation_id))
    _TTS_FINISH_TASKS.add(task)
    task.add_done_callback(_finalize_tts_finish_task)


def _finalize_tts_finish_task(task: asyncio.Task[None]) -> None:
    """Release a background TTS finish task and consume terminal exceptions."""

    _TTS_FINISH_TASKS.discard(task)
    try:
        task.result()
    except asyncio.CancelledError:
        logger.debug("TTS finish task cancelled")
    except Exception as exc:
        logger.warning(f"TTS finish task failed unexpectedly: {exc}")


async def _finish_tts_generation_safely(
    vad_state: WebSocketVADState,
    generation_id: str,
) -> None:
    """Flush TTS in the background and clean up on recoverable failures."""

    try:
        await vad_state.finish_tts_generation(generation_id)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "TTS finish task failed | generation_id={} | error={!r}",
            generation_id,
            exc,
        )
        try:
            await vad_state.interrupt_tts_generation(generation_id)
        except Exception as cleanup_exc:  # noqa: BLE001
            logger.warning(
                "TTS finish cleanup failed | generation_id={} | error={!r}",
                generation_id,
                cleanup_exc,
            )


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


async def _maybe_start_tts_segment_manager(
    websocket: Any,
    vad_state: WebSocketVADState,
    tts_service: Any | None,
    *,
    chat_id: str,
    character_id: str,
    generation_id: str,
) -> TTSSegmentManager | None:
    """Create and track a TTS segment manager when streaming auto-play is enabled."""

    if tts_service is None:
        return None

    config = _read_tts_config(tts_service)
    streaming_config = config.get("streaming")
    if not isinstance(streaming_config, dict):
        streaming_config = {}
    if not (
        _config_enabled(config.get("enabled"))
        and _config_enabled(config.get("auto_play"))
        and _config_enabled(streaming_config.get("enabled"))
    ):
        return None

    async def send_segment(segment: TTSAudioSegment) -> None:
        await _send_tts_audio_segment(websocket, vad_state, segment)

    async def send_complete(complete: TTSAudioComplete) -> None:
        await _send_tts_audio_complete(websocket, vad_state, complete)

    async def send_error(error: TTSAudioError) -> None:
        await _send_tts_audio_error(websocket, vad_state, error)

    try:
        manager = TTSSegmentManager(
            tts_service=tts_service,
            chat_id=chat_id,
            character_id=character_id,
            generation_id=generation_id,
            config=streaming_config,
            send_segment=send_segment,
            send_complete=send_complete,
            send_error=send_error,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to initialize TTS segment manager | chat_id={} | generation_id={} | error={!r}",
            chat_id,
            generation_id,
            exc,
        )
        return None

    await vad_state.set_tts_manager(generation_id, manager)
    return manager


def _read_tts_config(tts_service: Any) -> dict[str, Any]:
    config_store = getattr(tts_service, "config_store", None)
    if config_store is not None and hasattr(config_store, "read"):
        config = config_store.read()
    elif hasattr(tts_service, "get_config"):
        config = tts_service.get_config()
    else:
        return {}
    return config if isinstance(config, dict) else {}


def _config_enabled(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


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
    tts_service: Any | None = None,
    vision_state: WebSocketVisionState | None = None,
    vision_service: VisionService | None = None,
    input_image: InputImage | None = None,
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
    if not isinstance(data, dict):
        await _send_error(websocket, "Message 'data' must be an object", chat_id=None)
        _discard_generation_if_active(vad_state, generation_id)
        return
    text = data.get("text")
    chat_id = data.get("chat_id")
    character_id = data.get("character_id")
    request_id = _message_request_id(message)
    client_context = data.get("client_context")
    if not isinstance(client_context, dict):
        client_context = None

    # Validate required fields
    # 验证必填字段
    if not isinstance(text, str) or not text.strip():
        await _send_error(
            websocket,
            "Missing 'text' field",
            chat_id=chat_id,
            character_id=character_id if isinstance(character_id, str) else None,
            request_id=request_id,
            generation_id=generation_id,
        )
        _discard_generation_if_active(vad_state, generation_id)
        return
    if not chat_id:
        await _send_error(
            websocket,
            "Missing 'chat_id' field",
            chat_id=None,
            character_id=character_id if isinstance(character_id, str) else None,
            request_id=request_id,
            generation_id=generation_id,
        )
        _discard_generation_if_active(vad_state, generation_id)
        return
    if not character_id:
        await _send_error(
            websocket,
            "Missing 'character_id' field",
            chat_id=chat_id,
            request_id=request_id,
            generation_id=generation_id,
        )
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
        await _send_error(
            websocket,
            f"Invalid chat request: {exc}",
            chat_id=chat_id,
            character_id=str(character_id),
            request_id=request_id,
            generation_id=generation_id,
        )
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
            character_id=str(character_id),
            request_id=request_id,
            generation_id=generation_id,
        )
        _discard_generation_if_active(vad_state, generation_id)
        return

    vad_state.set_generation_context(
        generation_id,
        chat_id=str(chat_id),
        character_id=str(character_id),
        user_text=str(text),
    )

    try:
        effective_image = input_image
        if (
            vision_state is None
            or vision_service is None
            or not vision_state.is_active(vision_service)
        ):
            effective_image = None
        elif effective_image is None:
            effective_image = _validated_message_image(
                data,
                chat_id=str(chat_id),
                generation_id=generation_id,
                vision_state=vision_state,
                vision_service=vision_service,
            )
        input_inform = InputInform(
            input_text=InputText(content=text),
            image=effective_image,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to assemble chat input | chat_id={} | character_id={} | "
            "generation_id={} | error_type={}",
            chat_id,
            character_id,
            generation_id,
            type(exc).__name__,
        )
        await _send_generation_failure(
            websocket,
            vad_state,
            chat_id=str(chat_id),
            character_id=str(character_id),
            generation_id=generation_id,
        )
        return

    # Get or create ChatAgent for this character/user/chat.
    # 获取或创建此 character/user/chat 的 ChatAgent。
    try:
        agent = service_context.get_or_create_agent(character_id, user_id, chat_id)
    except Exception as exc:
        logger.error(
            "Failed to initialize ChatAgent | chat_id={} | character_id={} | "
            "generation_id={} | error_type={}",
            chat_id,
            character_id,
            generation_id,
            type(exc).__name__,
        )
        await _send_generation_failure(
            websocket,
            vad_state,
            chat_id=str(chat_id),
            character_id=str(character_id),
            generation_id=generation_id,
        )
        return

    tts_manager = await _maybe_start_tts_segment_manager(
        websocket,
        vad_state,
        tts_service,
        chat_id=str(chat_id),
        character_id=str(character_id),
        generation_id=generation_id,
    )

    # Stream ChatAgent response
    # 流式传输 ChatAgent 响应
    chunks = []
    durable_success_started = False
    try:
        chat_stream = (
            agent.chat(input_inform, runtime_context=client_context, commit_round=False)
            if client_context
            else agent.chat(input_inform, commit_round=False)
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
            if tts_manager is not None:
                await vad_state.feed_tts_text(generation_id, chunk)

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
        durable_success_started = await _claim_generation_commit(
            websocket,
            vad_state,
            generation_id,
        )
        if not durable_success_started:
            logger.info(
                "Discarding stale chat completion before durable commit | "
                "chat_id={} | generation_id={}",
                chat_id,
                generation_id,
            )
            return
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
                metadata={"generation_id": generation_id},
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
        except ValueError as exc:
            # Chat not found (client may have deleted it)
            # 聊天不存在（客户端可能已删除）
            logger.warning(
                "Failed to persist chat messages | chat_id={} | generation_id={} | error_type={}",
                chat_id,
                generation_id,
                type(exc).__name__,
            )
        except Exception as exc:
            logger.error(
                "Unexpected chat persistence failure | chat_id={} | generation_id={} | "
                "error_type={}",
                chat_id,
                generation_id,
                type(exc).__name__,
            )

        ai_name = character_id
        persona_name = getattr(getattr(agent, "persona", None), "name", None)
        if isinstance(persona_name, str) and persona_name.strip():
            ai_name = persona_name
        try:
            await agent.memory_manager.on_round_complete(
                {"role": "human", "content": str(text), "name": user_id},
                {"role": "ai", "content": full_reply, "name": ai_name},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Post-persistence memory commit failed | chat_id={} | generation_id={} | "
                "error_type={}",
                chat_id,
                generation_id,
                type(exc).__name__,
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
        if tts_manager is not None:
            _start_tts_finish_task(vad_state, generation_id)

        logger.info(f"Chat complete | chat_id={chat_id} | reply_length={len(full_reply)}")

    except asyncio.CancelledError:
        raise
    except LLMError as exc:
        logger.error(
            "LLM generation failed | chat_id={} | character_id={} | generation_id={} | "
            "error_type={}",
            chat_id,
            character_id,
            generation_id,
            type(exc).__name__,
        )
        if not durable_success_started:
            await _send_generation_failure(
                websocket,
                vad_state,
                chat_id=str(chat_id),
                character_id=str(character_id),
                generation_id=generation_id,
            )
            return
        _discard_generation_if_active(vad_state, generation_id)
        await vad_state.interrupt_tts_generation(generation_id)
    except Exception as exc:
        logger.error(
            "Chat generation orchestration failed | chat_id={} | character_id={} | "
            "generation_id={} | durable_success_started={} | error_type={}",
            chat_id,
            character_id,
            generation_id,
            durable_success_started,
            type(exc).__name__,
        )
        if not durable_success_started:
            await _send_generation_failure(
                websocket,
                vad_state,
                chat_id=str(chat_id),
                character_id=str(character_id),
                generation_id=generation_id,
            )
            return
        _discard_generation_if_active(vad_state, generation_id)
        await vad_state.interrupt_tts_generation(generation_id)


async def _wait_for_committing_generation(vad_state: WebSocketVADState) -> None:
    """Let an already claimed durable commit finish before the next ASR turn."""

    task = vad_state.current_chat_task
    if task is None or task.done() or not vad_state.is_generation_committing():
        return
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        if task.cancelled():
            return
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Committing chat task ended unexpectedly before next ASR turn | error_type={}",
            type(exc).__name__,
        )


async def _handle_audio_chunk(
    websocket: WebSocket,
    message: dict[str, Any],
    vad_service: VADService,
    vad_state: WebSocketVADState,
    asr_service: Any | None = None,
    service_context: Any | None = None,
    storage: Any | None = None,
    user_id: str | None = None,
    tts_service: Any | None = None,
    vision_state: WebSocketVisionState | None = None,
    vision_service: VisionService | None = None,
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
        await _wait_for_committing_generation(vad_state)
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
                tts_service=tts_service,
                vision_state=vision_state,
                vision_service=vision_service,
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
    tts_service: Any | None = None,
    vision_state: WebSocketVisionState | None = None,
    vision_service: VisionService | None = None,
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

    async def run_chat_generation() -> None:
        image: InputImage | None = None
        try:
            if vision_state is not None and vision_service is not None:
                image = await _capture_image_for_generation(
                    websocket,
                    vad_state,
                    vision_state,
                    vision_service,
                    generation_id=generation_id,
                    chat_id=chat_id,
                    character_id=character_id,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "VAD chat capture orchestration failed | chat_id={} | character_id={} | "
                "generation_id={} | error_type={}",
                chat_id,
                character_id,
                generation_id,
                type(exc).__name__,
            )
            await _send_generation_failure(
                websocket,
                vad_state,
                chat_id=chat_id,
                character_id=character_id,
                generation_id=generation_id,
            )
            return
        await _handle_text_input(
            websocket,
            message,
            service_context,
            storage,
            user_id,
            vad_state,
            generation_id,
            tts_service=tts_service,
            vision_state=vision_state,
            vision_service=vision_service,
            input_image=image,
        )

    started = _start_tracked_chat_task(
        vad_state,
        generation_id,
        run_chat_generation(),
    )
    if not started:
        await _send_error(
            websocket,
            "Chat task already running",
            chat_id=chat_id,
            generation_id=generation_id,
        )


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


async def _send_error(
    websocket: WebSocket,
    message: str,
    chat_id: str | None,
    generation_id: str | None = None,
    character_id: str | None = None,
    request_id: str | None = None,
) -> None:
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
    if generation_id:
        error_data["generation_id"] = generation_id
    if character_id:
        error_data["character_id"] = character_id
    if request_id:
        error_data["request_id"] = request_id

    await _send_json(websocket, {"type": "error", "data": error_data})
