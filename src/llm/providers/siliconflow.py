"""SiliconFlow LLM provider.

SiliconFlow exposes an OpenAI-compatible chat-completions API.  The dedicated
provider class keeps its factory registration and future SiliconFlow-specific
behaviour isolated while reusing the protocol implementation from
``OpenAICompatibleLLM``.

SiliconFlow LLM 提供商。

SiliconFlow 提供 OpenAI 兼容的 chat-completions API。独立 Provider 类将
工厂注册和后续 SiliconFlow 专用行为收口在本模块，同时复用
``OpenAICompatibleLLM`` 的协议实现。
"""

from __future__ import annotations

from src.llm.factory import LLMFactory
from src.llm.providers.openai_compatible import OpenAICompatibleLLM


@LLMFactory.register("siliconflow")
class SiliconFlowLLM(OpenAICompatibleLLM):
    """SiliconFlow provider using the shared OpenAI-compatible implementation.

    使用共享 OpenAI 兼容实现的 SiliconFlow 提供商。
    """
