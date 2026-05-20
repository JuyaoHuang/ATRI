# LLM 调用层设计讨论

> **项目**: emotion-robot
> **创建日期**: 2026-04-XX
> **状态**: 设计中
> **关联文档**: 记忆系统设计讨论.md（§8.2 多出口配置、§8.6 L3/L4 prompt）

---

## 1. 背景与目标

本项目有 4 个 LLM 调用出口：

```
Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='*USB*'} -MaxEvents 20 | Format-Table TimeCreated,Message -Wrap  
```

| # | 出口 | 流式？ | 模型级别 | 谁管理 |
|---|------|--------|----------|--------|
| 1 | 主聊天（user→AI） | 是 | 强模型 | 我们的 LLM 调用层 |
| 2 | L3 压缩（每 26 轮） | 否 | 轻量模型 | 我们的 LLM 调用层 |
| 3 | L4 压缩（每 4 个 block） | 否 | 中等模型 | 我们的 LLM 调用层 |
| 4 | mem0 事实抽取 | — | 由 mem0 配置 | mem0 框架内部 |

#4 由 mem0 框架自己管理（通过 `memory_config.yaml` 中的 `llm.provider` 配置），我们不需要为它写调用代码。

本设计文档覆盖 #1 #2 #3 三个出口的统一调用层。

**参考项目**: Open-LLM-VTuber（OLV）的工厂模式设计。我们借鉴其"接口 → 实现 → 工厂"三层分离的思想，但在工厂模式和接口设计上做改进。

---

## 2. 已确定的设计决策

### 2.1 工厂模式：注册表模式 ✅

**决策：** 使用注册表（Registry）模式替代 OLV 的 if/elif 工厂。

**OLV 的做法（if/elif 链）：**
```python
# 每加一个 provider 都要改工厂文件
if llm_provider == "openai_compatible_llm":
    return OpenAICompatibleLLM(...)
elif llm_provider == "ollama_llm":
    return OllamaLLM(...)
elif llm_provider == "claude_llm":
    return ClaudeLLM(...)
```

**我们的做法（注册表 + 装饰器）：**
```python
class LLMFactory:
    _registry: dict[str, type] = {}

    @classmethod
    def register(cls, name: str):
        def wrapper(llm_class):
            cls._registry[name] = llm_class
            return llm_class
        return wrapper

    @classmethod
    def create(cls, name: str, **kwargs) -> "LLMInterface":
        if name not in cls._registry:
            raise ValueError(f"Unknown LLM provider: {name}. Available: {list(cls._registry.keys())}")
        return cls._registry[name](**kwargs)

# 每个实现文件自己注册
@LLMFactory.register("openai_compatible")
class OpenAICompatibleLLM(LLMInterface):
    ...
```

**优势：**
- 添加新 provider 只需在新文件里加 `@LLMFactory.register("xxx")` 装饰器，工厂代码永远不用改
- 工厂自动知道所有已注册的 provider（`cls._registry.keys()`），方便错误提示和配置校验

---

### 2.2 LLM 接口：流式 + 非流式双接口 ✅

**决策：** 接口同时提供流式和非流式两个方法。子类只需实现流式方法，非流式方法由基类提供默认实现（收集流式结果）。

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Dict, Any, Optional

class LLMInterface(ABC):
    """无状态 LLM 接口。不存储 memory 或 system prompt，每次调用靠参数传入。"""

    @abstractmethod
    async def chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """流式生成。主聊天使用，逐 token yield。"""
        ...

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
    ) -> str:
        """非流式生成。L3/L4 压缩使用，返回完整文本。

        默认实现：收集流式结果。子类可覆盖以提供更高效的非流式调用。
        """
        result = ""
        async for chunk in self.chat_completion_stream(messages, system):
            result += chunk
        return result
```

**设计要点：**
- 子类只需实现 `chat_completion_stream`（一个抽象方法）
- `chat_completion` 有默认实现，子类可选择覆盖（比如某些 API 的非流式调用更高效）
- 接口是**无状态的**（借鉴 OLV）：不存储 memory、system prompt，由上层 Agent/压缩器传入
- 主聊天调 `chat_completion_stream`，L3/L4 调 `chat_completion`

---

### 2.3 多出口配置：凭证池 + 角色引用 ✅

**决策：** 借鉴 OLV 的 `llm_configs` 凭证池设计，但增加 `llm_roles` 层来支持多出口。

**OLV 的做法（单出口）：**
```yaml
agent_settings:
  basic_memory_agent:
    llm_provider: 'gemini_llm'  # 只有一个引用

llm_configs:  # 凭证池
  openai_compatible_llm: { base_url: ..., model: ... }
  gemini_llm: { llm_api_key: ..., model: ... }
  claude_llm: { base_url: ..., model: ... }
```

**我们的做法（多出口）：**
```yaml
llm_configs:  # 凭证池：所有可用的 LLM 配置
  gpt4o:
    provider: openai_compatible
    model: gpt-4o
    base_url: https://api.openai.com/v1
    api_key: sk-xxx
    temperature: 0.7
  haiku:
    provider: openai_compatible
    model: claude-3-haiku-20240307
    base_url: https://xxx/v1
    api_key: sk-xxx
    temperature: 0.3
  local_ollama:
    provider: openai_compatible
    model: qwen2.5:latest
    base_url: http://localhost:11434/v1
    api_key: not-needed

llm_roles:  # 角色映射：每个出口指向凭证池中的某个配置
  chat: gpt4o           # 主聊天 → 强模型
  l3_compress: haiku    # L3 压缩 → 轻量模型
  l4_compact: haiku     # L4 压缩 → 可与 L3 共用，也可指向不同模型
```

**设计要点：**
- `llm_configs` 是凭证池，定义所有可用的 LLM 连接配置（provider + 参数）
- `llm_roles` 是角色映射，每个出口按名字引用池中的配置
- L3 和 L4 可以指向同一个配置（省钱），也可以各自指向不同模型（灵活）
- 与 OLV 的区别：OLV 把 `llm_provider` 放在 `agent_settings` 里（只有一个），我们用独立的 `llm_roles` 支持多个出口
- 凭证池中的 `provider` 字段对应注册表中的 key（`@LLMFactory.register("openai_compatible")`）

---

### 2.4 LLM Provider 支持范围 ✅

**决策：** 支持 4 个 provider，MVP 阶段先实现 `openai_compatible`，其余预留注册表位置后续按需添加。

| Provider | SDK | 覆盖范围 | 实现优先级 |
|----------|-----|----------|-----------|
| `openai_compatible` | `openai` | OpenAI、DeepSeek、Groq、Mistral、vLLM、LM Studio 等所有兼容服务 | MVP 必做 |
| `ollama` | `openai` SDK（`/v1`） | Ollama 本地模型，支持 `keep_alive`、`unload_at_exit` 等特有参数 | 后续添加 |
| `gemini` | `google-genai` | Google Gemini 原生 API，免费额度大，多模态能力 | 后续添加 |
| `claude` | `anthropic` | Claude 原生 API，system prompt 独立参数处理 | 后续添加 |

**为什么 MVP 只做 `openai_compatible`：**
- 覆盖 80%+ 的使用场景（几乎所有主流 LLM 服务都支持 OpenAI 兼容协议）
- Ollama 的 `/v1` 端点也兼容，只是缺少 `keep_alive` 等特有参数
- Gemini 和 Claude 都可以通过 OpenRouter 等中转服务以 OpenAI 兼容方式调用
- 注册表模式下，后续添加新 provider 只需新建文件 + `@LLMFactory.register("xxx")`，不改任何已有代码

**后续添加 provider 的步骤（得益于注册表模式）：**
1. 新建 `ollama_llm.py`（或 `gemini_llm.py` / `claude_llm.py`）
2. 实现 `LLMInterface`，加 `@LLMFactory.register("ollama")` 装饰器
3. 在 `llm_configs` 凭证池中添加对应配置
4. 完成。工厂代码、接口代码、其他 provider 代码均不需要修改

---

### 2.5 配置文件结构：分层引用（仿 docker-compose） ✅

**决策：** 每个子模块有独立的配置文件，根目录的 `config.yaml` 通过路径引用统一管理。

**理由：**
- 使用 OLV 时的痛点：所有配置挤在一个 `conf.yaml` 里，改 LLM 配置要翻几百行找
- 分层后，改 LLM 配置只改 `config/llm_config.yaml`，改记忆配置只改 `config/memory_config.yaml`
- 路径引用（而非 `!include`）：不依赖 YAML 非标准扩展，用 Python 标准库读文件即可

**文件结构：**
```
emotion-robot/
├── config.yaml                  # 根入口，只存路径引用
├── config/
│   ├── llm_config.yaml          # LLM 凭证池 + 角色映射
│   ├── memory_config.yaml       # 记忆系统配置
│   ├── asr_config.yaml          # ASR 配置（后续）
│   └── tts_config.yaml          # TTS 配置（后续）
```

**config.yaml（根入口）：**
```yaml
# 子模块配置文件路径
llm_config: config/llm_config.yaml
memory_config: config/memory_config.yaml
# asr_config: config/asr_config.yaml      # 后续添加
# tts_config: config/tts_config.yaml      # 后续添加
```

**加载逻辑（代码层面）：**
```python
import yaml
from pathlib import Path

def load_config(root_config_path: str) -> dict:
    """读取根配置，再逐个加载子配置文件。"""
    root = Path(root_config_path).parent
    with open(root_config_path) as f:
        root_config = yaml.safe_load(f)

    config = {}
    for key, sub_path in root_config.items():
        full_path = root / sub_path
        with open(full_path) as f:
            config[key.replace("_config", "")] = yaml.safe_load(f)
    return config
    # 返回: {"llm": {...}, "memory": {...}, ...}
```

**llm_config.yaml 完整示例：**
```yaml
# LLM 凭证池：定义所有可用的 LLM 连接配置
llm_configs:
  gpt4o:
    provider: openai_compatible
    model: gpt-4o
    base_url: https://api.openai.com/v1
    api_key: sk-xxx
    temperature: 0.7

  haiku:
    provider: openai_compatible
    model: claude-3-haiku-20240307
    base_url: https://xxx/v1
    api_key: sk-xxx
    temperature: 0.3

  local_ollama:
    provider: openai_compatible
    model: qwen2.5:latest
    base_url: http://localhost:11434/v1
    api_key: not-needed
    temperature: 0.5

# 角色映射：每个调用出口指向凭证池中的某个配置
llm_roles:
  chat: gpt4o           # 主聊天 → 强模型
  l3_compress: haiku    # L3 压缩 → 轻量模型
  l4_compact: haiku     # L4 压缩 → 可与 L3 共用
```

**与 memory_config.yaml 的关系：** 记忆系统的 Memory Manager 在初始化时，由上层（ServiceContext）根据 `llm_roles` 创建 LLM 实例后注入。Memory Manager 不直接读 `llm_config.yaml`。

---

### 2.6 错误处理：接口层只抛异常 ✅

**决策：** LLM 接口层只负责抛出异常，不做重试。重试逻辑由调用方根据场景自行决定。

**OLV 的做法（不推荐）：** 在 provider 实现里 catch 异常，yield 错误文本给用户。没有重试机制，且错误处理和业务逻辑耦合。

**我们的做法：**

```python
# LLM 接口层 — 只抛异常
class OpenAICompatibleLLM(LLMInterface):
    async def chat_completion_stream(self, messages, system=None):
        try:
            stream = await self.client.chat.completions.create(...)
            async for chunk in stream:
                yield chunk.choices[0].delta.content
        except Exception:
            raise  # 不吞异常，不 yield 错误文本

# 调用方 — 各自决定重试策略
# 主聊天：不重试，直接告诉用户
try:
    async for chunk in llm.chat_completion_stream(messages):
        send_to_user(chunk)
except LLMError as e:
    send_to_user(f"LLM 调用失败: {e}")

# L3/L4 压缩：重试 3 次，指数退避
for attempt in range(3):
    try:
        summary = await llm.chat_completion(messages)
        break
    except LLMError:
        if attempt == 2:
            logger.error("L3 压缩失败，跳过本次压缩窗口")
        await asyncio.sleep(2 ** attempt)
```

**自定义异常层次：**
```python
class LLMError(Exception):
    """LLM 调用层基础异常"""

class LLMConnectionError(LLMError):
    """无法连接到 LLM 服务"""

class LLMRateLimitError(LLMError):
    """触发速率限制"""

class LLMAPIError(LLMError):
    """其他 API 错误"""
```

**设计要点：**
- 接口层职责单一：调用 API、返回结果、抛出异常。不做重试、不做错误文本 yield
- 主聊天失败：不重试，用户可以重新发消息
- L3/L4 压缩失败：重试 3 次指数退避，全部失败则跳过本次压缩窗口（下次触发时会补上）
- 自定义异常层次让调用方可以按异常类型做不同处理（如 RateLimit 可以等更久）

---

### 2.7 Tool Calling：接口预留，MVP 不实现 ✅

**决策：** LLM 接口上预留 `tools` 参数（`Optional`），但 MVP 阶段不实现 tool calling 逻辑。

**理由：** readme 明确说"不需要被赋予 mcp、plugin 等外部工具的使用"，当前阶段专注于 RAG 系统。但后续可能会加，所以接口上留个口子。

**接口预留方式：**
```python
class LLMInterface(ABC):
    @abstractmethod
    async def chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,  # 预留，MVP 不使用
    ) -> AsyncIterator[str]:
        ...

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,  # 预留，MVP 不使用
    ) -> str:
        ...
```

**MVP 阶段：** 所有调用方传 `tools=None`。provider 实现中忽略 `tools` 参数。
**后续扩展：** 需要时在 `openai_compatible` provider 中实现 tool calling 逻辑（参考 OLV 的 `openai_compatible_llm.py`），调用方传入 tools 列表即可。

---

## 3. 待讨论事项

| # | 待讨论项 | 状态 |
|---|----------|------|
| 1 | 多出口配置结构 | ✅ 已闭环（§2.3） |
| 2 | 支持哪些 LLM provider | ✅ 已闭环（§2.4） |
| 3 | 配置文件结构 | ✅ 已闭环（§2.5） |
| 4 | 错误处理与重试策略 | ✅ 已闭环（§2.6） |
| 5 | tool calling 支持 | ✅ 已闭环（§2.7），接口预留，MVP 不实现 |

| **#**    | **决策**                                  | **状态** |
| -------- | ----------------------------------------- | -------- |
| **§2.1** | 注册表工厂模式                            | ✅        |
| **§2.2** | 流式 + 非流式双接口                       | ✅        |
| **§2.3** | 凭证池 + 角色引用                         | ✅        |
| **§2.4** | 4 个 provider，MVP 先做 openai_compatible | ✅        |
| **§2.5** | 分层配置文件（根 yaml 引用子文件）        | ✅        |
| **§2.6** | 接口层只抛异常，调用方决定重试            | ✅        |
| **§2.7** | tool calling 接口预留，MVP 不实现         | ✅        |

------

**在开始实现之前，你觉得还有其他需要讨论的点吗？比如：**

- **项目目录结构**（`src/` 下的模块划分）
- **日志方案**（loguru？logging？）
- **其他模块**（ASR/TTS）是否也需要先设计再实现
