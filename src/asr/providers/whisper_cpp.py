"""whisper.cpp ASR provider via pywhispercpp.

通过 pywhispercpp 的 whisper.cpp ASR 提供商模块。

Provides local transcription using the whisper.cpp engine wrapped by
the ``pywhispercpp`` Python package.  The model is lazily loaded on
first use.

使用 ``pywhispercpp`` Python 包封装的 whisper.cpp 引擎提供本地转录。
模型在首次使用时延迟加载。

Reference: docs/ASR模块设计文档.md
"""

from __future__ import annotations

import importlib.util
from typing import Any

from loguru import logger

from src.asr.exceptions import ASRProviderUnavailableError
from src.asr.factory import ASRFactory, ASRProviderMetadata
from src.asr.interface import ASRHealth, ASRInterface


@ASRFactory.register(
    "whisper_cpp",
    metadata=ASRProviderMetadata(
        name="whisper_cpp",
        display_name="Whisper.cpp",
        provider_type="local",
        supports_backend_transcription=True,
        supports_browser_streaming=False,
        description="Local pywhispercpp transcription compatible with OLV flow.",
    ),
)
class WhisperCppASR(ASRInterface):
    """Local whisper.cpp provider with lazy optional dependency loading.

    本地 whisper.cpp 提供商，延迟加载可选依赖。

    The underlying ``pywhispercpp.model.Model`` is created on first
    transcription so that importing this module does not require the
    ``pywhispercpp`` package to be installed.

    底层 ``pywhispercpp.model.Model`` 在首次转录时创建，因此导入此模块不要求
    安装 ``pywhispercpp`` 包。
    """

    def __init__(self, **config: Any) -> None:
        super().__init__(**config)
        self.model_name = str(config.get("model_name") or "small")
        self.model_dir = str(config.get("model_dir") or "models/whisper")
        self.language = str(config.get("language") or "auto")
        self.print_realtime = bool(config.get("print_realtime", False))
        self.print_progress = bool(config.get("print_progress", False))
        self.prompt = config.get("prompt") or None
        self._model: Any | None = None

    def health(self) -> ASRHealth:
        if importlib.util.find_spec("pywhispercpp") is None:
            return ASRHealth(False, "Python package 'pywhispercpp' is not installed")
        if not self.model_name:
            return ASRHealth(False, "whisper_cpp.model_name is not configured")
        return ASRHealth(True)

    def transcribe_np(self, audio: Any) -> str:
        """Transcribe a float32 numpy audio array using whisper.cpp.

        使用 whisper.cpp 转录 float32 numpy 音频数组。

        Segments are concatenated into a single string.  An optional
        ``initial_prompt`` is passed to guide the model.

        分段结果拼接为单个字符串。可选的 ``initial_prompt`` 用于引导模型。
        """
        model = self._get_model()
        kwargs: dict[str, Any] = {"new_segment_callback": logger.info}
        if self.prompt:
            kwargs["initial_prompt"] = self.prompt

        segments = model.transcribe(audio, **kwargs)
        return "".join(segment.text for segment in segments)

    def preload(self) -> None:
        """Load the whisper.cpp model without transcribing audio."""

        # 复用懒加载入口，让常驻模式提前完成模型初始化。
        self._get_model()

    def _get_model(self) -> Any:
        health = self.health()
        if not health.available:
            raise ASRProviderUnavailableError(health.reason or "whisper_cpp is unavailable")

        from pywhispercpp.model import Model

        if self._model is None:
            self._model = Model(
                model=self.model_name,
                models_dir=self.model_dir,
                language=self.language,
                print_realtime=self.print_realtime,
                print_progress=self.print_progress,
            )
        return self._model
