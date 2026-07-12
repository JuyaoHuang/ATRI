"""Short-lived visual input domain models.

短生命周期视觉输入领域模型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class InputText:
    """Final text for one user turn.

    一轮用户输入的最终文本。
    """

    content: str

    def __post_init__(self) -> None:
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("InputText content must be a non-empty string")


@dataclass(frozen=True, slots=True)
class InputImage:
    """One JPEG frame captured from the active screen-sharing stream.

    从当前屏幕共享流截取的一张 JPEG 静态图片。
    """

    source: Literal["screen"]
    media_type: Literal["image/jpeg"]
    encoding: Literal["base64"]
    data: str = field(repr=False)

    def __post_init__(self) -> None:
        if self.source != "screen":
            raise ValueError("InputImage source must be 'screen'")
        if self.media_type != "image/jpeg":
            raise ValueError("InputImage media_type must be 'image/jpeg'")
        if self.encoding != "base64":
            raise ValueError("InputImage encoding must be 'base64'")
        if not isinstance(self.data, str) or not self.data:
            raise ValueError("InputImage data must be a non-empty string")


@dataclass(frozen=True, slots=True)
class InputInform:
    """Complete user information passed to the LLM invocation boundary.

    传给 LLM 调用边界的一轮完整用户信息。
    """

    input_text: InputText
    image: InputImage | None = None

    @classmethod
    def text_only(cls, content: str) -> InputInform:
        """Build a text-only turn without a visual attachment."""

        return cls(input_text=InputText(content=content))
