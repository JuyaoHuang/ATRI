# TTS 模块设计文档

> **文档版本**: v1.0  
> **创建日期**: 2026-04-22  
> **最后更新**: 2026-04-22

---

## 参考文档

- **设计讨论**: `docs/总结_前端对话历史.md` (Round 6-9, Round 11-17)
- **完整对话**: `docs/前端设计对话历史.md` (Round 6-8, Round 15-16)
- **后端架构**: `docs/后端设计.md`
- **项目架构**: `docs/项目架构设计.md`

## 参考项目

- **OLV 架构**: `docs/projects-docs/OLV架构文档.md`
- **AIRI 架构**: `docs/projects-docs/airi_架构文档.md`
- **OLV 源码**: `refer-projects/Open-LLM-VTuber/`
- **AIRI 源码**: `refer-projects/airi/`
- **atri LLM 层**: `atri/src/llm/` (装饰器工厂模式参考)

---

## 1. 模块概述

### 1.1 模块定位

TTS (Text-to-Speech) 模块是 atri 项目的核心语音输出组件，负责将 LLM 生成的文本转换为自然流畅的语音。作为插件式模块，TTS 充当 LLM 流输出的旁路消费者，在翻译模块之后接收处理后的文本，生成音频数据并发送到前端播放。

**在系统中的位置**：
```
LLM 输出 → 翻译模块 → TTS 模块 → 音频播放
                ↓
           Live2D 表情控制（并行）
```

### 1.2 核心功能

1. **多 Provider 支持**：支持 6 个 TTS Provider（3 个云服务 + 3 个本地部署）
2. **统一接口抽象**：通过 `TTSInterface` 抽象基类统一不同 Provider 的调用方式
3. **热插拔切换**：运行时动态切换 TTS Provider，无需重启服务
4. **健康检查**：启动时和切换时自动检查 Provider 可用性
5. **声音管理**：获取和管理不同 Provider 的声音列表
6. **配置驱动**：基于 YAML 配置文件，支持环境变量
7. **异常处理**：5 层异常体系，精确定位错误类型

### 1.3 设计目标

- **可扩展性**：新增 Provider 只需创建文件并添加装饰器，无需修改工厂类
- **可维护性**：清晰的模块分层，职责明确，易于理解和维护
- **高性能**：支持模型预加载、结果缓存、批处理优化
- **高可用**：健康检查机制确保 Provider 可用性，自动降级到备用 Provider
- **易集成**：RESTful API 设计，前端可轻松集成

---

## 2. 技术选型

### 2.1 支持的 TTS Provider 列表

atri 支持 **6 个 TTS Provider**，涵盖云服务和本地部署两大类：

#### 云服务 Provider（3 个）

| Provider | 来源 | 特点 | 推荐场景 | 成本 |
|----------|------|------|----------|------|
| **edge_tts** | Microsoft Edge | 免费，无需 API Key，支持多语言 | 开发测试、零成本部署 | 免费 |
| **openai_tts** | OpenAI | 高质量，6 种声音，支持多语言 | 生产环境、高质量需求 | 按字符计费 |
| **elevenlabs_tts** | ElevenLabs | 顶级质量，情感控制，声音克隆 | 高端应用、情感表达 | 按字符计费 |

#### 本地部署 Provider（3 个）

| Provider | 来源 | 特点 | 推荐场景 | 资源需求 |
|----------|------|------|----------|----------|
| **gpt_sovits_tts** | OLV | 音色克隆，多语言混合，流式支持 | 核心需求，个性化音色 | GPU 推荐 |
| **cosyvoice2_tts** | OLV | 中文优化，支持流式，Gradio API | 中文场景，本地部署 | GPU 推荐 |
| **siliconflow_tts** | 云服务 | 国内云服务，低延迟 | 国内部署，低延迟需求 | 按字符计费 |

### 2.2 Provider 特点对比

#### 准确率对比

| Provider | 中文准确率 | 英文准确率 | 多语言支持 | 情感表达 |
|----------|-----------|-----------|-----------|----------|
| edge_tts | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ 50+ 语言 | ⭐⭐⭐ |
| openai_tts | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ 多语言 | ⭐⭐⭐⭐ |
| elevenlabs_tts | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ 多语言 | ⭐⭐⭐⭐⭐ |
| gpt_sovits_tts | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ 中日英混合 | ⭐⭐⭐⭐ |
| cosyvoice2_tts | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ 中文优化 | ⭐⭐⭐ |
| siliconflow_tts | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ 多语言 | ⭐⭐⭐⭐ |

#### 延迟对比

| Provider | 首字延迟 | 流式支持 | 网络依赖 | 适用场景 |
|----------|---------|---------|---------|----------|
| edge_tts | ~500ms | ❌ | 需要网络 | 非实时场景 |
| openai_tts | ~300ms | ❌ | 需要网络 | 非实时场景 |
| elevenlabs_tts | ~400ms | ✅ | 需要网络 | 实时对话 |
| gpt_sovits_tts | ~200ms | ✅ | 本地部署 | 实时对话 |
| cosyvoice2_tts | ~150ms | ✅ | 本地部署 | 实时对话 |
| siliconflow_tts | ~300ms | ❌ | 需要网络 | 国内部署 |

#### 资源占用对比

| Provider | GPU 内存 | CPU 占用 | 磁盘空间 | 启动时间 |
|----------|---------|---------|---------|----------|
| edge_tts | 0 MB | 低 | 0 MB | 即时 |
| openai_tts | 0 MB | 低 | 0 MB | 即时 |
| elevenlabs_tts | 0 MB | 低 | 0 MB | 即时 |
| gpt_sovits_tts | ~4 GB | 中 | ~2 GB | ~10s |
| cosyvoice2_tts | ~3 GB | 中 | ~1.5 GB | ~8s |
| siliconflow_tts | 0 MB | 低 | 0 MB | 即时 |

### 2.3 技术选型依据

**选择这 6 个 Provider 的原因**：

1. **覆盖全场景**：
   - 免费方案（edge_tts）适合开发测试
   - 云服务方案（openai_tts, elevenlabs_tts）适合生产环境
   - 本地部署方案（gpt_sovits_tts, cosyvoice2_tts）适合隐私保护和离线场景

2. **复用成熟实现**：
   - 本地 Provider 直接复用 OLV 的实现（gpt_sovits_tts, cosyvoice2_tts）
   - 云服务 Provider 参考 AIRI 的实现（openai_tts, elevenlabs_tts）

3. **满足核心需求**：
   - **音色克隆**：gpt_sovits_tts 支持参考音频克隆
   - **中文优化**：cosyvoice2_tts 专为中文优化
   - **零成本**：edge_tts 免费且无需 API Key
   - **高质量**：elevenlabs_tts 提供顶级音质

4. **架构一致性**：
   - 与 ASR 模块保持一致的架构设计
   - 与 atri LLM 层保持一致的装饰器工厂模式

---

## 3. 架构设计

### 3.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI 路由层                         │
│                    (src/routes/tts.py)                       │
│  GET /api/tts/providers                                      │
│  POST /api/tts/set-provider                                  │
│  GET /api/tts/voices                                         │
│  POST /api/tts/synthesize                                    │
│  GET /api/tts/providers/{id}/health                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                        工厂层                                 │
│                   (src/tts/factory.py)                       │
│  TTSFactory.register()  - 装饰器注册                         │
│  TTSFactory.create()    - Provider 实例化                    │
│  TTSFactory.get_registry() - 获取注册表                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                        接口层                                 │
│                  (src/tts/interface.py)                      │
│  TTSInterface (ABC)                                          │
│    - synthesize()         同步合成                           │
│    - synthesize_stream()  流式合成（接口预留）                │
│    - get_voices()         获取声音列表                        │
│    - health_check()       健康检查                           │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      Provider 实现层                          │
│                  (src/tts/providers/)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  edge_tts.py │  │openai_tts.py │  │elevenlabs.py │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │gpt_sovits.py │  │cosyvoice2.py │  │siliconflow.py│      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                        异常层                                 │
│                 (src/tts/exceptions.py)                      │
│  TTSError → TTSConnectionError                               │
│          → TTSConfigError                                    │
│          → TTSAPIError                                       │
│          → TTSRateLimitError                                 │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 模块分层

TTS 模块采用 **5 层架构**：

1. **路由层** (`src/routes/tts.py`)
   - 职责：处理 HTTP 请求，参数验证，响应格式化
   - 依赖：工厂层

2. **工厂层** (`src/tts/factory.py`)
   - 职责：Provider 注册、实例化、管理
   - 依赖：接口层

3. **接口层** (`src/tts/interface.py`)
   - 职责：定义统一的 TTS 接口规范
   - 依赖：无

4. **Provider 实现层** (`src/tts/providers/`)
   - 职责：实现具体的 TTS Provider
   - 依赖：接口层、异常层

5. **异常层** (`src/tts/exceptions.py`)
   - 职责：定义 TTS 模块的异常体系
   - 依赖：无

### 3.3 目录结构

```
atri/src/tts/
├── __init__.py              # 导入所有 Provider 触发注册
├── interface.py             # TTSInterface 抽象基类
├── factory.py               # TTSFactory 装饰器注册
├── exceptions.py            # TTS 异常层次
├── types.py                 # 类型定义（TTSConfig, VoiceInfo）
└── providers/
    ├── __init__.py
    ├── edge_tts.py          # @TTSFactory.register("edge_tts")
    ├── openai_tts.py        # @TTSFactory.register("openai_tts")
    ├── elevenlabs_tts.py    # @TTSFactory.register("elevenlabs_tts")
    ├── gpt_sovits_tts.py    # @TTSFactory.register("gpt_sovits_tts")
    ├── cosyvoice2_tts.py    # @TTSFactory.register("cosyvoice2_tts")
    └── siliconflow_tts.py   # @TTSFactory.register("siliconflow_tts")
```

### 3.4 核心组件关系

```
┌─────────────────┐
│  ServiceContext │  ← 服务上下文（管理当前 TTS Provider）
└────────┬────────┘
         │ 持有
         ↓
┌─────────────────┐
│   TTSFactory    │  ← 工厂类（管理 Provider 注册表）
└────────┬────────┘
         │ 创建
         ↓
┌─────────────────┐
│  TTSInterface   │  ← 抽象基类（定义统一接口）
└────────┬────────┘
         │ 继承
         ↓
┌─────────────────┐
│ EdgeTTS / ...   │  ← 具体 Provider 实现
└─────────────────┘
```

**参考代码路径**：
- 接口定义：`atri/src/llm/interface.py` (LLMInterface 抽象基类)
- 工厂注册：`atri/src/llm/factory.py` (LLMFactory 装饰器模式)
- Provider 实现：`atri/src/llm/providers/openai_compatible.py` (装饰器注册示例)
- OLV TTS 实现：`refer-projects/Open-LLM-VTuber/src/open_llm_vtuber/tts/`

---

## 4. 接口设计

### 4.1 TTSInterface 抽象基类

`TTSInterface` 是所有 TTS Provider 的抽象基类，定义了统一的接口规范。

```python
# src/tts/interface.py

from abc import ABC, abstractmethod
from typing import Optional, AsyncIterator

class TTSInterface(ABC):
    """TTS 引擎抽象基类"""
    
    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """
        同步合成语音（返回完整音频数据）
        
        Args:
            text: 要合成的文本
            voice_id: 声音 ID（可选，使用默认声音）
            **kwargs: 其他参数（pitch, rate, volume 等）
        
        Returns:
            bytes: 音频数据（MP3/WAV 格式）
        
        Raises:
            TTSError: TTS 合成失败
            TTSConnectionError: 网络连接失败
            TTSAPIError: API 调用失败
            TTSRateLimitError: 速率限制
        """
        raise NotImplementedError
    
    @abstractmethod
    async def synthesize_stream(
        self,
        text: str,
        voice_id: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[bytes]:
        """
        流式合成语音（返回音频数据流）
        
        注意：当前实现为非流式输出，此接口为后续扩展预留。
        实现时应抛出 NotImplementedError。
        
        Args:
            text: 要合成的文本
            voice_id: 声音 ID
            **kwargs: 其他参数
        
        Yields:
            bytes: 音频数据块
        
        Raises:
            NotImplementedError: 当前版本未实现流式合成
        """
        raise NotImplementedError("流式合成暂未实现")
    
    @abstractmethod
    async def get_voices(self) -> list[dict]:
        """
        获取可用声音列表
        
        Returns:
            list[dict]: 声音列表
            [
                {
                    "id": "voice_id",
                    "name": "Voice Name",
                    "language": "zh-CN",
                    "gender": "female",
                    "description": "声音描述",
                    "preview_url": "https://..."  # 可选
                }
            ]
        
        Raises:
            TTSError: 获取声音列表失败
        """
        raise NotImplementedError
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        健康检查（启动时 + 切换时调用）
        
        Returns:
            bool: True 表示 Provider 可用，False 表示不可用
        
        Note:
            - 云服务：检查 API Key 有效性、网络连接
            - 本地服务：检查服务是否启动、模型是否加载
        """
        raise NotImplementedError
```

### 4.2 方法签名和返回值

#### 4.2.1 synthesize() - 同步合成

**方法签名**：
```python
async def synthesize(
    self,
    text: str,
    voice_id: Optional[str] = None,
    **kwargs
) -> bytes
```

**参数说明**：
- `text`: 要合成的文本（必需）
- `voice_id`: 声音 ID（可选，不提供则使用默认声音）
- `**kwargs`: 其他参数
  - `pitch`: 音调调整（-100 ~ +100）
  - `rate`: 语速调整（0.5 ~ 2.0）
  - `volume`: 音量调整（0.0 ~ 2.0）
  - `format`: 输出格式（mp3/wav/ogg）
  - `sample_rate`: 采样率（16000/24000/48000）

**返回值**：
- `bytes`: 完整的音频数据（二进制格式）

**使用示例**：
```python
# 使用默认声音
audio_data = await tts_engine.synthesize("你好，世界")

# 指定声音和参数
audio_data = await tts_engine.synthesize(
    text="Hello, world",
    voice_id="alloy",
    rate=1.2,
    pitch=10
)
```

#### 4.2.2 synthesize_stream() - 流式合成

**方法签名**：
```python
async def synthesize_stream(
    self,
    text: str,
    voice_id: Optional[str] = None,
    **kwargs
) -> AsyncIterator[bytes]
```

**当前实现**：
- ❌ 当前版本未实现流式合成
- ✅ 接口预留，后续版本实现
- 实现时应抛出 `NotImplementedError`

**设计说明**：
根据对 OLV 的分析，OLV 只实现了非流式输出。即使 `gpt_sovits` 配置 `streaming_mode: true`，OLV 也会等待完整音频生成后再保存为文件。因此，atri 当前版本采用同样的实现方式，流式输出作为后续优化项。

#### 4.2.3 get_voices() - 获取声音列表

**方法签名**：
```python
async def get_voices(self) -> list[dict]
```

**返回值格式**：
```python
[
    {
        "id": "zh-CN-XiaoxiaoNeural",
        "name": "晓晓",
        "language": "zh-CN",
        "gender": "female",
        "description": "温柔的女声",
        "preview_url": "https://..."  # 可选
    },
    {
        "id": "en-US-AriaNeural",
        "name": "Aria",
        "language": "en-US",
        "gender": "female",
        "description": "Natural English voice"
    }
]
```

**使用示例**：
```python
voices = await tts_engine.get_voices()
for voice in voices:
    print(f"{voice['name']} ({voice['language']})")
```

#### 4.2.4 health_check() - 健康检查

**方法签名**：
```python
async def health_check(self) -> bool
```

**返回值**：
- `True`: Provider 可用
- `False`: Provider 不可用

**检查逻辑**：

**云服务 Provider**：
```python
async def health_check(self) -> bool:
    try:
        # 尝试调用 API（轻量级请求）
        response = await self.client.models.list()
        return True
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return False
```

**本地部署 Provider**：
```python
async def health_check(self) -> bool:
    try:
        # 检查服务是否启动
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/health",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                return response.status == 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return False
```

### 4.3 接口设计原则

1. **统一性**：所有 Provider 实现相同的接口，调用方式一致
2. **异步优先**：所有方法都是异步的，避免阻塞主线程
3. **可选参数**：使用 `**kwargs` 支持 Provider 特定参数
4. **明确异常**：使用自定义异常体系，精确定位错误类型
5. **向后兼容**：预留流式接口，但当前实现为非流式

**参考代码路径**：
- OLV 接口：`refer-projects/Open-LLM-VTuber/src/open_llm_vtuber/tts/tts_interface.py`
- atri LLM 接口：`atri/src/llm/interface.py`

---

## 5. 工厂模式实现

### 5.1 TTSFactory 装饰器注册机制

`TTSFactory` 采用装饰器注册模式，与 atri LLM 层保持一致。

```python
# src/tts/factory.py

from typing import Dict, Type, Optional
from .interface import TTSInterface
from .exceptions import TTSConfigError

class TTSFactory:
    """TTS Provider 工厂类（装饰器注册模式）"""
    
    _registry: Dict[str, Type[TTSInterface]] = {}
    
    @classmethod
    def register(cls, name: str):
        """
        装饰器：将 Provider 注册到工厂
        
        Args:
            name: Provider 名称（如 "edge_tts"）
        
        Returns:
            装饰器函数
        
        Example:
            @TTSFactory.register("edge_tts")
            class EdgeTTS(TTSInterface):
                ...
        """
        def wrapper(provider_class: Type[TTSInterface]):
            if name in cls._registry:
                raise TTSConfigError(f"Provider {name} already registered")
            cls._registry[name] = provider_class
            return provider_class
        return wrapper
    
    @classmethod
    def create(cls, name: str, **kwargs) -> TTSInterface:
        """
        根据 name 实例化 Provider
        
        Args:
            name: Provider 名称
            **kwargs: Provider 初始化参数
        
        Returns:
            TTSInterface: Provider 实例
        
        Raises:
            TTSConfigError: Provider 未注册
        
        Example:
            tts_engine = TTSFactory.create(
                "edge_tts",
                voice="zh-CN-XiaoxiaoNeural"
            )
        """
        provider_class = cls._registry.get(name)
        if not provider_class:
            available = ", ".join(cls._registry.keys())
            raise TTSConfigError(
                f"Provider {name} not found. "
                f"Available providers: {available}"
            )
        return provider_class(**kwargs)
    
    @classmethod
    def get_registry(cls) -> Dict[str, Type[TTSInterface]]:
        """
        获取注册表
        
        Returns:
            Dict[str, Type[TTSInterface]]: Provider 注册表
        """
        return cls._registry.copy()
    
    @classmethod
    def list_providers(cls) -> list[str]:
        """
        列出所有已注册的 Provider
        
        Returns:
            list[str]: Provider 名称列表
        """
        return list(cls._registry.keys())
```

### 5.2 Provider 注册流程

#### 5.2.1 注册时机

Provider 在模块导入时自动注册：

```python
# src/tts/__init__.py

"""TTS 模块初始化"""

# 导入工厂和接口
from .factory import TTSFactory
from .interface import TTSInterface

# 导入所有 Provider（触发装饰器注册）
from .providers import (
    edge_tts,
    openai_tts,
    elevenlabs_tts,
    gpt_sovits_tts,
    cosyvoice2_tts,
    siliconflow_tts,
)

__all__ = [
    "TTSFactory",
    "TTSInterface",
]
```

#### 5.2.2 Provider 实现示例

```python
# src/tts/providers/edge_tts.py

from ..factory import TTSFactory
from ..interface import TTSInterface
from ..exceptions import TTSError, TTSConnectionError

@TTSFactory.register("edge_tts")
class EdgeTTS(TTSInterface):
    """Microsoft Edge TTS Provider"""
    
    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural", **kwargs):
        self.voice = voice
        self.rate = kwargs.get("rate", 1.0)
        self.pitch = kwargs.get("pitch", 0)
    
    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """同步合成语音"""
        try:
            import edge_tts
            
            voice = voice_id or self.voice
            rate = kwargs.get("rate", self.rate)
            pitch = kwargs.get("pitch", self.pitch)
            
            # 调用 edge_tts 合成
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=f"{rate:+.0%}",
                pitch=f"{pitch:+.0f}Hz"
            )
            
            # 收集音频数据
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            
            return audio_data
        
        except Exception as e:
            raise TTSError(f"Edge TTS synthesis failed: {e}")
    
    async def synthesize_stream(
        self,
        text: str,
        voice_id: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[bytes]:
        """流式合成（当前未实现）"""
        raise NotImplementedError("流式合成暂未实现")
    
    async def get_voices(self) -> list[dict]:
        """获取可用声音列表"""
        import edge_tts
        
        voices = await edge_tts.list_voices()
        return [
            {
                "id": voice["ShortName"],
                "name": voice["FriendlyName"],
                "language": voice["Locale"],
                "gender": voice["Gender"].lower()
            }
            for voice in voices
        ]
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 尝试获取声音列表
            await self.get_voices()
            return True
        except Exception:
            return False
```

### 5.3 Provider 创建和初始化

#### 5.3.1 从配置文件创建

```python
# src/service_context.py

from src.tts.factory import TTSFactory
from src.config import load_config

class ServiceContext:
    def __init__(self):
        self.config = load_config()
        self.tts_engine = None
    
    def initialize_tts(self):
        """初始化 TTS Provider"""
        tts_config = self.config["tts"]
        active_provider = tts_config["active_provider"]
        provider_config = tts_config["providers"][active_provider]
        
        # 从配置创建 Provider
        self.tts_engine = TTSFactory.create(
            name=provider_config["provider"],
            **provider_config
        )
```

#### 5.3.2 运行时切换 Provider

```python
async def switch_tts_provider(
    service_context: ServiceContext,
    provider_name: str
) -> bool:
    """
    切换 TTS Provider
    
    Args:
        service_context: 服务上下文
        provider_name: 新的 Provider 名称
    
    Returns:
        bool: 切换是否成功
    """
    try:
        # 获取新 Provider 配置
        provider_config = service_context.config["tts"]["providers"][provider_name]
        
        # 创建新 Provider 实例
        new_engine = TTSFactory.create(
            name=provider_config["provider"],
            **provider_config
        )
        
        # 健康检查
        if not await new_engine.health_check():
            logger.error(f"Provider {provider_name} health check failed")
            return False
        
        # 切换 Provider
        service_context.tts_engine = new_engine
        service_context.config["tts"]["active_provider"] = provider_name
        
        logger.info(f"Switched to TTS provider: {provider_name}")
        return True
    
    except Exception as e:
        logger.error(f"Failed to switch TTS provider: {e}")
        return False
```

### 5.4 热切换机制

热切换机制允许在运行时动态切换 TTS Provider，无需重启服务。

**实现步骤**：

1. **创建新 Provider 实例**
2. **执行健康检查**
3. **切换 Provider**（原子操作）
4. **更新配置**

**注意事项**：

- 切换前必须执行健康检查
- 切换失败时保持原 Provider 不变
- 切换过程中的请求使用旧 Provider
- 切换完成后的请求使用新 Provider

**参考代码路径**：
- atri LLM 工厂：`atri/src/llm/factory.py`
- OLV TTS 工厂：`refer-projects/Open-LLM-VTuber/src/open_llm_vtuber/tts/tts_factory.py`

---

## 6. Provider 实现规范

### 6.1 6 个 Provider 的详细实现

本节详细说明 6 个 TTS Provider 的配置参数、初始化逻辑和核心实现。

#### 6.1.1 edge_tts（免费云服务）

**配置参数**：
```yaml
edge_tts:
  provider: "edge_tts"
  name: "Edge TTS"
  type: cloud
  health_check: true
  voice: "zh-CN-XiaoxiaoNeural"  # 默认声音
  rate: 1.0                       # 语速（0.5-2.0）
  pitch: 0                        # 音调（-100 ~ +100）
  format: "mp3"
```

**初始化逻辑**：
```python
@TTSFactory.register("edge_tts")
class EdgeTTS(TTSInterface):
    def __init__(
        self,
        voice: str = "zh-CN-XiaoxiaoNeural",
        rate: float = 1.0,
        pitch: int = 0,
        format: str = "mp3",
        **kwargs
    ):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.format = format
```

**核心实现**：
```python
async def synthesize(self, text: str, voice_id: Optional[str] = None, **kwargs) -> bytes:
    import edge_tts
    
    voice = voice_id or self.voice
    rate = kwargs.get("rate", self.rate)
    pitch = kwargs.get("pitch", self.pitch)
    
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=f"{rate:+.0%}",
        pitch=f"{pitch:+.0f}Hz"
    )
    
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    
    return audio_data
```

**参考代码路径**：
- AIRI Edge TTS：`refer-projects/airi/packages/stage-ui/src/lib/tts/edge-tts.ts`

---

#### 6.1.2 openai_tts（云服务）

**配置参数**：
```yaml
openai_tts:
  provider: "openai_tts"
  name: "OpenAI TTS"
  type: cloud
  health_check: true
  api_key: ${OPENAI_API_KEY}
  base_url: "https://api.openai.com/v1"
  model: "tts-1-hd"              # tts-1 / tts-1-hd
  voice: "alloy"                 # alloy, echo, fable, onyx, nova, shimmer
  format: "mp3"
  sample_rate: 24000
```

**初始化逻辑**：
```python
@TTSFactory.register("openai_tts")
class OpenAITTS(TTSInterface):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "tts-1-hd",
        voice: str = "alloy",
        format: str = "mp3",
        **kwargs
    ):
        from openai import AsyncOpenAI
        
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        self.model = model
        self.voice = voice
        self.format = format
```

**核心实现**：
```python
async def synthesize(self, text: str, voice_id: Optional[str] = None, **kwargs) -> bytes:
    try:
        response = await self.client.audio.speech.create(
            model=self.model,
            voice=voice_id or self.voice,
            input=text,
            response_format=self.format,
            speed=kwargs.get("rate", 1.0)
        )
        return response.content
    except Exception as e:
        raise TTSAPIError(f"OpenAI TTS API error: {e}")

async def get_voices(self) -> list[dict]:
    return [
        {"id": "alloy", "name": "Alloy", "language": "en-US", "gender": "neutral"},
        {"id": "echo", "name": "Echo", "language": "en-US", "gender": "male"},
        {"id": "fable", "name": "Fable", "language": "en-US", "gender": "neutral"},
        {"id": "onyx", "name": "Onyx", "language": "en-US", "gender": "male"},
        {"id": "nova", "name": "Nova", "language": "en-US", "gender": "female"},
        {"id": "shimmer", "name": "Shimmer", "language": "en-US", "gender": "female"}
    ]

async def health_check(self) -> bool:
    try:
        await self.client.models.list()
        return True
    except Exception:
        return False
```

**参考代码路径**：
- AIRI OpenAI TTS：`refer-projects/airi/packages/stage-ui/src/lib/tts/openai-tts.ts`

---

#### 6.1.3 elevenlabs_tts（云服务）

**配置参数**：
```yaml
elevenlabs_tts:
  provider: "elevenlabs_tts"
  name: "ElevenLabs TTS"
  type: cloud
  health_check: true
  api_key: ${ELEVENLABS_API_KEY}
  base_url: "https://api.elevenlabs.io/v1"
  voice_id: "21m00Tcm4TlvDq8ikWAM"  # Rachel
  model_id: "eleven_monolingual_v1"
  stability: 0.5
  similarity_boost: 0.75
  format: "mp3"
```

**初始化逻辑**：
```python
@TTSFactory.register("elevenlabs_tts")
class ElevenLabsTTS(TTSInterface):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.elevenlabs.io/v1",
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",
        model_id: str = "eleven_monolingual_v1",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        **kwargs
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.voice_id = voice_id
        self.model_id = model_id
        self.stability = stability
        self.similarity_boost = similarity_boost
```

**核心实现**：
```python
async def synthesize(self, text: str, voice_id: Optional[str] = None, **kwargs) -> bytes:
    import aiohttp
    
    voice = voice_id or self.voice_id
    url = f"{self.base_url}/text-to-speech/{voice}"
    
    headers = {
        "xi-api-key": self.api_key,
        "Content-Type": "application/json"
    }
    
    data = {
        "text": text,
        "model_id": self.model_id,
        "voice_settings": {
            "stability": self.stability,
            "similarity_boost": self.similarity_boost
        }
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            if response.status != 200:
                raise TTSAPIError(f"ElevenLabs API error: {response.status}")
            return await response.read()

async def get_voices(self) -> list[dict]:
    import aiohttp
    
    url = f"{self.base_url}/voices"
    headers = {"xi-api-key": self.api_key}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            data = await response.json()
            return [
                {
                    "id": voice["voice_id"],
                    "name": voice["name"],
                    "language": voice.get("labels", {}).get("language", "en"),
                    "gender": voice.get("labels", {}).get("gender", "neutral"),
                    "preview_url": voice.get("preview_url")
                }
                for voice in data["voices"]
            ]
```

---

#### 6.1.4 gpt_sovits_tts（本地部署，核心）

**配置参数**：
```yaml
gpt_sovits_tts:
  provider: "gpt_sovits_tts"
  name: "GPT-SoVITS"
  type: local
  health_check: true
  required: false
  # 必需参数（5 个）
  api_url: "http://127.0.0.1:9880/tts"
  text_lang: "zh"                                    # zh/ja/en
  ref_audio_path: "./data/reference_audio/atri.wav"
  prompt_lang: "zh"
  prompt_text: "这是参考音频的文本内容"
  # 可选参数
  text_split_method: "cut5"                          # cut0-cut5
  batch_size: "1"
  media_type: "wav"
  streaming_mode: "false"
```

**初始化逻辑**：
```python
@TTSFactory.register("gpt_sovits_tts")
class GPTSoVITSTTS(TTSInterface):
    def __init__(
        self,
        api_url: str,
        text_lang: str,
        ref_audio_path: str,
        prompt_lang: str,
        prompt_text: str,
        text_split_method: str = "cut5",
        batch_size: str = "1",
        media_type: str = "wav",
        streaming_mode: str = "false",
        **kwargs
    ):
        self.api_url = api_url
        self.text_lang = text_lang
        self.ref_audio_path = ref_audio_path
        self.prompt_lang = prompt_lang
        self.prompt_text = prompt_text
        self.text_split_method = text_split_method
        self.batch_size = batch_size
        self.media_type = media_type
        self.streaming_mode = streaming_mode
```

**核心实现**：
```python
async def synthesize(self, text: str, voice_id: Optional[str] = None, **kwargs) -> bytes:
    import aiohttp
    
    params = {
        "text": text,
        "text_lang": self.text_lang,
        "ref_audio_path": self.ref_audio_path,
        "prompt_lang": self.prompt_lang,
        "prompt_text": self.prompt_text,
        "text_split_method": self.text_split_method,
        "batch_size": self.batch_size,
        "media_type": self.media_type,
        "streaming_mode": self.streaming_mode
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(self.api_url, params=params) as response:
            if response.status != 200:
                raise TTSAPIError(f"GPT-SoVITS API error: {response.status}")
            return await response.read()

async def health_check(self) -> bool:
    import aiohttp
    
    try:
        # 检查服务是否启动
        health_url = self.api_url.replace("/tts", "/health")
        async with aiohttp.ClientSession() as session:
            async with session.get(
                health_url,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                return response.status == 200
    except Exception:
        return False
```

**参考代码路径**：
- OLV GPT-SoVITS：`refer-projects/Open-LLM-VTuber/src/open_llm_vtuber/tts/gpt_sovits_tts.py`

---

#### 6.1.5 cosyvoice2_tts（本地部署）

**配置参数**：
```yaml
cosyvoice2_tts:
  provider: "cosyvoice2_tts"
  name: "CosyVoice2"
  type: local
  health_check: true
  base_url: "http://127.0.0.1:7860"
  speaker: "中文女"
  format: "wav"
```

**初始化逻辑**：
```python
@TTSFactory.register("cosyvoice2_tts")
class CosyVoice2TTS(TTSInterface):
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:7860",
        speaker: str = "中文女",
        format: str = "wav",
        **kwargs
    ):
        from gradio_client import Client
        
        self.base_url = base_url
        self.speaker = speaker
        self.format = format
        self.client = Client(base_url)
```

**核心实现**：
```python
async def synthesize(self, text: str, voice_id: Optional[str] = None, **kwargs) -> bytes:
    try:
        speaker = voice_id or self.speaker
        
        # 调用 Gradio API
        result = self.client.predict(
            text=text,
            speaker=speaker,
            api_name="/synthesize"
        )
        
        # 读取音频文件
        with open(result, "rb") as f:
            return f.read()
    
    except Exception as e:
        raise TTSError(f"CosyVoice2 synthesis failed: {e}")

async def health_check(self) -> bool:
    try:
        # 使用 Gradio Client 的 view_api() 检查连接
        self.client.view_api()
        return True
    except Exception:
        return False
```

**参考代码路径**：
- OLV CosyVoice：`refer-projects/Open-LLM-VTuber/src/open_llm_vtuber/tts/cosyvoice_tts.py`

---

#### 6.1.6 siliconflow_tts（国内云服务）

**配置参数**：
```yaml
siliconflow_tts:
  provider: "siliconflow_tts"
  name: "SiliconFlow TTS"
  type: cloud
  health_check: true
  api_key: ${SILICONFLOW_API_KEY}
  base_url: "https://api.siliconflow.cn/v1"
  model: "fishaudio/fish-speech-1.4"
  voice: "zh-CN-female-1"
  format: "mp3"
```

**初始化逻辑**：
```python
@TTSFactory.register("siliconflow_tts")
class SiliconFlowTTS(TTSInterface):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.siliconflow.cn/v1",
        model: str = "fishaudio/fish-speech-1.4",
        voice: str = "zh-CN-female-1",
        format: str = "mp3",
        **kwargs
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.voice = voice
        self.format = format
```

**核心实现**：
```python
async def synthesize(self, text: str, voice_id: Optional[str] = None, **kwargs) -> bytes:
    import aiohttp
    
    url = f"{self.base_url}/audio/speech"
    headers = {
        "Authorization": f"Bearer {self.api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": self.model,
        "input": text,
        "voice": voice_id or self.voice,
        "response_format": self.format
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            if response.status != 200:
                raise TTSAPIError(f"SiliconFlow API error: {response.status}")
            return await response.read()
```

---

### 6.2 统一的配置结构

所有 Provider 的配置遵循统一的结构：

```python
# src/tts/types.py

from typing import Optional, Literal
from pydantic import BaseModel

class TTSConfig(BaseModel):
    """TTS Provider 配置"""
    provider: str                           # Provider ID
    name: str                               # 显示名称
    type: Literal["cloud", "local"]         # Provider 类型
    health_check: bool = True               # 是否启用健康检查
    required: bool = True                   # 是否必需（本地服务可选）
    
    # 云服务通用参数
    api_key: Optional[str] = None           # API Key
    base_url: Optional[str] = None          # API 基础 URL
    model: Optional[str] = None             # 模型 ID
    voice: Optional[str] = None             # 默认声音 ID
    
    # 音频参数
    pitch: int = 0                          # 音调 (-100 ~ +100)
    rate: float = 1.0                       # 语速 (0.5 ~ 2.0)
    volume: float = 1.0                     # 音量 (0.0 ~ 2.0)
    
    # 输出格式
    format: Literal["mp3", "wav", "ogg"] = "mp3"
    sample_rate: int = 24000                # 采样率
    
    # 流式支持
    streaming: bool = False                 # 是否支持流式输出

class VoiceInfo(BaseModel):
    """声音信息"""
    id: str                                 # 声音 ID
    name: str                               # 显示名称
    language: str                           # 语言代码（zh-CN, en-US）
    gender: Optional[str] = None            # 性别（male, female, neutral）
    description: Optional[str] = None       # 描述
    preview_url: Optional[str] = None       # 预览音频 URL
```

### 6.3 模型加载和管理

#### 6.3.1 本地模型预加载

对于本地部署的 Provider（gpt_sovits_tts, cosyvoice2_tts），建议在服务启动时预加载模型：

```python
# src/service_context.py

class ServiceContext:
    async def initialize_tts(self):
        """初始化 TTS Provider"""
        tts_config = self.config["tts"]
        active_provider = tts_config["active_provider"]
        provider_config = tts_config["providers"][active_provider]
        
        # 创建 Provider
        self.tts_engine = TTSFactory.create(
            name=provider_config["provider"],
            **provider_config
        )
        
        # 本地 Provider 预加载模型
        if provider_config["type"] == "local":
            logger.info(f"Preloading TTS model: {active_provider}")
            # 执行一次空合成，触发模型加载
            try:
                await self.tts_engine.synthesize("测试")
                logger.info(f"TTS model preloaded: {active_provider}")
            except Exception as e:
                logger.warning(f"TTS model preload failed: {e}")
```

#### 6.3.2 模型文件管理

本地模型文件存储在 `atri/models/tts/` 目录：

```
atri/models/tts/
├── gpt_sovits/
│   ├── GPT_SoVITS.pth
│   ├── SoVITS_weights.pth
│   └── reference_audio/
│       └── atri.wav
├── cosyvoice2/
│   ├── model.pt
│   └── config.yaml
└── README.md
```

**参考代码路径**：
- OLV 模型管理：`refer-projects/Open-LLM-VTuber/models/`

---

## 7. 异常处理机制

### 7.1 异常层次结构

TTS 模块定义了 **5 个异常类**，形成清晰的异常层次：

```python
# src/tts/exceptions.py

class TTSError(Exception):
    """TTS 基础异常"""
    pass

class TTSConnectionError(TTSError):
    """网络/连接错误"""
    pass

class TTSConfigError(TTSError):
    """配置错误"""
    pass

class TTSAPIError(TTSError):
    """API 调用错误"""
    pass

class TTSRateLimitError(TTSError):
    """速率限制错误"""
    pass
```

### 7.2 异常使用场景

#### 7.2.1 TTSError（基础异常）

**使用场景**：通用 TTS 错误，无法归类到其他异常时使用。

**示例**：
```python
async def synthesize(self, text: str, **kwargs) -> bytes:
    try:
        # TTS 合成逻辑
        ...
    except Exception as e:
        raise TTSError(f"TTS synthesis failed: {e}")
```

#### 7.2.2 TTSConnectionError（连接错误）

**使用场景**：网络连接失败、服务不可达。

**示例**：
```python
async def health_check(self) -> bool:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(self.base_url) as response:
                return response.status == 200
    except aiohttp.ClientConnectorError as e:
        raise TTSConnectionError(f"Cannot connect to TTS service: {e}")
    except asyncio.TimeoutError:
        raise TTSConnectionError("TTS service connection timeout")
```

#### 7.2.3 TTSConfigError（配置错误）

**使用场景**：配置参数缺失、格式错误、Provider 未注册。

**示例**：
```python
def __init__(self, api_key: str, **kwargs):
    if not api_key:
        raise TTSConfigError("API key is required")
    
    if not api_key.startswith("sk-"):
        raise TTSConfigError("Invalid API key format")
    
    self.api_key = api_key
```

#### 7.2.4 TTSAPIError（API 错误）

**使用场景**：API 调用失败、返回错误状态码。

**示例**：
```python
async def synthesize(self, text: str, **kwargs) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.post(self.api_url, json=data) as response:
            if response.status == 400:
                raise TTSAPIError("Invalid request parameters")
            elif response.status == 401:
                raise TTSAPIError("Invalid API key")
            elif response.status == 500:
                raise TTSAPIError("TTS service internal error")
            elif response.status != 200:
                raise TTSAPIError(f"API error: {response.status}")
            
            return await response.read()
```

#### 7.2.5 TTSRateLimitError（速率限制）

**使用场景**：API 调用超过速率限制。

**示例**：
```python
async def synthesize(self, text: str, **kwargs) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.post(self.api_url, json=data) as response:
            if response.status == 429:
                retry_after = response.headers.get("Retry-After", "60")
                raise TTSRateLimitError(
                    f"Rate limit exceeded. Retry after {retry_after} seconds"
                )
            
            return await response.read()
```

### 7.3 错误传播和处理策略

#### 7.3.1 Provider 层

Provider 层捕获底层异常，转换为 TTS 异常：

```python
async def synthesize(self, text: str, **kwargs) -> bytes:
    try:
        # 调用底层 API
        response = await self.client.synthesize(text)
        return response.content
    
    except ConnectionError as e:
        raise TTSConnectionError(f"Connection failed: {e}")
    
    except ValueError as e:
        raise TTSConfigError(f"Invalid parameter: {e}")
    
    except Exception as e:
        raise TTSError(f"Synthesis failed: {e}")
```

#### 7.3.2 路由层

路由层捕获 TTS 异常，返回 HTTP 错误响应：

```python
# src/routes/tts.py

@router.post("/api/tts/synthesize")
async def synthesize_text(request: SynthesizeRequest):
    try:
        audio_data = await service_context.tts_engine.synthesize(
            text=request.text,
            voice_id=request.voice_id
        )
        return Response(content=audio_data, media_type="audio/mpeg")
    
    except TTSConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    
    except TTSConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    except TTSAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))
    
    except TTSRateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))
    
    except TTSError as e:
        raise HTTPException(status_code=500, detail=str(e))
```

#### 7.3.3 错误日志记录

所有异常都应记录到日志：

```python
import logging

logger = logging.getLogger(__name__)

async def synthesize(self, text: str, **kwargs) -> bytes:
    try:
        # TTS 合成逻辑
        ...
    except TTSConnectionError as e:
        logger.error(f"TTS connection error: {e}", exc_info=True)
        raise
    except TTSError as e:
        logger.error(f"TTS error: {e}", exc_info=True)
        raise
```

**参考代码路径**：
- atri LLM 异常：`atri/src/llm/exceptions.py`
- OLV TTS 异常：`refer-projects/Open-LLM-VTuber/src/open_llm_vtuber/tts/tts_interface.py`

---

## 8. 配置文件设计

### 8.1 YAML 配置结构

TTS 模块使用 YAML 配置文件，支持环境变量和多 Provider 配置。

```yaml
# config/tts_config.yaml

tts:
  # 当前激活的 Provider
  active_provider: "gpt_sovits_tts"
  
  # Provider 配置
  providers:
    # 云服务 Provider
    edge_tts:
      provider: "edge_tts"
      name: "Edge TTS"
      type: cloud
      health_check: true
      voice: "zh-CN-XiaoxiaoNeural"
      rate: 1.0
      pitch: 0
      format: "mp3"
    
    openai_tts:
      provider: "openai_tts"
      name: "OpenAI TTS"
      type: cloud
      health_check: true
      api_key: ${OPENAI_API_KEY}
      base_url: "https://api.openai.com/v1"
      model: "tts-1-hd"
      voice: "alloy"
      format: "mp3"
      sample_rate: 24000
    
    elevenlabs_tts:
      provider: "elevenlabs_tts"
      name: "ElevenLabs TTS"
      type: cloud
      health_check: true
      api_key: ${ELEVENLABS_API_KEY}
      base_url: "https://api.elevenlabs.io/v1"
      voice_id: "21m00Tcm4TlvDq8ikWAM"
      model_id: "eleven_monolingual_v1"
      stability: 0.5
      similarity_boost: 0.75
      format: "mp3"
    
    # 本地部署 Provider
    gpt_sovits_tts:
      provider: "gpt_sovits_tts"
      name: "GPT-SoVITS"
      type: local
      health_check: true
      required: false
      # 必需参数
      api_url: "http://127.0.0.1:9880/tts"
      text_lang: "zh"
      ref_audio_path: "./data/reference_audio/atri.wav"
      prompt_lang: "zh"
      prompt_text: "这是参考音频的文本内容"
      # 可选参数
      text_split_method: "cut5"
      batch_size: "1"
      media_type: "wav"
      streaming_mode: "false"
    
    cosyvoice2_tts:
      provider: "cosyvoice2_tts"
      name: "CosyVoice2"
      type: local
      health_check: true
      required: false
      base_url: "http://127.0.0.1:7860"
      speaker: "中文女"
      format: "wav"
    
    siliconflow_tts:
      provider: "siliconflow_tts"
      name: "SiliconFlow TTS"
      type: cloud
      health_check: true
      api_key: ${SILICONFLOW_API_KEY}
      base_url: "https://api.siliconflow.cn/v1"
      model: "fishaudio/fish-speech-1.4"
      voice: "zh-CN-female-1"
      format: "mp3"
```

### 8.2 各 Provider 的配置参数

#### 8.2.1 通用参数

所有 Provider 都支持的参数：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `provider` | string | ✅ | - | Provider ID |
| `name` | string | ✅ | - | 显示名称 |
| `type` | string | ✅ | - | Provider 类型（cloud/local） |
| `health_check` | boolean | ❌ | true | 是否启用健康检查 |
| `required` | boolean | ❌ | true | 是否必需（本地服务可选） |

#### 8.2.2 云服务参数

云服务 Provider 支持的参数：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `api_key` | string | ✅ | - | API 密钥（支持环境变量） |
| `base_url` | string | ❌ | - | API 基础 URL |
| `model` | string | ❌ | - | 模型 ID |
| `voice` | string | ❌ | - | 默认声音 ID |
| `format` | string | ❌ | mp3 | 输出格式（mp3/wav/ogg） |
| `sample_rate` | integer | ❌ | 24000 | 采样率 |

#### 8.2.3 本地部署参数

本地部署 Provider 支持的参数：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `api_url` / `base_url` | string | ✅ | - | 服务地址 |
| `ref_audio_path` | string | ⚠️ | - | 参考音频路径（GPT-SoVITS） |
| `prompt_text` | string | ⚠️ | - | 参考音频文本（GPT-SoVITS） |
| `speaker` | string | ❌ | - | 说话人（CosyVoice） |

### 8.3 环境变量支持

配置文件支持环境变量替换，格式为 `${VAR_NAME}`：

```yaml
openai_tts:
  api_key: ${OPENAI_API_KEY}  # 从环境变量读取
  base_url: ${OPENAI_BASE_URL:-https://api.openai.com/v1}  # 支持默认值
```

**环境变量加载**：

```python
# src/config.py

import os
import yaml
import re

def load_config(config_path: str = "config/tts_config.yaml") -> dict:
    """加载配置文件，支持环境变量替换"""
    
    with open(config_path, "r", encoding="utf-8") as f:
        config_str = f.read()
    
    # 替换环境变量
    def replace_env_var(match):
        var_name = match.group(1)
        default_value = match.group(2) if match.group(2) else None
        
        # 从环境变量获取值
        value = os.getenv(var_name, default_value)
        
        if value is None:
            raise ValueError(f"Environment variable {var_name} not set")
        
        return value
    
    # 支持 ${VAR} 和 ${VAR:-default} 格式
    config_str = re.sub(
        r'\$\{([A-Z_]+)(?::-(.*?))?\}',
        replace_env_var,
        config_str
    )
    
    return yaml.safe_load(config_str)
```

### 8.4 配置验证

启动时验证配置文件的完整性和正确性：

```python
# src/tts/config_validator.py

from pydantic import BaseModel, ValidationError
from typing import Literal, Optional

class TTSProviderConfig(BaseModel):
    provider: str
    name: str
    type: Literal["cloud", "local"]
    health_check: bool = True
    required: bool = True
    
    # 云服务参数
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    voice: Optional[str] = None
    
    # 本地部署参数
    api_url: Optional[str] = None
    ref_audio_path: Optional[str] = None
    prompt_text: Optional[str] = None

def validate_tts_config(config: dict) -> bool:
    """验证 TTS 配置"""
    try:
        # 验证 active_provider 存在
        active_provider = config["tts"]["active_provider"]
        if active_provider not in config["tts"]["providers"]:
            raise ValueError(f"Active provider {active_provider} not found")
        
        # 验证每个 Provider 配置
        for provider_id, provider_config in config["tts"]["providers"].items():
            TTSProviderConfig(**provider_config)
        
        return True
    
    except (KeyError, ValidationError) as e:
        logger.error(f"TTS config validation failed: {e}")
        return False
```

**参考代码路径**：
- OLV 配置：`refer-projects/Open-LLM-VTuber/conf.yaml`
- atri 配置加载：`atri/src/config.py`

---

## 9. 健康检查机制

### 9.1 健康检查触发时机

TTS 模块在 **4 个时机**触发健康检查：

1. **启动时检查**：服务器启动时检查所有 Provider
2. **定时检查**：每 5 分钟后台检查一次（可选）
3. **按需检查**：用户点击"刷新状态"按钮时
4. **切换前检查**：用户切换 Provider 前强制检查

### 9.2 健康检查实现逻辑

#### 9.2.1 启动时检查

```python
# src/service_context.py

class ServiceContext:
    async def initialize_tts(self):
        """初始化 TTS Provider"""
        tts_config = self.config["tts"]
        
        # 检查所有 Provider 的健康状态
        health_status = {}
        for provider_id, provider_config in tts_config["providers"].items():
            if not provider_config.get("health_check", True):
                continue
            
            try:
                # 创建 Provider 实例
                engine = TTSFactory.create(
                    name=provider_config["provider"],
                    **provider_config
                )
                
                # 执行健康检查
                is_healthy = await engine.health_check()
                health_status[provider_id] = is_healthy
                
                logger.info(f"TTS Provider {provider_id}: {'✅ healthy' if is_healthy else '❌ unhealthy'}")
            
            except Exception as e:
                health_status[provider_id] = False
                logger.error(f"TTS Provider {provider_id} initialization failed: {e}")
        
        # 初始化当前 Provider
        active_provider = tts_config["active_provider"]
        provider_config = tts_config["providers"][active_provider]
        
        self.tts_engine = TTSFactory.create(
            name=provider_config["provider"],
            **provider_config
        )
        
        # 如果当前 Provider 不健康，尝试降级到备用 Provider
        if not health_status.get(active_provider, False):
            logger.warning(f"Active TTS provider {active_provider} is unhealthy")
            
            # 查找健康的备用 Provider
            for provider_id, is_healthy in health_status.items():
                if is_healthy:
                    logger.info(f"Falling back to TTS provider: {provider_id}")
                    provider_config = tts_config["providers"][provider_id]
                    self.tts_engine = TTSFactory.create(
                        name=provider_config["provider"],
                        **provider_config
                    )
                    break
```

#### 9.2.2 定时检查（可选）

```python
# src/background_tasks.py

import asyncio

async def periodic_health_check(service_context: ServiceContext):
    """定时健康检查（每 5 分钟）"""
    while True:
        await asyncio.sleep(300)  # 5 分钟
        
        try:
            is_healthy = await service_context.tts_engine.health_check()
            
            if not is_healthy:
                logger.warning("TTS provider health check failed")
                # 可以触发告警或自动切换
        
        except Exception as e:
            logger.error(f"Health check error: {e}")
```

#### 9.2.3 按需检查

```python
# src/routes/tts.py

@router.get("/api/tts/providers/{provider_id}/health")
async def check_provider_health(provider_id: str):
    """检查指定 Provider 的健康状态"""
    try:
        # 获取 Provider 配置
        provider_config = service_context.config["tts"]["providers"][provider_id]
        
        # 创建 Provider 实例
        engine = TTSFactory.create(
            name=provider_config["provider"],
            **provider_config
        )
        
        # 执行健康检查
        is_healthy = await engine.health_check()
        
        return {
            "provider_id": provider_id,
            "healthy": is_healthy,
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

#### 9.2.4 切换前检查

```python
# src/routes/tts.py

@router.post("/api/tts/set-provider")
async def set_tts_provider(request: SetProviderRequest):
    """切换 TTS Provider（带健康检查）"""
    try:
        provider_id = request.provider_id
        provider_config = service_context.config["tts"]["providers"][provider_id]
        
        # 创建新 Provider 实例
        new_engine = TTSFactory.create(
            name=provider_config["provider"],
            **provider_config
        )
        
        # 强制执行健康检查
        is_healthy = await new_engine.health_check()
        
        if not is_healthy:
            raise HTTPException(
                status_code=503,
                detail=f"Provider {provider_id} is not available"
            )
        
        # 切换 Provider
        service_context.tts_engine = new_engine
        service_context.config["tts"]["active_provider"] = provider_id
        
        return {
            "success": True,
            "provider_id": provider_id,
            "message": f"Switched to TTS provider: {provider_id}"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 9.3 结果缓存策略

为避免频繁的健康检查，实现 **5 分钟 TTL 缓存**：

```python
# src/tts/health_cache.py

from datetime import datetime, timedelta
from typing import Dict, Optional

class HealthCheckCache:
    """健康检查结果缓存"""
    
    def __init__(self, ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, tuple[bool, datetime]] = {}
    
    def get(self, provider_id: str) -> Optional[bool]:
        """获取缓存的健康状态"""
        if provider_id not in self._cache:
            return None
        
        is_healthy, timestamp = self._cache[provider_id]
        
        # 检查是否过期
        if datetime.now() - timestamp > timedelta(seconds=self.ttl_seconds):
            del self._cache[provider_id]
            return None
        
        return is_healthy
    
    def set(self, provider_id: str, is_healthy: bool):
        """设置健康状态"""
        self._cache[provider_id] = (is_healthy, datetime.now())
    
    def invalidate(self, provider_id: str):
        """使缓存失效"""
        if provider_id in self._cache:
            del self._cache[provider_id]
    
    def clear(self):
        """清空缓存"""
        self._cache.clear()

# 全局缓存实例
health_cache = HealthCheckCache(ttl_seconds=300)
```

**使用缓存**：

```python
async def check_provider_health_cached(provider_id: str) -> bool:
    """带缓存的健康检查"""
    
    # 尝试从缓存获取
    cached_result = health_cache.get(provider_id)
    if cached_result is not None:
        return cached_result
    
    # 执行健康检查
    provider_config = service_context.config["tts"]["providers"][provider_id]
    engine = TTSFactory.create(
        name=provider_config["provider"],
        **provider_config
    )
    
    is_healthy = await engine.health_check()
    
    # 缓存结果
    health_cache.set(provider_id, is_healthy)
    
    return is_healthy
```

### 9.4 失败处理

健康检查失败时的处理策略：

1. **记录日志**：记录失败原因和时间
2. **返回状态**：返回 `False` 表示不可用
3. **不抛出异常**：健康检查失败不应中断服务
4. **自动降级**：如果当前 Provider 不健康，自动切换到备用 Provider

```python
async def health_check(self) -> bool:
    """健康检查（不抛出异常）"""
    try:
        # 执行健康检查逻辑
        ...
        return True
    
    except Exception as e:
        # 记录日志，但不抛出异常
        logger.error(f"Health check failed: {e}", exc_info=True)
        return False
```

**参考代码路径**：
- AIRI 健康检查：`refer-projects/airi/packages/stage-ui/src/stores/providers.ts`

---

## 10. API 接口设计

### 10.1 RESTful API 端点

TTS 模块提供 **5 个 RESTful API 端点**：

#### 10.1.1 GET /api/tts/providers

**功能**：获取所有 TTS Provider 列表及其健康状态

**请求**：
```http
GET /api/tts/providers
```

**响应**：
```json
{
  "active_provider": "gpt_sovits_tts",
  "providers": [
    {
      "id": "edge_tts",
      "name": "Edge TTS",
      "type": "cloud",
      "healthy": true,
      "models": [],
      "streaming": false
    },
    {
      "id": "gpt_sovits_tts",
      "name": "GPT-SoVITS",
      "type": "local",
      "healthy": true,
      "models": ["GPT-SoVITS"],
      "streaming": true
    }
  ]
}
```

**实现**：
```python
@router.get("/api/tts/providers")
async def get_tts_providers():
    """获取 TTS Provider 列表"""
    tts_config = service_context.config["tts"]
    active_provider = tts_config["active_provider"]
    
    providers = []
    for provider_id, provider_config in tts_config["providers"].items():
        # 检查健康状态（使用缓存）
        is_healthy = await check_provider_health_cached(provider_id)
        
        providers.append({
            "id": provider_id,
            "name": provider_config["name"],
            "type": provider_config["type"],
            "healthy": is_healthy,
            "models": provider_config.get("models", []),
            "streaming": provider_config.get("streaming", False)
        })
    
    return {
        "active_provider": active_provider,
        "providers": providers
    }
```

---

#### 10.1.2 GET /api/tts/providers/{id}/health

**功能**：检查指定 Provider 的健康状态

**请求**：
```http
GET /api/tts/providers/gpt_sovits_tts/health
```

**响应**：
```json
{
  "provider_id": "gpt_sovits_tts",
  "healthy": true,
  "timestamp": "2026-04-22T10:30:00Z"
}
```

**实现**：
```python
@router.get("/api/tts/providers/{provider_id}/health")
async def check_provider_health(provider_id: str):
    """检查 Provider 健康状态"""
    try:
        provider_config = service_context.config["tts"]["providers"][provider_id]
        
        engine = TTSFactory.create(
            name=provider_config["provider"],
            **provider_config
        )
        
        is_healthy = await engine.health_check()
        
        # 更新缓存
        health_cache.set(provider_id, is_healthy)
        
        return {
            "provider_id": provider_id,
            "healthy": is_healthy,
            "timestamp": datetime.now().isoformat()
        }
    
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

#### 10.1.3 POST /api/tts/set-provider

**功能**：切换 TTS Provider

**请求**：
```http
POST /api/tts/set-provider
Content-Type: application/json

{
  "provider_id": "gpt_sovits_tts"
}
```

**响应**：
```json
{
  "success": true,
  "provider_id": "gpt_sovits_tts",
  "message": "Switched to TTS provider: gpt_sovits_tts"
}
```

**实现**：
```python
class SetProviderRequest(BaseModel):
    provider_id: str

@router.post("/api/tts/set-provider")
async def set_tts_provider(request: SetProviderRequest):
    """切换 TTS Provider"""
    try:
        provider_id = request.provider_id
        provider_config = service_context.config["tts"]["providers"][provider_id]
        
        # 创建新 Provider
        new_engine = TTSFactory.create(
            name=provider_config["provider"],
            **provider_config
        )
        
        # 健康检查
        is_healthy = await new_engine.health_check()
        if not is_healthy:
            raise HTTPException(
                status_code=503,
                detail=f"Provider {provider_id} is not available"
            )
        
        # 切换 Provider
        service_context.tts_engine = new_engine
        service_context.config["tts"]["active_provider"] = provider_id
        
        return {
            "success": True,
            "provider_id": provider_id,
            "message": f"Switched to TTS provider: {provider_id}"
        }
    
    except HTTPException:
        raise
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

#### 10.1.4 GET /api/tts/voices

**功能**：获取指定 Provider 的声音列表

**请求**：
```http
GET /api/tts/voices?provider_id=edge_tts
```

**响应**：
```json
{
  "provider_id": "edge_tts",
  "voices": [
    {
      "id": "zh-CN-XiaoxiaoNeural",
      "name": "晓晓",
      "language": "zh-CN",
      "gender": "female"
    },
    {
      "id": "zh-CN-YunxiNeural",
      "name": "云希",
      "language": "zh-CN",
      "gender": "male"
    }
  ]
}
```

**实现**：
```python
@router.get("/api/tts/voices")
async def get_tts_voices(provider_id: Optional[str] = None):
    """获取声音列表"""
    try:
        # 如果未指定 provider_id，使用当前 Provider
        if provider_id is None:
            provider_id = service_context.config["tts"]["active_provider"]
            engine = service_context.tts_engine
        else:
            provider_config = service_context.config["tts"]["providers"][provider_id]
            engine = TTSFactory.create(
                name=provider_config["provider"],
                **provider_config
            )
        
        voices = await engine.get_voices()
        
        return {
            "provider_id": provider_id,
            "voices": voices
        }
    
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

#### 10.1.5 POST /api/tts/synthesize

**功能**：同步合成语音

**请求**：
```http
POST /api/tts/synthesize
Content-Type: application/json

{
  "text": "你好，世界",
  "voice_id": "zh-CN-XiaoxiaoNeural",
  "rate": 1.2,
  "pitch": 10
}
```

**响应**：
```http
HTTP/1.1 200 OK
Content-Type: audio/mpeg
Content-Length: 12345

<binary audio data>
```

**实现**：
```python
class SynthesizeRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None
    rate: Optional[float] = None
    pitch: Optional[int] = None
    volume: Optional[float] = None

@router.post("/api/tts/synthesize")
async def synthesize_text(request: SynthesizeRequest):
    """同步合成语音"""
    try:
        # 参数验证
        if not request.text or len(request.text) == 0:
            raise HTTPException(status_code=400, detail="Text is required")
        
        if len(request.text) > 5000:
            raise HTTPException(status_code=400, detail="Text too long (max 5000 characters)")
        
        # 合成语音
        audio_data = await service_context.tts_engine.synthesize(
            text=request.text,
            voice_id=request.voice_id,
            rate=request.rate,
            pitch=request.pitch,
            volume=request.volume
        )
        
        # 返回音频数据
        return Response(
            content=audio_data,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "attachment; filename=speech.mp3"
            }
        )
    
    except TTSConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except TTSConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TTSAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except TTSRateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except TTSError as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 10.2 请求/响应格式

#### 10.2.1 请求格式

所有 POST 请求使用 JSON 格式：

```json
{
  "text": "要合成的文本",
  "voice_id": "声音 ID（可选）",
  "rate": 1.2,
  "pitch": 10,
  "volume": 1.0
}
```

#### 10.2.2 响应格式

**成功响应**：
```json
{
  "success": true,
  "data": { ... },
  "message": "操作成功"
}
```

**错误响应**：
```json
{
  "detail": "错误信息"
}
```

### 10.3 错误码定义

| HTTP 状态码 | 错误类型 | 说明 |
|------------|---------|------|
| 200 | 成功 | 请求成功 |
| 400 | 参数错误 | 请求参数无效 |
| 404 | 未找到 | Provider 不存在 |
| 429 | 速率限制 | API 调用超过限制 |
| 500 | 服务器错误 | 内部错误 |
| 502 | 网关错误 | 上游 API 错误 |
| 503 | 服务不可用 | Provider 不可用 |

**参考代码路径**：
- atri 路由：`atri/src/routes/`
- FastAPI 文档：https://fastapi.tiangolo.com/

---

## 11. 性能优化

### 11.1 模型预加载

对于本地部署的 Provider，在服务启动时预加载模型，避免首次请求延迟。

```python
# src/service_context.py

async def preload_tts_models(self):
    """预加载 TTS 模型"""
    tts_config = self.config["tts"]
    
    for provider_id, provider_config in tts_config["providers"].items():
        if provider_config["type"] != "local":
            continue
        
        if not provider_config.get("required", True):
            continue
        
        try:
            logger.info(f"Preloading TTS model: {provider_id}")
            
            # 创建 Provider 实例
            engine = TTSFactory.create(
                name=provider_config["provider"],
                **provider_config
            )
            
            # 执行一次空合成，触发模型加载
            await engine.synthesize("测试")
            
            logger.info(f"TTS model preloaded: {provider_id}")
        
        except Exception as e:
            logger.warning(f"Failed to preload TTS model {provider_id}: {e}")
```

### 11.2 结果缓存

对于相同的文本和参数，缓存合成结果，避免重复计算。

```python
# src/tts/cache.py

from functools import lru_cache
import hashlib

class TTSCache:
    """TTS 结果缓存"""
    
    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self._cache: dict[str, bytes] = {}
    
    def _generate_key(self, text: str, voice_id: str, **kwargs) -> str:
        """生成缓存键"""
        key_str = f"{text}:{voice_id}:{kwargs}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, text: str, voice_id: str, **kwargs) -> bytes | None:
        """获取缓存"""
        key = self._generate_key(text, voice_id, **kwargs)
        return self._cache.get(key)
    
    def set(self, text: str, voice_id: str, audio_data: bytes, **kwargs):
        """设置缓存"""
        if len(self._cache) >= self.max_size:
            # LRU 淘汰
            self._cache.pop(next(iter(self._cache)))
        
        key = self._generate_key(text, voice_id, **kwargs)
        self._cache[key] = audio_data
    
    def clear(self):
        """清空缓存"""
        self._cache.clear()

# 全局缓存实例
tts_cache = TTSCache(max_size=100)
```

**使用缓存**：

```python
async def synthesize_with_cache(
    text: str,
    voice_id: Optional[str] = None,
    **kwargs
) -> bytes:
    """带缓存的合成"""
    
    # 尝试从缓存获取
    cached_audio = tts_cache.get(text, voice_id or "", **kwargs)
    if cached_audio is not None:
        logger.debug(f"TTS cache hit: {text[:20]}...")
        return cached_audio
    
    # 执行合成
    audio_data = await service_context.tts_engine.synthesize(
        text=text,
        voice_id=voice_id,
        **kwargs
    )
    
    # 缓存结果
    tts_cache.set(text, voice_id or "", audio_data, **kwargs)
    
    return audio_data
```

### 11.3 批处理支持

对于多个文本的合成请求，支持批处理以提高效率。

```python
# src/routes/tts.py

class BatchSynthesizeRequest(BaseModel):
    texts: list[str]
    voice_id: Optional[str] = None

@router.post("/api/tts/synthesize-batch")
async def synthesize_batch(request: BatchSynthesizeRequest):
    """批量合成语音"""
    if len(request.texts) > 10:
        raise HTTPException(status_code=400, detail="Too many texts (max 10)")
    
    results = []
    for text in request.texts:
        try:
            audio_data = await service_context.tts_engine.synthesize(
                text=text,
                voice_id=request.voice_id
            )
            results.append({
                "text": text,
                "success": True,
                "audio": base64.b64encode(audio_data).decode()
            })
        except Exception as e:
            results.append({
                "text": text,
                "success": False,
                "error": str(e)
            })
    
    return {"results": results}
```

### 11.4 内存管理

对于大文本的合成，分段处理以避免内存溢出。

```python
def split_text(text: str, max_length: int = 500) -> list[str]:
    """分段文本"""
    if len(text) <= max_length:
        return [text]
    
    # 按句子分割
    sentences = re.split(r'[。！？\n]', text)
    
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= max_length:
            current_chunk += sentence
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks

async def synthesize_long_text(text: str, **kwargs) -> bytes:
    """合成长文本"""
    chunks = split_text(text, max_length=500)
    
    audio_chunks = []
    for chunk in chunks:
        audio_data = await service_context.tts_engine.synthesize(
            text=chunk,
            **kwargs
        )
        audio_chunks.append(audio_data)
    
    # 合并音频
    return b"".join(audio_chunks)
```

---

## 12. 测试策略

### 12.1 单元测试

测试每个 Provider 的核心功能。

```python
# tests/test_tts_providers.py

import pytest
from src.tts.factory import TTSFactory
from src.tts.exceptions import TTSError

@pytest.mark.asyncio
async def test_edge_tts_synthesize():
    """测试 Edge TTS 合成"""
    engine = TTSFactory.create(
        "edge_tts",
        voice="zh-CN-XiaoxiaoNeural"
    )
    
    audio_data = await engine.synthesize("你好")
    
    assert isinstance(audio_data, bytes)
    assert len(audio_data) > 0

@pytest.mark.asyncio
async def test_edge_tts_get_voices():
    """测试 Edge TTS 获取声音列表"""
    engine = TTSFactory.create("edge_tts")
    
    voices = await engine.get_voices()
    
    assert isinstance(voices, list)
    assert len(voices) > 0
    assert "id" in voices[0]
    assert "name" in voices[0]

@pytest.mark.asyncio
async def test_edge_tts_health_check():
    """测试 Edge TTS 健康检查"""
    engine = TTSFactory.create("edge_tts")
    
    is_healthy = await engine.health_check()
    
    assert isinstance(is_healthy, bool)

@pytest.mark.asyncio
async def test_factory_register():
    """测试工厂注册"""
    providers = TTSFactory.list_providers()
    
    assert "edge_tts" in providers
    assert "openai_tts" in providers
    assert "gpt_sovits_tts" in providers

@pytest.mark.asyncio
async def test_factory_create_invalid():
    """测试创建不存在的 Provider"""
    with pytest.raises(TTSError):
        TTSFactory.create("invalid_provider")
```

### 12.2 集成测试

测试 API 端点的完整流程。

```python
# tests/test_tts_api.py

import pytest
from fastapi.testclient import TestClient
from src.app import app

client = TestClient(app)

def test_get_providers():
    """测试获取 Provider 列表"""
    response = client.get("/api/tts/providers")
    
    assert response.status_code == 200
    data = response.json()
    assert "active_provider" in data
    assert "providers" in data
    assert len(data["providers"]) > 0

def test_check_health():
    """测试健康检查"""
    response = client.get("/api/tts/providers/edge_tts/health")
    
    assert response.status_code == 200
    data = response.json()
    assert "provider_id" in data
    assert "healthy" in data

def test_set_provider():
    """测试切换 Provider"""
    response = client.post(
        "/api/tts/set-provider",
        json={"provider_id": "edge_tts"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

def test_get_voices():
    """测试获取声音列表"""
    response = client.get("/api/tts/voices?provider_id=edge_tts")
    
    assert response.status_code == 200
    data = response.json()
    assert "voices" in data
    assert len(data["voices"]) > 0

def test_synthesize():
    """测试合成语音"""
    response = client.post(
        "/api/tts/synthesize",
        json={"text": "你好"}
    )
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert len(response.content) > 0
```

### 12.3 性能测试

测试合成延迟和吞吐量。

```python
# tests/test_tts_performance.py

import pytest
import time
from src.tts.factory import TTSFactory

@pytest.mark.asyncio
async def test_synthesize_latency():
    """测试合成延迟"""
    engine = TTSFactory.create("edge_tts")
    
    start_time = time.time()
    await engine.synthesize("你好，世界")
    latency = time.time() - start_time
    
    # 延迟应小于 2 秒
    assert latency < 2.0

@pytest.mark.asyncio
async def test_synthesize_throughput():
    """测试合成吞吐量"""
    engine = TTSFactory.create("edge_tts")
    
    texts = ["测试文本" + str(i) for i in range(10)]
    
    start_time = time.time()
    for text in texts:
        await engine.synthesize(text)
    duration = time.time() - start_time
    
    throughput = len(texts) / duration
    
    # 吞吐量应大于 1 次/秒
    assert throughput > 1.0
```

### 12.4 测试覆盖率目标

- **单元测试覆盖率**：≥ 80%
- **集成测试覆盖率**：≥ 60%
- **关键路径覆盖率**：100%

**运行测试**：

```bash
# 运行所有测试
pytest tests/

# 运行单元测试
pytest tests/test_tts_providers.py

# 运行集成测试
pytest tests/test_tts_api.py

# 生成覆盖率报告
pytest --cov=src/tts --cov-report=html tests/
```

---

## 13. 部署和运维

### 13.1 模型文件管理

#### 13.1.1 模型下载

本地 Provider 需要下载模型文件：

```bash
# GPT-SoVITS 模型
mkdir -p atri/models/tts/gpt_sovits
cd atri/models/tts/gpt_sovits
wget https://huggingface.co/lj1995/GPT-SoVITS/resolve/main/GPT_SoVITS.pth
wget https://huggingface.co/lj1995/GPT-SoVITS/resolve/main/SoVITS_weights.pth

# CosyVoice2 模型
mkdir -p atri/models/tts/cosyvoice2
cd atri/models/tts/cosyvoice2
wget https://huggingface.co/FunAudioLLM/CosyVoice2/resolve/main/model.pt
```

#### 13.1.2 参考音频管理

GPT-SoVITS 需要参考音频进行音色克隆：

```bash
# 创建参考音频目录
mkdir -p atri/data/reference_audio

# 添加参考音频
cp your_reference_audio.wav atri/data/reference_audio/atri.wav
```

**参考音频要求**：
- 格式：WAV
- 采样率：16000 Hz 或 24000 Hz
- 时长：3-10 秒
- 内容：清晰的语音，无背景噪音

### 13.2 依赖安装

#### 13.2.1 Python 依赖

```bash
# 安装基础依赖
pip install -r requirements.txt

# 安装 TTS Provider 依赖
pip install edge-tts          # Edge TTS
pip install openai            # OpenAI TTS
pip install elevenlabs        # ElevenLabs TTS
pip install gradio-client     # CosyVoice2
pip install aiohttp           # HTTP 客户端
```

#### 13.2.2 系统依赖

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y ffmpeg libsndfile1

# macOS
brew install ffmpeg libsndfile

# Windows
# 下载 ffmpeg: https://ffmpeg.org/download.html
```

### 13.3 环境要求

#### 13.3.1 硬件要求

| Provider | CPU | GPU | 内存 | 磁盘 |
|----------|-----|-----|------|------|
| edge_tts | 1 核 | 不需要 | 512 MB | 100 MB |
| openai_tts | 1 核 | 不需要 | 512 MB | 100 MB |
| elevenlabs_tts | 1 核 | 不需要 | 512 MB | 100 MB |
| gpt_sovits_tts | 4 核 | 推荐 | 8 GB | 5 GB |
| cosyvoice2_tts | 4 核 | 推荐 | 6 GB | 3 GB |
| siliconflow_tts | 1 核 | 不需要 | 512 MB | 100 MB |

#### 13.3.2 软件要求

- Python 3.10+
- CUDA 11.8+ (GPU 加速)
- FFmpeg 4.0+

### 13.4 监控指标

#### 13.4.1 关键指标

| 指标 | 说明 | 告警阈值 |
|------|------|---------|
| 合成延迟 | 从请求到返回的时间 | > 3 秒 |
| 合成成功率 | 成功合成的请求比例 | < 95% |
| Provider 健康状态 | Provider 是否可用 | 不可用 |
| 错误率 | 错误请求的比例 | > 5% |
| 队列长度 | 等待处理的请求数 | > 10 |

#### 13.4.2 监控实现

```python
# src/monitoring.py

from prometheus_client import Counter, Histogram, Gauge

# 合成请求计数
tts_requests_total = Counter(
    "tts_requests_total",
    "Total TTS synthesis requests",
    ["provider", "status"]
)

# 合成延迟
tts_latency_seconds = Histogram(
    "tts_latency_seconds",
    "TTS synthesis latency",
    ["provider"]
)

# Provider 健康状态
tts_provider_health = Gauge(
    "tts_provider_health",
    "TTS provider health status",
    ["provider"]
)

# 使用示例
async def synthesize_with_metrics(text: str, **kwargs) -> bytes:
    provider_id = service_context.config["tts"]["active_provider"]
    
    with tts_latency_seconds.labels(provider=provider_id).time():
        try:
            audio_data = await service_context.tts_engine.synthesize(
                text=text,
                **kwargs
            )
            tts_requests_total.labels(provider=provider_id, status="success").inc()
            return audio_data
        
        except Exception as e:
            tts_requests_total.labels(provider=provider_id, status="error").inc()
            raise
```

---

## 14. 扩展指南

### 14.1 如何添加新的 Provider

添加新的 TTS Provider 只需 4 个步骤：

#### 步骤 1：创建 Provider 文件

```python
# src/tts/providers/new_provider.py

from ..factory import TTSFactory
from ..interface import TTSInterface
from ..exceptions import TTSError

@TTSFactory.register("new_provider")
class NewProviderTTS(TTSInterface):
    """新的 TTS Provider"""
    
    def __init__(self, api_key: str, **kwargs):
        self.api_key = api_key
        # 初始化逻辑
    
    async def synthesize(self, text: str, voice_id: Optional[str] = None, **kwargs) -> bytes:
        """同步合成"""
        # 实现合成逻辑
        pass
    
    async def synthesize_stream(self, text: str, voice_id: Optional[str] = None, **kwargs) -> AsyncIterator[bytes]:
        """流式合成（可选）"""
        raise NotImplementedError("流式合成暂未实现")
    
    async def get_voices(self) -> list[dict]:
        """获取声音列表"""
        # 实现获取声音列表逻辑
        pass
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 实现健康检查逻辑
            return True
        except Exception:
            return False
```

#### 步骤 2：导入 Provider

```python
# src/tts/providers/__init__.py

from . import edge_tts
from . import openai_tts
from . import elevenlabs_tts
from . import gpt_sovits_tts
from . import cosyvoice2_tts
from . import siliconflow_tts
from . import new_provider  # 添加新 Provider
```

#### 步骤 3：添加配置

```yaml
# config/tts_config.yaml

tts:
  providers:
    new_provider:
      provider: "new_provider"
      name: "New Provider"
      type: cloud
      health_check: true
      api_key: ${NEW_PROVIDER_API_KEY}
      # 其他配置参数
```

#### 步骤 4：测试

```python
# tests/test_new_provider.py

import pytest
from src.tts.factory import TTSFactory

@pytest.mark.asyncio
async def test_new_provider_synthesize():
    engine = TTSFactory.create(
        "new_provider",
        api_key="test_key"
    )
    
    audio_data = await engine.synthesize("测试")
    assert isinstance(audio_data, bytes)
```

### 14.2 自定义 Provider 开发流程

#### 14.2.1 开发流程

1. **需求分析**：确定 Provider 的功能和参数
2. **接口设计**：设计 API 调用方式
3. **实现代码**：实现 TTSInterface 的所有方法
4. **单元测试**：编写测试用例
5. **集成测试**：测试与系统的集成
6. **文档编写**：编写使用文档

#### 14.2.2 最佳实践

1. **遵循接口规范**：严格实现 TTSInterface 的所有方法
2. **异常处理**：使用 TTS 异常体系，不要抛出原始异常
3. **日志记录**：记录关键操作和错误信息
4. **配置验证**：在 `__init__` 中验证必需参数
5. **健康检查**：实现轻量级的健康检查逻辑
6. **性能优化**：考虑缓存、批处理等优化手段

#### 14.2.3 代码模板

```python
# src/tts/providers/template.py

from typing import Optional, AsyncIterator
from ..factory import TTSFactory
from ..interface import TTSInterface
from ..exceptions import TTSError, TTSConnectionError, TTSAPIError
import logging

logger = logging.getLogger(__name__)

@TTSFactory.register("template")
class TemplateTTS(TTSInterface):
    """TTS Provider 模板"""
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.example.com",
        **kwargs
    ):
        """初始化"""
        # 参数验证
        if not api_key:
            raise TTSConfigError("API key is required")
        
        self.api_key = api_key
        self.base_url = base_url
        
        logger.info(f"Initialized TemplateTTS with base_url: {base_url}")
    
    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """同步合成"""
        try:
            # 实现合成逻辑
            logger.debug(f"Synthesizing text: {text[:50]}...")
            
            # TODO: 调用 API
            audio_data = b""  # 替换为实际实现
            
            logger.info(f"Synthesis completed, audio size: {len(audio_data)} bytes")
            return audio_data
        
        except ConnectionError as e:
            raise TTSConnectionError(f"Connection failed: {e}")
        except Exception as e:
            raise TTSError(f"Synthesis failed: {e}")
    
    async def synthesize_stream(
        self,
        text: str,
        voice_id: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[bytes]:
        """流式合成（可选）"""
        raise NotImplementedError("流式合成暂未实现")
    
    async def get_voices(self) -> list[dict]:
        """获取声音列表"""
        try:
            # TODO: 调用 API 获取声音列表
            voices = []  # 替换为实际实现
            
            logger.info(f"Retrieved {len(voices)} voices")
            return voices
        
        except Exception as e:
            raise TTSError(f"Failed to get voices: {e}")
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # TODO: 实现健康检查逻辑
            # 例如：调用 API 的 /health 端点
            
            logger.debug("Health check passed")
            return True
        
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
```

### 14.3 配置扩展

如果新 Provider 需要特殊配置，可以扩展配置结构：

```python
# src/tts/types.py

class CustomProviderConfig(TTSConfig):
    """自定义 Provider 配置"""
    custom_param1: str
    custom_param2: int
    custom_param3: Optional[bool] = False
```

---

## 15. 总结

### 15.1 设计亮点

1. **装饰器工厂模式**：新增 Provider 无需修改工厂类，扩展性强
2. **统一接口抽象**：所有 Provider 实现相同接口，调用方式一致
3. **健康检查机制**：4 个触发时机 + 5 分钟缓存，确保高可用
4. **5 层异常体系**：精确定位错误类型，便于调试和监控
5. **配置驱动设计**：支持环境变量，易于部署和管理
6. **性能优化**：模型预加载、结果缓存、批处理支持

### 15.2 与 ASR 模块的一致性

TTS 模块与 ASR 模块保持高度一致的架构设计：

| 设计要素 | TTS 模块 | ASR 模块 | 一致性 |
|---------|---------|---------|--------|
| 工厂模式 | 装饰器注册 | 装饰器注册 | ✅ |
| 接口设计 | TTSInterface (4 方法) | ASRInterface (4 方法) | ✅ |
| 异常层次 | 5 个异常类 | 5 个异常类 | ✅ |
| 健康检查 | 返回 bool | 返回 bool | ✅ |
| 配置结构 | YAML + 环境变量 | YAML + 环境变量 | ✅ |
| API 设计 | 5 个端点 | 5 个端点 | ✅ |

### 15.3 实现路径

**参考代码路径**：
- **OLV TTS 实现**：`refer-projects/Open-LLM-VTuber/src/open_llm_vtuber/tts/`
- **AIRI TTS 实现**：`refer-projects/airi/packages/stage-ui/src/lib/tts/`
- **atri LLM 层**：`atri/src/llm/` (装饰器工厂模式)
- **atri ASR 模块**：`atri/src/asr/` (架构参考)

### 15.4 下一步工作

1. **实现 TTS 模块**：按照本文档实现 6 个 Provider
2. **编写单元测试**：确保每个 Provider 功能正常
3. **集成到 FastAPI**：实现 5 个 API 端点
4. **性能测试**：测试合成延迟和吞吐量
5. **文档完善**：编写 API 文档和使用指南

---

**文档完成日期**：2026-04-22  
**文档版本**：v1.0  
**维护者**：atri 开发团队

