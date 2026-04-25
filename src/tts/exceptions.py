"""TTS-specific exception hierarchy."""

from __future__ import annotations


class TTSError(Exception):
    """Base exception for TTS failures."""


class TTSConfigError(TTSError):
    """Raised when TTS configuration is invalid."""


class TTSProviderUnavailableError(TTSError):
    """Raised when a selected TTS provider cannot be used."""


class TTSSynthesisError(TTSError):
    """Raised when text synthesis fails."""


class TTSRateLimitError(TTSSynthesisError):
    """Raised when an upstream TTS provider reports rate limiting."""


class TTSAPIError(TTSSynthesisError):
    """Raised when an upstream TTS provider returns an API error."""
