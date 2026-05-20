"""ASR provider interface.

ASR 提供商接口模块。

The core contract mirrors Open-LLM-VTuber's ASR flow: local providers
transcribe 16 kHz, mono, 16-bit PCM-style audio represented as a numeric
array, and the async method delegates sync model work to a worker thread.

核心契约镜像 Open-LLM-VTuber 的 ASR 流程：本地提供商转录 16 kHz、单声道、
16 位 PCM 风格的数字数组音频，异步方法将同步模型工作委托给工作线程。

Reference: docs/ASR模块设计文档.md
"""

from __future__ import annotations

import asyncio
import io
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .exceptions import ASRProviderUnavailableError, ASRTranscriptionError


@dataclass(frozen=True)
class ASRHealth:
    """Provider availability state.

    提供商可用性状态。

    Immutable data class returned by ``ASRInterface.health()`` to
    indicate whether a provider is ready to accept transcription
    requests.

    由 ``ASRInterface.health()`` 返回的不可变数据类，用于指示提供商是否准备好
    接受转录请求。
    """

    available: bool
    reason: str | None = None


class ASRInterface(ABC):
    """Base interface for all ASR providers.

    所有 ASR 提供商的基础接口。

    Subclasses must implement at least ``transcribe_np``.  The async
    wrappers delegate to a thread pool by default so providers only
    need to supply synchronous logic.

    子类必须至少实现 ``transcribe_np``。异步包装器默认委托给线程池，
    因此提供商只需提供同步逻辑。
    """

    SAMPLE_RATE = 16000
    NUM_CHANNELS = 1
    SAMPLE_WIDTH = 2

    provider_name = "unknown"
    supports_backend_transcription = True
    supports_browser_streaming = False

    def __init__(self, **config: Any) -> None:
        self.config = dict(config)

    async def async_transcribe_np(self, audio: Any) -> str:
        """Transcribe an OLV-style numeric audio array asynchronously.

        异步转录 OLV 风格的数字音频数组。

        Delegates to ``transcribe_np`` via ``asyncio.to_thread``.

        通过 ``asyncio.to_thread`` 委托给 ``transcribe_np``。
        """

        audio = self._ensure_float32_array(audio)
        return await asyncio.to_thread(self.transcribe_np, audio)

    @abstractmethod
    def transcribe_np(self, audio: Any) -> str:
        """Transcribe a 16 kHz mono float32 audio array.

        转录 16 kHz 单声道 float32 音频数组。

        This is the core synchronous contract that every local provider
        must implement.

        这是每个本地提供商必须实现的核心同步契约。
        """

    async def async_transcribe_audio(
        self,
        audio: bytes,
        *,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> str:
        """Transcribe uploaded audio bytes.

        转录上传的音频字节。

        The default path converts 16 kHz mono PCM WAV bytes into the OLV
        numeric-array contract and then calls :meth:`async_transcribe_np`.
        Providers that can decode other formats should override this method.

        默认路径将 16 kHz 单声道 PCM WAV 字节转换为 OLV 数字数组格式，
        然后调用 :meth:`async_transcribe_np`。能解码其他格式的提供商应覆盖此方法。
        """

        if not audio:
            raise ASRTranscriptionError("Uploaded audio is empty")
        audio_array = self.audio_bytes_to_float32_array(
            audio,
            filename=filename,
            content_type=content_type,
        )
        return await self.async_transcribe_np(audio_array)

    def health(self) -> ASRHealth:
        """Return provider availability without doing heavyweight model work.

        返回提供商可用性状态，不执行重量级模型加载操作。

        The default implementation always returns ``available=True``.
        Subclasses should override this to check for missing dependencies
        or misconfigured credentials.

        默认实现始终返回 ``available=True``。子类应覆盖此方法以检查缺失的依赖
        或未正确配置的凭证。
        """

        return ASRHealth(available=True)

    def _ensure_float32_array(self, audio: Any) -> Any:
        try:
            import numpy as np
        except ImportError as error:
            raise ASRProviderUnavailableError(
                "numpy is required for local ASR array transcription"
            ) from error

        if not isinstance(audio, np.ndarray):
            audio = np.asarray(audio)
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        return audio

    def audio_bytes_to_float32_array(
        self,
        audio: bytes,
        *,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> Any:
        """Convert a PCM WAV upload into an OLV-style float32 mono array.

        将 PCM WAV 上传转换为 OLV 风格的 float32 单声道数组。

        Supports 8-bit, 16-bit, and 32-bit WAV.  Multi-channel audio is
        down-mixed to mono by averaging channels.

        支持 8 位、16 位和 32 位 WAV。多声道音频通过取各声道平均值降混为单声道。
        """

        try:
            import numpy as np
        except ImportError as error:
            raise ASRProviderUnavailableError(
                "numpy is required to decode WAV audio for local ASR providers"
            ) from error

        if not self._looks_like_wav(audio, filename=filename, content_type=content_type):
            raise ASRTranscriptionError(
                "Only PCM WAV uploads can be converted by the default ASR adapter"
            )

        try:
            with wave.open(io.BytesIO(audio), "rb") as wav:
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                sample_rate = wav.getframerate()
                frames = wav.readframes(wav.getnframes())
        except wave.Error as error:
            raise ASRTranscriptionError("Uploaded audio is not a valid WAV file") from error

        if sample_rate != self.SAMPLE_RATE:
            raise ASRTranscriptionError(
                f"Expected {self.SAMPLE_RATE} Hz WAV audio, got {sample_rate} Hz"
            )
        if sample_width not in {1, 2, 4}:
            raise ASRTranscriptionError(f"Unsupported WAV sample width: {sample_width}")
        if channels < 1:
            raise ASRTranscriptionError("WAV audio must contain at least one channel")

        if sample_width == 1:
            samples = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        elif sample_width == 2:
            samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        else:
            samples = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0

        if channels > 1:
            samples = samples.reshape(-1, channels).mean(axis=1)

        return np.clip(samples, -1.0, 1.0).astype(np.float32)

    def nparray_to_audio_file(self, audio: Any, sample_rate: int, file_path: str) -> None:
        """Write a numeric audio array as a mono 16-bit PCM WAV file.

        将数字音频数组写入为单声道 16 位 PCM WAV 文件。

        Values are clipped to [-1, 1] and scaled to int16 range before
        writing.

        写入前将值裁剪到 [-1, 1] 范围并缩放到 int16 范围。
        """

        try:
            import numpy as np
        except ImportError as error:
            raise ASRProviderUnavailableError("numpy is required to write ASR WAV audio") from error

        audio = np.clip(self._ensure_float32_array(audio), -1, 1)
        audio_integer = (audio * 32767).astype(np.int16)

        with wave.open(file_path, "wb") as wav:
            wav.setnchannels(self.NUM_CHANNELS)
            wav.setsampwidth(self.SAMPLE_WIDTH)
            wav.setframerate(sample_rate)
            wav.writeframes(audio_integer.tobytes())

    def _looks_like_wav(
        self,
        audio: bytes,
        *,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> bool:
        if audio.startswith(b"RIFF") and b"WAVE" in audio[:16]:
            return True
        if content_type in {"audio/wav", "audio/wave", "audio/x-wav"}:
            return True
        return bool(filename and filename.lower().endswith(".wav"))
