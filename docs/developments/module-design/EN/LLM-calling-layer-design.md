# LLM Calling Layer Design Discussion

> Legacy design note:
> Prefer the current implementation docs under [../../modules/llm/README.zh-CN.md](../../modules/llm/README.zh-CN.md).
> This file is kept as historical design source and migration reference, not as the authoritative entry point for the current implementation.

> **Project**: emotion-robot
> **Created**: 2026-04-XX
> **Status**: In Design
> **Related Documents**: Memory System Design Discussion.md (section 8.2 Multi-outlet Configuration, section 8.6 L3/L4 Prompts)

---

## 1. Background and Goals

This project has 4 LLM calling outlets:

```
Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='*USB*'} -MaxEvents 20 | Format-Table TimeCreated,Message -Wrap  
```

| # | Outlet | Streaming? | Model Tier | Managed By |
|---|------|--------|----------|--------|
| 1 | Main chat (user -> AI) | Yes | Strong model | Our LLM calling layer |
| 2 | L3 compression (every 26 rounds) | No | Lightweight model | Our LLM calling layer |
| 3 | L4 compression (every 4 blocks) | No | Medium model | Our LLM calling layer |
| 4 | mem0 fact extraction | -- | Configured by mem0 | Inside mem0 framework |

#4 is managed by the mem0 framework itself (configured via `llm.provider` in `memory_config.yaml`), so we don't need to write calling code for it.

This design document covers the unified calling layer for outlets #1, #2, and #3.

**Reference Project**: Open-LLM-VTuber (OLV) factory pattern design. We borrow the "Interface -> Implementation -> Factory" three-layer separation idea, but make improvements to the factory pattern and interface design.

---

## 2. Finalized Design Decisions

### 2.1 Factory Pattern: Registry Pattern

**Decision:** Use the Registry pattern to replace OLV's if/elif factory.

**OLV's approach (if/elif chain):**
```python
# Every new provider requires modifying the factory file
if llm_provider == "openai_compatible_llm":
    return OpenAICompatibleLLM(...)
elif llm_provider == "ollama_llm":
    return OllamaLLM(...)
elif llm_provider == "claude_llm":
    return ClaudeLLM(...)
```

**Our approach (registry + decorator):**
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

# Each implementation file registers itself
@LLMFactory.register("openai_compatible")
class OpenAICompatibleLLM(LLMInterface):
    ...
```

**Advantages:**
- Adding a new provider only requires adding a `@LLMFactory.register("xxx")` decorator in a new file; the factory code never needs to change
- The factory automatically knows all registered providers (`cls._registry.keys()`), convenient for error messages and configuration validation

---

### 2.2 LLM Interface: Streaming + Non-streaming Dual Interface

**Decision:** The interface provides both streaming and non-streaming methods. Subclasses only need to implement the streaming method; the non-streaming method is provided by the base class as a default implementation (collects streaming results).

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Dict, Any, Optional

class LLMInterface(ABC):
    """Stateless LLM interface. Does not store memory or system prompt; each call passes them via parameters."""

    @abstractmethod
    async def chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Streaming generation. Used for main chat, yields tokens one by one."""
        ...

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
    ) -> str:
        """Non-streaming generation. Used for L3/L4 compression, returns complete text.

        Default implementation: collects streaming results. Subclasses can override for more efficient non-streaming calls.
        """
        result = ""
        async for chunk in self.chat_completion_stream(messages, system):
            result += chunk
        return result
```

**Design highlights:**
- Subclasses only need to implement `chat_completion_stream` (one abstract method)
- `chat_completion` has a default implementation; subclasses can optionally override (e.g., some APIs have more efficient non-streaming calls)
- The interface is **stateless** (inspired by OLV): does not store memory or system prompt; they are passed in by the upper-level Agent/compressor
- Main chat calls `chat_completion_stream`, L3/L4 calls `chat_completion`

---

### 2.3 Multi-outlet Configuration: Credential Pool + Role References

**Decision:** Borrow OLV's `llm_configs` credential pool design, but add an `llm_roles` layer to support multiple outlets.

**OLV's approach (single outlet):**
```yaml
agent_settings:
  basic_memory_agent:
    llm_provider: 'gemini_llm'  # Only one reference

llm_configs:  # Credential pool
  openai_compatible_llm: { base_url: ..., model: ... }
  gemini_llm: { llm_api_key: ..., model: ... }
  claude_llm: { base_url: ..., model: ... }
```

**Our approach (multiple outlets):**
```yaml
llm_configs:  # Credential pool: all available LLM configurations
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

llm_roles:  # Role mapping: each outlet references a configuration in the pool
  chat: gpt4o           # Main chat -> strong model
  l3_compress: haiku    # L3 compression -> lightweight model
  l4_compact: haiku     # L4 compression -> can share with L3, or point to a different model
```

**Design highlights:**
- `llm_configs` is the credential pool, defining all available LLM connection configurations (provider + parameters)
- `llm_roles` is the role mapping, each outlet references a configuration in the pool by name
- L3 and L4 can point to the same configuration (cost-saving) or to different models (flexible)
- Difference from OLV: OLV places `llm_provider` in `agent_settings` (only one), we use a separate `llm_roles` to support multiple outlets
- The `provider` field in the credential pool corresponds to the key in the registry (`@LLMFactory.register("openai_compatible")`)

---

### 2.4 LLM Provider Support Scope

**Decision:** Support 4 providers. During MVP phase, implement `openai_compatible` first; reserve registry slots for the rest and add them as needed later.

| Provider | SDK | Coverage | Implementation Priority |
|----------|-----|----------|-----------|
| `openai_compatible` | `openai` | OpenAI, DeepSeek, Groq, Mistral, vLLM, LM Studio, and all compatible services | MVP required |
| `ollama` | `openai` SDK (`/v1`) | Ollama local models, supports `keep_alive`, `unload_at_exit` and other proprietary parameters | Add later |
| `gemini` | `google-genai` | Google Gemini native API, large free tier, multimodal capabilities | Add later |
| `claude` | `anthropic` | Claude native API, separate system prompt parameter handling | Add later |

**Why MVP only implements `openai_compatible`:**
- Covers 80%+ of use cases (almost all mainstream LLM services support the OpenAI-compatible protocol)
- Ollama's `/v1` endpoint is also compatible, just lacking `keep_alive` and other proprietary parameters
- Gemini and Claude can both be called in OpenAI-compatible mode through relay services like OpenRouter
- With the registry pattern, adding a new provider later only requires creating a new file + `@LLMFactory.register("xxx")`, without modifying any existing code

**Steps for adding providers later (thanks to the registry pattern):**
1. Create `ollama_llm.py` (or `gemini_llm.py` / `claude_llm.py`)
2. Implement `LLMInterface`, add `@LLMFactory.register("ollama")` decorator
3. Add the corresponding configuration in the `llm_configs` credential pool
4. Done. Factory code, interface code, and other provider code all remain unchanged

---

### 2.5 Configuration File Structure: Layered References (Inspired by docker-compose)

**Decision:** Each submodule has its own configuration file, and the root `config.yaml` manages them via path references.

**Reasons:**
- Pain point when using OLV: all configurations are crammed into a single `conf.yaml`; changing LLM config requires scrolling through hundreds of lines
- With layering, changing LLM config only requires editing `config/llm_config.yaml`, changing memory config only requires editing `config/memory_config.yaml`
- Path references (rather than `!include`): does not depend on non-standard YAML extensions, can use Python standard library to read files

**File structure:**
```
emotion-robot/
├── config.yaml                  # Root entry, only stores path references
├── config/
│   ├── llm_config.yaml          # LLM credential pool + role mapping
│   ├── memory_config.yaml       # Memory system configuration
│   ├── asr_config.yaml          # ASR configuration (later)
│   └── tts_config.yaml          # TTS configuration (later)
```

**config.yaml (root entry):**
```yaml
# Sub-module configuration file paths
llm_config: config/llm_config.yaml
memory_config: config/memory_config.yaml
# asr_config: config/asr_config.yaml      # Add later
# tts_config: config/tts_config.yaml      # Add later
```

**Loading logic (code level):**
```python
import yaml
from pathlib import Path

def load_config(root_config_path: str) -> dict:
    """Read root config, then load each sub-config file individually."""
    root = Path(root_config_path).parent
    with open(root_config_path) as f:
        root_config = yaml.safe_load(f)

    config = {}
    for key, sub_path in root_config.items():
        full_path = root / sub_path
        with open(full_path) as f:
            config[key.replace("_config", "")] = yaml.safe_load(f)
    return config
    # Returns: {"llm": {...}, "memory": {...}, ...}
```

**Complete llm_config.yaml example:**
```yaml
# LLM credential pool: define all available LLM connection configurations
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

# Role mapping: each calling outlet references a configuration in the pool
llm_roles:
  chat: gpt4o           # Main chat -> strong model
  l3_compress: haiku    # L3 compression -> lightweight model
  l4_compact: haiku     # L4 compression -> can share with L3
```

**Relationship with memory_config.yaml:** The Memory Manager of the memory system, during initialization, has LLM instances created by the upper layer (ServiceContext) based on `llm_roles` and then injected. The Memory Manager does not directly read `llm_config.yaml`.

---

### 2.6 Error Handling: Interface Layer Only Throws Exceptions

**Decision:** The LLM interface layer is only responsible for throwing exceptions, not for retrying. Retry logic is decided by the caller based on the scenario.

**OLV's approach (not recommended):** Catches exceptions in the provider implementation, yields error text to the user. No retry mechanism, and error handling is coupled with business logic.

**Our approach:**

```python
# LLM interface layer -- only throws exceptions
class OpenAICompatibleLLM(LLMInterface):
    async def chat_completion_stream(self, messages, system=None):
        try:
            stream = await self.client.chat.completions.create(...)
            async for chunk in stream:
                yield chunk.choices[0].delta.content
        except Exception:
            raise  # Don't swallow exceptions, don't yield error text

# Caller -- each decides its own retry strategy
# Main chat: no retry, tell user directly
try:
    async for chunk in llm.chat_completion_stream(messages):
        send_to_user(chunk)
except LLMError as e:
    send_to_user(f"LLM call failed: {e}")

# L3/L4 compression: retry 3 times with exponential backoff
for attempt in range(3):
    try:
        summary = await llm.chat_completion(messages)
        break
    except LLMError:
        if attempt == 2:
            logger.error("L3 compression failed, skipping this compression window")
        await asyncio.sleep(2 ** attempt)
```

**Custom exception hierarchy:**
```python
class LLMError(Exception):
    """Base exception for LLM calling layer"""

class LLMConnectionError(LLMError):
    """Unable to connect to LLM service"""

class LLMRateLimitError(LLMError):
    """Rate limit triggered"""

class LLMAPIError(LLMError):
    """Other API errors"""
```

**Design highlights:**
- Single responsibility for the interface layer: call API, return results, throw exceptions. No retrying, no yielding error text
- Main chat failure: no retry, user can resend the message
- L3/L4 compression failure: retry 3 times with exponential backoff; if all fail, skip this compression window (will be caught up next time it triggers)
- Custom exception hierarchy allows callers to handle different exception types differently (e.g., RateLimit can wait longer)

---

### 2.7 Tool Calling: Interface Reserved, Not Implemented in MVP

**Decision:** Reserve a `tools` parameter (`Optional`) on the LLM interface, but do not implement tool calling logic during the MVP phase.

**Reasons:** The readme explicitly states "no need to be equipped with external tools such as MCP or plugins"; the current phase focuses on the RAG system. However, it may be added later, so a placeholder is left on the interface.

**Interface reservation method:**
```python
class LLMInterface(ABC):
    @abstractmethod
    async def chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,  # Reserved, not used in MVP
    ) -> AsyncIterator[str]:
        ...

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,  # Reserved, not used in MVP
    ) -> str:
        ...
```

**MVP phase:** All callers pass `tools=None`. Provider implementations ignore the `tools` parameter.
**Future extension:** When needed, implement tool calling logic in the `openai_compatible` provider (refer to OLV's `openai_compatible_llm.py`), and callers pass in the tools list.

---

## 3. Items Pending Discussion

| # | Item | Status |
|---|----------|------|
| 1 | Multi-outlet configuration structure | Closed (section 2.3) |
| 2 | Which LLM providers to support | Closed (section 2.4) |
| 3 | Configuration file structure | Closed (section 2.5) |
| 4 | Error handling and retry strategy | Closed (section 2.6) |
| 5 | Tool calling support | Closed (section 2.7), interface reserved, not implemented in MVP |

| **Section** | **Decision** | **Status** |
| -------- | ----------------------------------------- | -------- |
| **2.1** | Registry factory pattern | Done |
| **2.2** | Streaming + non-streaming dual interface | Done |
| **2.3** | Credential pool + role references | Done |
| **2.4** | 4 providers, MVP does openai_compatible first | Done |
| **2.5** | Layered config files (root yaml references sub-files) | Done |
| **2.6** | Interface layer only throws exceptions, caller decides retry | Done |
| **2.7** | Tool calling interface reserved, not implemented in MVP | Done |

------

**Before starting implementation, do you think there are other points that need discussion? For example:**

- **Project directory structure** (module layout under `src/`)
- **Logging solution** (loguru? logging?)
- **Other modules** (ASR/TTS) -- do they also need design before implementation?
