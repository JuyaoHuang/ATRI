"""Text-to-speech module."""

from .config import DEFAULT_TTS_CONFIG, DEFAULT_TTS_CONFIG_PATH, TTSConfigStore
from .factory import TTSFactory, TTSProviderMetadata
from .interface import TTSHealth, TTSInterface, TTSVoice
from .service import TTSService

__all__ = [
    "DEFAULT_TTS_CONFIG",
    "DEFAULT_TTS_CONFIG_PATH",
    "TTSConfigStore",
    "TTSFactory",
    "TTSHealth",
    "TTSInterface",
    "TTSProviderMetadata",
    "TTSService",
    "TTSVoice",
]
