"""Vision module exceptions.

视觉模块异常。
"""

from __future__ import annotations


class VisionError(Exception):
    """Base exception for visual input operations.

    视觉输入操作的基础异常。
    """


class VisionConfigError(VisionError, ValueError):
    """Raised when visual configuration is invalid or not writable.

    视觉配置无效或不允许写入时抛出。
    """
