"""ASR-specific exception hierarchy.

ASR 异常层次结构模块。

Defines the exception classes used throughout the ASR subsystem,
organised in a hierarchy rooted at ``ASRError``.

定义 ASR 子系统使用的异常类，以 ``ASRError`` 为根组织层次结构。

Reference: docs/ASR模块设计文档.md
"""

from __future__ import annotations


class ASRError(Exception):
    """Base exception for ASR operations.

    ASR 操作的基础异常。

    All ASR-specific exceptions inherit from this class so callers can
    catch a single base type for any ASR-related failure.

    所有 ASR 特定异常均继承此类，调用方可以捕获单一基类来处理所有 ASR 相关故障。
    """


class ASRConfigError(ASRError):
    """Raised when ASR configuration is invalid.

    当 ASR 配置无效时抛出。

    Examples include missing required fields, referencing an unknown
    provider, or providing values of the wrong type.

    示例包括缺少必填字段、引用未知提供商或提供错误类型的值。
    """


class ASRProviderUnavailableError(ASRError):
    """Raised when a provider cannot run because dependencies or config are missing.

    当提供商因缺少依赖或配置而无法运行时抛出。

    Typically surfaced by ``health()`` checks or when attempting to
    instantiate a provider whose Python package is not installed.

    通常由 ``health()`` 检查触发，或在尝试实例化未安装 Python 包的提供商时抛出。
    """


class ASRTranscriptionError(ASRError):
    """Raised when transcription fails after a provider was selected.

    当提供商已选定但转录失败时抛出。

    Covers errors such as empty audio input, unsupported sample rates,
    invalid WAV headers, or runtime failures inside the ASR model.

    涵盖的错误包括空音频输入、不支持的采样率、无效的 WAV 头或 ASR 模型内部运行时故障。
    """
