"""Voice activity detection module."""

from .config import DEFAULT_VAD_CONFIG, DEFAULT_VAD_CONFIG_PATH, VADConfigStore
from .exceptions import VADConfigError, VADError, VADProcessingError, VADProviderUnavailableError
from .factory import VADFactory, VADProviderMetadata
from .interface import VADEvent, VADEventType, VADHealth, VADInterface, VADResult, VADState
from .service import VADService
from .session import VADSession, VADSessionConfig

__all__ = [
    "DEFAULT_VAD_CONFIG",
    "DEFAULT_VAD_CONFIG_PATH",
    "VADEvent",
    "VADEventType",
    "VADConfigStore",
    "VADConfigError",
    "VADError",
    "VADFactory",
    "VADHealth",
    "VADInterface",
    "VADProcessingError",
    "VADProviderMetadata",
    "VADProviderUnavailableError",
    "VADResult",
    "VADService",
    "VADSession",
    "VADSessionConfig",
    "VADState",
]
