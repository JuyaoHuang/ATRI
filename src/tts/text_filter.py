"""Text filtering helpers for AI-reply TTS synthesis."""

from __future__ import annotations

import re

_PARENTHETICAL_PATTERNS = (
    re.compile(r"（[^（）]*）"),
    re.compile(r"\([^()]*\)"),
    re.compile(r"\[[^\[\]]*\]"),
    re.compile(r"【[^【】]*】"),
)


def clean_ai_reply_text_for_tts(text: str) -> str:
    """Remove non-spoken AI action annotations before TTS synthesis."""

    stripped = _strip_parenthetical_content(text)
    segments = [segment.strip() for segment in stripped.splitlines() if segment.strip()]
    return "".join(segments).strip()


def _strip_parenthetical_content(text: str) -> str:
    current = text
    while True:
        next_text = current
        for pattern in _PARENTHETICAL_PATTERNS:
            next_text = pattern.sub("", next_text)
        if next_text == current:
            return current
        current = next_text
