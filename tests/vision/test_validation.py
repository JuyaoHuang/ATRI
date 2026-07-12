"""Tests for bounded visual payload validation."""

from __future__ import annotations

import base64
from unittest.mock import Mock

import pytest

from src.vision import (
    maximum_base64_length,
    validate_input_image,
    websocket_message_size_bytes,
    websocket_message_within_limit,
)

_JPEG_BYTES = b"\xff\xd8\xff\xe0safe-fixture\xff\xd9"


def _payload(data: str | None = None) -> dict[str, object]:
    return {
        "source": "screen",
        "media_type": "image/jpeg",
        "encoding": "base64",
        "data": data if data is not None else base64.b64encode(_JPEG_BYTES).decode("ascii"),
    }


def test_valid_jpeg_constructs_safe_input_image() -> None:
    payload = _payload()
    result = validate_input_image(payload, max_decoded_bytes=1024)

    assert result.is_valid is True
    assert result.code == "ok"
    assert result.image is not None
    assert result.image.data == payload["data"]
    assert payload["data"] not in repr(result)


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        (None, "missing"),
        ("not-an-object", "not_object"),
        ({**_payload(), "source": "camera"}, "invalid_source"),
        ({**_payload(), "media_type": "image/png"}, "invalid_media_type"),
        ({**_payload(), "encoding": "binary"}, "invalid_encoding"),
        ({**_payload(), "data": ""}, "invalid_data"),
        ({**_payload(), "data": 123}, "invalid_data"),
        (_payload("not valid base64"), "invalid_base64"),
        (_payload(base64.b64encode(b"not-a-jpeg").decode("ascii")), "invalid_jpeg"),
    ],
)
def test_invalid_payload_returns_safe_code(payload: object, expected_code: str) -> None:
    result = validate_input_image(payload, max_decoded_bytes=1024)

    assert result.is_valid is False
    assert result.code == expected_code
    assert result.image is None


def test_encoded_length_is_checked_before_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    decode = Mock(side_effect=AssertionError("decode must not run"))
    monkeypatch.setattr("src.vision.validation.base64.b64decode", decode)
    oversized = "A" * (maximum_base64_length(4) + 1)

    result = validate_input_image(_payload(oversized), max_decoded_bytes=4)

    assert result.code == "encoded_too_large"
    assert result.encoded_length == len(oversized)
    decode.assert_not_called()


def test_decoded_length_is_checked_after_strict_decode() -> None:
    five_bytes = base64.b64encode(b"12345").decode("ascii")

    result = validate_input_image(_payload(five_bytes), max_decoded_bytes=4)

    assert result.code == "decoded_too_large"
    assert result.decoded_length == 5


def test_websocket_message_limit_uses_utf8_bytes() -> None:
    assert websocket_message_size_bytes("图") == 3
    assert websocket_message_within_limit("图", 3) is True
    assert websocket_message_within_limit("图", 2) is False


@pytest.mark.parametrize("value", [0, -1, True])
def test_positive_size_limits_are_required(value: int) -> None:
    with pytest.raises(ValueError):
        maximum_base64_length(value)
    with pytest.raises(ValueError):
        websocket_message_within_limit("payload", value)
