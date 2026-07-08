"""Sentence segmentation for application-level TTS streaming."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pysbd

SENTENCE_END_CHARS = frozenset("。！？!?…．.｡")
FIRST_RESPONSE_BREAK_CHARS = frozenset("，,、､；;：:")
NON_SPEECH_CHARS = frozenset(" \t\r\n　，,、､。｡！？!?；;：:…‥“”\"'‘’（）()[]【】{}<>《》-_—~·.．")


@dataclass(frozen=True)
class TTSTextSegment:
    """A text span ready for one TTS synthesis request."""

    segment_id: str
    sequence: int
    display_text: str
    tts_text: str


class SentenceDivider:
    """Accumulate LLM chunks and emit sentence-like TTS text segments."""

    def __init__(
        self,
        *,
        language: str = "zh",
        faster_first_response: bool = True,
        segment_method: str = "pysbd",
    ) -> None:
        if segment_method != "pysbd":
            raise ValueError(f"Unsupported TTS segment method: {segment_method}")
        self._segmenter = pysbd.Segmenter(language=language, clean=False)
        self._faster_first_response = faster_first_response
        self._buffer = ""
        self._next_sequence = 0
        self._first_segment_emitted = False

    @property
    def buffer(self) -> str:
        """Return buffered text not yet emitted as a segment."""

        return self._buffer

    def feed(self, chunk: str) -> list[TTSTextSegment]:
        """Append a new LLM chunk and return newly complete text segments."""

        if not chunk:
            return []

        self._buffer += chunk
        segments: list[TTSTextSegment] = []

        first_segment = self._take_first_response_segment()
        if first_segment is not None:
            segments.append(first_segment)

        segments.extend(self._take_complete_sentence_segments())
        return segments

    def flush(self) -> list[TTSTextSegment]:
        """Emit the remaining buffered text, if it contains speakable content."""

        text = self._buffer.strip()
        self._buffer = ""
        if not _has_speakable_text(text):
            return []
        return [self._make_segment(text)]

    def reset(self) -> None:
        """Clear buffered text and restart sequence numbering."""

        self._buffer = ""
        self._next_sequence = 0
        self._first_segment_emitted = False

    def _take_first_response_segment(self) -> TTSTextSegment | None:
        if self._first_segment_emitted or not self._faster_first_response:
            return None

        for index, character in enumerate(self._buffer):
            if character not in FIRST_RESPONSE_BREAK_CHARS:
                continue

            candidate = self._buffer[: index + 1].strip()
            if not _has_speakable_text(candidate):
                continue

            self._buffer = self._buffer[index + 1 :].lstrip()
            return self._make_segment(candidate)

        return None

    def _take_complete_sentence_segments(self) -> list[TTSTextSegment]:
        if not self._buffer.strip():
            return []

        raw_segments = self._segmenter.segment(self._buffer)
        emitted: list[str] = []
        consumed_chars = 0

        for raw_segment in raw_segments:
            segment = raw_segment.strip()
            if not segment:
                consumed_chars += len(raw_segment)
                continue

            if not _ends_with_sentence_boundary(segment):
                break

            consumed_chars += len(raw_segment)
            if _has_speakable_text(segment):
                emitted.append(segment)

        if consumed_chars > 0:
            self._buffer = self._buffer[consumed_chars:].lstrip()

        return [self._make_segment(segment) for segment in emitted]

    def _make_segment(self, text: str) -> TTSTextSegment:
        self._first_segment_emitted = True
        segment = TTSTextSegment(
            segment_id=uuid4().hex,
            sequence=self._next_sequence,
            display_text=text,
            tts_text=text,
        )
        self._next_sequence += 1
        return segment


def _ends_with_sentence_boundary(text: str) -> bool:
    return bool(text) and text[-1] in SENTENCE_END_CHARS


def _has_speakable_text(text: str) -> bool:
    return any(character not in NON_SPEECH_CHARS for character in text)
