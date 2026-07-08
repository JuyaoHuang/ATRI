import asyncio
from collections.abc import Mapping
from typing import Any

import pytest

from src.tts.segment_manager import (
    TTSAudioComplete,
    TTSAudioError,
    TTSAudioSegment,
    TTSSegmentManager,
    TTSSegmentManagerConfig,
)


class FakeTTSService:
    def __init__(
        self,
        *,
        delays: Mapping[str, float] | None = None,
        failures: set[str] | None = None,
    ) -> None:
        self.delays = dict(delays or {})
        self.failures = failures or set()
        self.calls: list[str] = []

    async def synthesize(
        self,
        text: str,
        *,
        provider: str | None = None,
        voice_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(text)
        await asyncio.sleep(self.delays.get(text, 0))
        if text in self.failures:
            raise RuntimeError(f"boom: {text}")
        return {
            "provider": provider or "fake",
            "audio": f"audio:{text}".encode(),
            "media_type": "audio/mpeg",
        }


class BlockingTTSService(FakeTTSService):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def synthesize(
        self,
        text: str,
        *,
        provider: str | None = None,
        voice_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(text)
        self.started.set()
        await self.release.wait()
        return {
            "provider": provider or "fake",
            "audio": f"audio:{text}".encode(),
            "media_type": "audio/mpeg",
        }


@pytest.mark.asyncio
async def test_segment_manager_sends_single_audio_segment() -> None:
    service = FakeTTSService()
    sent, complete, errors = _events()
    manager = _manager(service, sent, complete, errors)

    await manager.feed_text("你好。")
    await manager.finish()

    assert [item.tts_text for item in sent] == ["你好。"]
    assert sent[0].audio == b"audio:\xe4\xbd\xa0\xe5\xa5\xbd\xe3\x80\x82"
    assert [item.last_sequence for item in complete] == [0]
    assert errors == []


@pytest.mark.asyncio
async def test_segment_manager_preserves_sequence_when_synthesis_finishes_out_of_order() -> None:
    service = FakeTTSService(delays={"第一句。": 0.02, "第二句。": 0})
    sent, complete, errors = _events()
    manager = _manager(service, sent, complete, errors)

    await manager.feed_text("第一句。第二句。")
    await manager.finish()

    assert [item.tts_text for item in sent] == ["第一句。", "第二句。"]
    assert [item.sequence for item in sent] == [0, 1]
    assert [item.last_sequence for item in complete] == [1]
    assert errors == []


@pytest.mark.asyncio
async def test_segment_manager_interrupt_discards_late_provider_result() -> None:
    service = BlockingTTSService()
    sent, complete, errors = _events()
    manager = _manager(service, sent, complete, errors)

    await manager.feed_text("第一句。")
    await service.started.wait()
    await manager.interrupt()
    service.release.set()
    await manager.finish()

    assert sent == []
    assert complete == []
    assert errors == []


@pytest.mark.asyncio
async def test_segment_manager_sends_error_and_skips_failed_segment() -> None:
    service = FakeTTSService(failures={"第一句。"})
    sent, complete, errors = _events()
    manager = _manager(service, sent, complete, errors)

    await manager.feed_text("第一句。第二句。")
    await manager.finish()

    assert [item.sequence for item in errors] == [0]
    assert errors[0].code == "tts_synthesis_failed"
    assert [item.tts_text for item in sent] == ["第二句。"]
    assert [item.sequence for item in sent] == [1]
    assert [item.last_sequence for item in complete] == [1]


@pytest.mark.asyncio
async def test_segment_manager_finish_flushes_remaining_text() -> None:
    service = FakeTTSService()
    sent, complete, errors = _events()
    manager = _manager(service, sent, complete, errors)

    await manager.feed_text("还有半句")
    await manager.finish()

    assert [item.tts_text for item in sent] == ["还有半句"]
    assert [item.last_sequence for item in complete] == [0]
    assert errors == []


def _events() -> tuple[list[TTSAudioSegment], list[TTSAudioComplete], list[TTSAudioError]]:
    return [], [], []


def _manager(
    service: FakeTTSService,
    sent: list[TTSAudioSegment],
    complete: list[TTSAudioComplete],
    errors: list[TTSAudioError],
) -> TTSSegmentManager:
    async def send_segment(segment: TTSAudioSegment) -> None:
        sent.append(segment)

    async def send_complete(event: TTSAudioComplete) -> None:
        complete.append(event)

    async def send_error(error: TTSAudioError) -> None:
        errors.append(error)

    return TTSSegmentManager(
        tts_service=service,  # type: ignore[arg-type]
        chat_id="chat-a",
        character_id="atri",
        generation_id="gen-a",
        config=TTSSegmentManagerConfig(faster_first_response=False),
        send_segment=send_segment,
        send_complete=send_complete,
        send_error=send_error,
    )
