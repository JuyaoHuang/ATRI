"""Application-level segmented TTS synthesis manager."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from loguru import logger

from .sentence_divider import SentenceDivider, TTSTextSegment
from .service import TTSService


@dataclass(frozen=True)
class TTSSegmentManagerConfig:
    """Runtime options for segmented TTS synthesis."""

    segment_method: str = "pysbd"
    faster_first_response: bool = True
    max_concurrent_synthesis: int = 2
    max_pending_segments: int = 12
    language: str = "zh"

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any] | None) -> TTSSegmentManagerConfig:
        if not config:
            return cls()

        return cls(
            segment_method=str(config.get("segment_method") or "pysbd"),
            faster_first_response=bool(config.get("faster_first_response", True)),
            max_concurrent_synthesis=_positive_int(
                config.get("max_concurrent_synthesis"),
                default=2,
            ),
            max_pending_segments=_positive_int(
                config.get("max_pending_segments"),
                default=12,
            ),
            language=str(config.get("language") or "zh"),
        )


@dataclass(frozen=True)
class TTSAudioSegment:
    """A synthesized audio segment ready to send over WebSocket."""

    chat_id: str
    character_id: str
    generation_id: str
    segment_id: str
    sequence: int
    display_text: str
    tts_text: str
    audio: bytes
    media_type: str


@dataclass(frozen=True)
class TTSAudioComplete:
    """Completion marker for all TTS segments in a generation."""

    chat_id: str
    character_id: str
    generation_id: str
    last_sequence: int | None


@dataclass(frozen=True)
class TTSAudioError:
    """Per-segment TTS synthesis or delivery error."""

    chat_id: str
    character_id: str
    generation_id: str
    segment_id: str
    sequence: int
    code: str
    message: str


SendSegment = Callable[[TTSAudioSegment], Awaitable[None]]
SendComplete = Callable[[TTSAudioComplete], Awaitable[None]]
SendError = Callable[[TTSAudioError], Awaitable[None]]


class TTSSegmentManager:
    """Coordinate sentence segmentation, TTS synthesis, and ordered delivery."""

    def __init__(
        self,
        *,
        tts_service: TTSService,
        chat_id: str,
        character_id: str,
        generation_id: str,
        config: TTSSegmentManagerConfig | Mapping[str, Any] | None,
        send_segment: SendSegment,
        send_complete: SendComplete,
        send_error: SendError,
        provider: str | None = None,
        voice_id: str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> None:
        manager_config = (
            config
            if isinstance(config, TTSSegmentManagerConfig)
            else TTSSegmentManagerConfig.from_mapping(config)
        )
        self.chat_id = chat_id
        self.character_id = character_id
        self.generation_id = generation_id
        self._tts_service = tts_service
        self._config = manager_config
        self._send_segment = send_segment
        self._send_complete = send_complete
        self._send_error = send_error
        self._provider = provider
        self._voice_id = voice_id
        self._options = dict(options or {})

        self._divider = SentenceDivider(
            language=manager_config.language,
            faster_first_response=manager_config.faster_first_response,
            segment_method=manager_config.segment_method,
        )
        self._semaphore = asyncio.Semaphore(manager_config.max_concurrent_synthesis)
        self._lock = asyncio.Lock()
        self._pending_tasks: set[asyncio.Task[None]] = set()
        self._completed_segments: dict[int, TTSAudioSegment] = {}
        self._skipped_sequences: set[int] = set()
        self._next_sequence_to_send = 0
        self._last_sequence_seen: int | None = None
        self._interrupted = False
        self._closed = False
        self._complete_sent = False

    @property
    def interrupted(self) -> bool:
        """Return whether this manager has been invalidated."""

        return self._interrupted or self._closed

    async def feed_text(self, chunk: str) -> None:
        """Consume a just-sent LLM chunk and schedule any new TTS segments."""

        if self.interrupted:
            return

        for segment in self._divider.feed(chunk):
            await self._schedule_or_skip(segment)

    async def finish(self) -> None:
        """Flush remaining text, await synthesis tasks, and send completion."""

        if self.interrupted:
            return

        for segment in self._divider.flush():
            await self._schedule_or_skip(segment)

        await self._wait_for_pending_tasks()
        async with self._lock:
            if self.interrupted or self._complete_sent:
                return
            await self._drain_ready_locked()
            if self.interrupted or self._complete_sent:
                return
            await self._send_complete(
                TTSAudioComplete(
                    chat_id=self.chat_id,
                    character_id=self.character_id,
                    generation_id=self.generation_id,
                    last_sequence=self._last_sequence_seen,
                )
            )
            self._complete_sent = True

    async def interrupt(self) -> None:
        """Invalidate this generation and cancel queued segment work."""

        await self._stop(interrupted=True)

    async def close(self) -> None:
        """Close this manager because its owning WebSocket is ending."""

        await self._stop(interrupted=False)

    async def _schedule_or_skip(self, segment: TTSTextSegment) -> None:
        async with self._lock:
            if self.interrupted:
                return
            self._last_sequence_seen = segment.sequence
            pending_count = segment.sequence - self._next_sequence_to_send + 1

        if pending_count > self._config.max_pending_segments:
            await self._skip_segment(
                segment,
                code="tts_segment_queue_full",
                message="TTS segment queue is full.",
            )
            return

        task = asyncio.create_task(self._synthesize_segment(segment))
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    async def _synthesize_segment(self, segment: TTSTextSegment) -> None:
        try:
            async with self._semaphore:
                if self.interrupted:
                    return
                result = await self._tts_service.synthesize(
                    segment.tts_text,
                    provider=self._provider,
                    voice_id=self._voice_id,
                    options=self._options,
                )
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            logger.warning(
                "TTS segment synthesis failed | chat_id={} | generation_id={} "
                "| sequence={} | error={!r}",
                self.chat_id,
                self.generation_id,
                segment.sequence,
                error,
            )
            await self._skip_segment(
                segment,
                code="tts_synthesis_failed",
                message=str(error),
            )
            return

        audio = result.get("audio")
        if not isinstance(audio, bytes):
            await self._skip_segment(
                segment,
                code="tts_invalid_audio",
                message="TTS service returned invalid audio payload.",
            )
            return

        audio_segment = TTSAudioSegment(
            chat_id=self.chat_id,
            character_id=self.character_id,
            generation_id=self.generation_id,
            segment_id=segment.segment_id,
            sequence=segment.sequence,
            display_text=segment.display_text,
            tts_text=segment.tts_text,
            audio=audio,
            media_type=str(result.get("media_type") or "application/octet-stream"),
        )
        async with self._lock:
            if self.interrupted:
                return
            self._completed_segments[segment.sequence] = audio_segment
            await self._drain_ready_locked()

    async def _skip_segment(self, segment: TTSTextSegment, *, code: str, message: str) -> None:
        async with self._lock:
            if self.interrupted:
                return
            self._skipped_sequences.add(segment.sequence)
            error = TTSAudioError(
                chat_id=self.chat_id,
                character_id=self.character_id,
                generation_id=self.generation_id,
                segment_id=segment.segment_id,
                sequence=segment.sequence,
                code=code,
                message=message,
            )
            await self._send_error(error)
            await self._drain_ready_locked()

    async def _drain_ready_locked(self) -> None:
        while not self.interrupted:
            if self._next_sequence_to_send in self._skipped_sequences:
                self._skipped_sequences.remove(self._next_sequence_to_send)
                self._next_sequence_to_send += 1
                continue

            segment = self._completed_segments.pop(self._next_sequence_to_send, None)
            if segment is None:
                return

            try:
                await self._send_segment(segment)
            except Exception as error:  # noqa: BLE001
                logger.warning(
                    "TTS segment delivery failed | chat_id={} | generation_id={} "
                    "| sequence={} | error={!r}",
                    self.chat_id,
                    self.generation_id,
                    segment.sequence,
                    error,
                )
                await self._stop_locked(interrupted=True)
                return
            self._next_sequence_to_send += 1

    async def _wait_for_pending_tasks(self) -> None:
        while self._pending_tasks:
            tasks = list(self._pending_tasks)
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _stop(self, *, interrupted: bool) -> None:
        async with self._lock:
            await self._stop_locked(interrupted=interrupted)

    async def _stop_locked(self, *, interrupted: bool) -> None:
        self._interrupted = self._interrupted or interrupted
        self._closed = self._closed or not interrupted
        self._completed_segments.clear()
        self._skipped_sequences.clear()
        self._divider.reset()
        tasks = list(self._pending_tasks)
        self._pending_tasks.clear()
        for task in tasks:
            if not task.done():
                task.cancel()


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
