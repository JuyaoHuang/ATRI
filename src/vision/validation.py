"""Bounded validation for short-lived visual input payloads.

短生命周期视觉输入载荷的有界校验。
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from .models import InputImage

ImageValidationCode = Literal[
    "ok",
    "missing",
    "not_object",
    "invalid_source",
    "invalid_media_type",
    "invalid_encoding",
    "invalid_data",
    "encoded_too_large",
    "invalid_base64",
    "decoded_too_large",
    "invalid_jpeg",
]


@dataclass(frozen=True, slots=True)
class InputImageValidationResult:
    """Safe validation outcome that never exposes the image payload in repr."""

    code: ImageValidationCode
    image: InputImage | None = field(default=None, repr=False)
    encoded_length: int = 0
    decoded_length: int = 0

    @property
    def is_valid(self) -> bool:
        return self.code == "ok" and self.image is not None


def maximum_base64_length(max_decoded_bytes: int) -> int:
    """Return the largest canonical Base64 length for the decoded byte budget."""

    if type(max_decoded_bytes) is not int or max_decoded_bytes <= 0:
        raise ValueError("max_decoded_bytes must be a positive integer")
    return 4 * ((max_decoded_bytes + 2) // 3)


def websocket_message_size_bytes(message: str) -> int:
    """Return the UTF-8 byte size used by the application-level frame guard."""

    if not isinstance(message, str):
        raise TypeError("WebSocket text message must be a string")
    return len(message.encode("utf-8"))


def websocket_message_within_limit(message: str, max_message_bytes: int) -> bool:
    """Check a WebSocket text frame without logging or returning its content."""

    if type(max_message_bytes) is not int or max_message_bytes <= 0:
        raise ValueError("max_message_bytes must be a positive integer")
    return websocket_message_size_bytes(message) <= max_message_bytes


def validate_input_image(
    payload: object,
    *,
    max_decoded_bytes: int,
) -> InputImageValidationResult:
    """Validate one raw image mapping in a fixed, allocation-bounded order.

    The Base64 string is length-checked before strict decoding. Failures return
    a short status code and integer lengths only; raw input and decoder errors
    never cross this boundary.
    """

    max_encoded_length = maximum_base64_length(max_decoded_bytes)
    if payload is None:
        return InputImageValidationResult(code="missing")
    if not isinstance(payload, Mapping):
        return InputImageValidationResult(code="not_object")
    if payload.get("source") != "screen":
        return InputImageValidationResult(code="invalid_source")
    if payload.get("media_type") != "image/jpeg":
        return InputImageValidationResult(code="invalid_media_type")
    if payload.get("encoding") != "base64":
        return InputImageValidationResult(code="invalid_encoding")

    data = payload.get("data")
    if not isinstance(data, str) or not data:
        return InputImageValidationResult(code="invalid_data")

    encoded_length = len(data)
    if encoded_length > max_encoded_length:
        return InputImageValidationResult(
            code="encoded_too_large",
            encoded_length=encoded_length,
        )

    try:
        decoded = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return InputImageValidationResult(
            code="invalid_base64",
            encoded_length=encoded_length,
        )

    decoded_length = len(decoded)
    if decoded_length > max_decoded_bytes:
        return InputImageValidationResult(
            code="decoded_too_large",
            encoded_length=encoded_length,
            decoded_length=decoded_length,
        )
    if not _has_basic_jpeg_signature(decoded):
        return InputImageValidationResult(
            code="invalid_jpeg",
            encoded_length=encoded_length,
            decoded_length=decoded_length,
        )

    del decoded
    image = InputImage(
        source="screen",
        media_type="image/jpeg",
        encoding="base64",
        data=data,
    )
    return InputImageValidationResult(
        code="ok",
        image=image,
        encoded_length=encoded_length,
        decoded_length=decoded_length,
    )


def _has_basic_jpeg_signature(data: bytes) -> bool:
    return len(data) >= 5 and data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")
