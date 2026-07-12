"""Tests for short-lived visual input domain models."""

from __future__ import annotations

import pytest

from src.vision import InputImage, InputInform, InputText


def test_input_inform_repr_never_contains_image_data() -> None:
    opaque_data = "opaque-image-payload-that-must-not-appear"
    image = InputImage(
        source="screen",
        media_type="image/jpeg",
        encoding="base64",
        data=opaque_data,
    )
    input_inform = InputInform(input_text=InputText("describe this screen"), image=image)

    assert opaque_data not in repr(image)
    assert opaque_data not in repr(input_inform)


def test_input_text_rejects_blank_content() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        InputText("   ")


def test_text_only_builds_input_without_image() -> None:
    input_inform = InputInform.text_only("hello")

    assert input_inform.input_text.content == "hello"
    assert input_inform.image is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source", "camera"),
        ("media_type", "image/png"),
        ("encoding", "binary"),
        ("data", ""),
    ],
)
def test_input_image_rejects_unsupported_shape(field: str, value: str) -> None:
    kwargs = {
        "source": "screen",
        "media_type": "image/jpeg",
        "encoding": "base64",
        "data": "opaque",
    }
    kwargs[field] = value

    with pytest.raises(ValueError):
        InputImage(**kwargs)  # type: ignore[arg-type]
