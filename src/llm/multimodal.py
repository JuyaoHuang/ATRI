"""Pure helpers for one-image OpenAI-compatible user messages.

OpenAI 兼容单图用户消息的纯函数辅助模块。
"""

from __future__ import annotations

from typing import Any, Literal

from src.vision.models import InputImage

ImageDetail = Literal["auto", "low", "high"]
SUPPORTED_IMAGE_DETAILS: frozenset[str] = frozenset({"auto", "low", "high"})


def build_multimodal_messages(
    messages: list[dict[str, Any]],
    input_image: InputImage | None,
    *,
    image_detail: ImageDetail,
) -> list[dict[str, Any]]:
    """Copy and multimodalize only the final current user message.

    With no image, the original list is returned unchanged. With an image,
    the list and final user mapping are copied; historical messages and the
    caller-owned input remain untouched.
    """

    if input_image is None:
        return messages
    if image_detail not in SUPPORTED_IMAGE_DETAILS:
        raise ValueError(f"Unsupported image detail: {image_detail!r}")
    if not messages:
        raise ValueError("Cannot attach an image without a current user message")

    current_user = messages[-1]
    if current_user.get("role") != "user":
        raise ValueError("The final message must be the current user message")

    text = current_user.get("content")
    if not isinstance(text, str):
        raise ValueError("The current user message content must be a string")

    multimodal_user = dict(current_user)
    multimodal_user["content"] = [
        {"type": "text", "text": text},
        {
            "type": "image_url",
            "image_url": {
                "url": (f"data:{input_image.media_type};{input_image.encoding},{input_image.data}"),
                "detail": image_detail,
            },
        },
    ]
    return [*messages[:-1], multimodal_user]
