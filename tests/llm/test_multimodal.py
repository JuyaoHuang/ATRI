"""Tests for pure OpenAI-compatible multimodal message serialization."""

from __future__ import annotations

from copy import deepcopy

import pytest

from src.llm.multimodal import build_multimodal_messages
from src.vision import InputImage

_OPAQUE_DATA = "c21hbGwtaW1hZ2U="


def _image() -> InputImage:
    return InputImage(
        source="screen",
        media_type="image/jpeg",
        encoding="base64",
        data=_OPAQUE_DATA,
    )


def test_no_image_returns_original_messages_without_copy() -> None:
    messages = [{"role": "user", "content": "hello"}]

    result = build_multimodal_messages(messages, None, image_detail="auto")

    assert result is messages


def test_only_final_current_user_message_is_multimodalized() -> None:
    messages = [
        {"role": "user", "content": "historical question"},
        {"role": "assistant", "content": "historical answer"},
        {"role": "user", "content": "current question", "name": "alice"},
    ]
    before = deepcopy(messages)

    result = build_multimodal_messages(messages, _image(), image_detail="high")

    assert messages == before
    assert result is not messages
    assert result[:2] == before[:2]
    assert result[-1]["name"] == "alice"
    content = result[-1]["content"]
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "current question"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["detail"] == "high"
    url = content[1]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    assert len(url) == len("data:image/jpeg;base64,") + len(_OPAQUE_DATA)


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [{"role": "assistant", "content": "not current user"}],
        [{"role": "user", "content": [{"type": "text", "text": "already structured"}]}],
    ],
)
def test_image_requires_final_string_user_message(messages: list[dict[str, object]]) -> None:
    with pytest.raises(ValueError):
        build_multimodal_messages(messages, _image(), image_detail="auto")


def test_unsupported_detail_is_rejected() -> None:
    with pytest.raises(ValueError, match="detail"):
        build_multimodal_messages(
            [{"role": "user", "content": "hello"}],
            _image(),
            image_detail="original",  # type: ignore[arg-type]
        )
