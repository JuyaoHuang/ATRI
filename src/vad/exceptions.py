"""VAD-specific exception hierarchy."""

from __future__ import annotations


class VADError(Exception):
    """Base exception for VAD operations."""


class VADConfigError(VADError):
    """Raised when VAD configuration is invalid."""


class VADProviderUnavailableError(VADError):
    """Raised when a VAD provider cannot run because dependencies are missing."""


class VADProcessingError(VADError):
    """Raised when VAD processing fails after a provider was selected."""
