"""TTS-specific exception hierarchy.

TTS 异常层次结构。

Defines granular exceptions for configuration errors, provider availability,
synthesis failures, rate limiting, and upstream API errors.

定义了细粒度的异常，涵盖配置错误、提供商可用性、合成失败、速率限制和上游 API 错误。

Reference: docs/TTS模块设计文档.md
"""

from __future__ import annotations


class TTSError(Exception):
    """Base exception for TTS failures.

    TTS 失败的基类异常。
    """


class TTSConfigError(TTSError):
    """Raised when TTS configuration is invalid.

    当 TTS 配置无效时抛出。
    """


class TTSProviderUnavailableError(TTSError):
    """Raised when a selected TTS provider cannot be used.

    当所选的 TTS 提供商不可用时抛出。
    """


class TTSSynthesisError(TTSError):
    """Raised when text synthesis fails.

    当文本合成失败时抛出。
    """


class TTSRateLimitError(TTSSynthesisError):
    """Raised when an upstream TTS provider reports rate limiting.

    当上游 TTS 提供商报告速率限制时抛出。
    """


class TTSAPIError(TTSSynthesisError):
    """Raised when an upstream TTS provider returns an API error.

    当上游 TTS 提供商返回 API 错误时抛出。
    """
