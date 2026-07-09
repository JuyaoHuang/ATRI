---
status: active
owner: asr
created: 2026-07-09
updated: 2026-07-09
source:
  - ../../module-design/CN/ASR模块设计文档.md
  - src/asr/interface.py
  - src/asr/factory.py
  - src/asr/service.py
  - src/routes/asr.py
related_code:
  - src/asr/interface.py
  - src/asr/factory.py
  - src/asr/service.py
  - src/asr/config.py
  - src/asr/exceptions.py
  - src/routes/asr.py
---

# ASR 接口与工厂设计

本文沉淀 `src/asr/` 的稳定接口面。重点说明：

1. Provider 必须实现什么契约。
2. 工厂如何注册和实例化 Provider。
3. 服务层如何把上传转录、常驻本地模型和前端配置 API 汇总起来。

## 分层定位

当前 ASR 模块可以稳定拆成 5 层：

| 层 | 代码 | 职责 |
| --- | --- | --- |
| 路由层 | `src/routes/asr.py` | 暴露 REST 配置接口和上传转录端点。 |
| 服务层 | `src/asr/service.py` | 聚合配置、Provider 健康、切换、上传转录和本地 Provider 常驻缓存。 |
| 配置层 | `src/asr/config.py` | 读写 `config/asr_config.yaml`，做深合并和敏感字段保护。 |
| 工厂层 | `src/asr/factory.py` | 维护 Provider 注册表和能力元数据。 |
| 接口层 | `src/asr/interface.py` | 定义 Provider 最小实现面与默认 WAV 适配逻辑。 |

长期约束是：路由层不直接操作模型，Provider 也不直接读写 YAML。两者都通过 `ASRService` 汇合。

## 接口数据结构

### `ASRHealth`

`ASRHealth` 是同步、低成本的可用性结果：

```python
ASRHealth(
    available: bool,
    reason: str | None = None,
)
```

用途：

- Provider 列表里展示当前可用性；
- 活跃 Provider 健康汇总；
- 上传转录前做最后一次就绪判断。

它不承担：

- 重量级模型预热；
- 持续后台探针；
- 自动切备用 Provider。

### `ASRAudioUploadMetadata`

`ASRAudioUploadMetadata` 表达浏览器上传时声明的音频契约：

```python
ASRAudioUploadMetadata(
    source: str | None = None,
    sample_rate: int | None = None,
    channels: int | None = None,
    encoding: str | None = None,
)
```

它用于让后端在默认 WAV 适配路径上验证：

- 前端声称的采样率是否与文件实际内容一致；
- channels / encoding 是否匹配；
- 上传协议是否被意外破坏。

这也是近期 `git log` 里 `validate traditional asr wav upload contracts` 这类提交真正沉淀下来的长期设计点。

## `ASRInterface` 契约

所有 Provider 都继承 `ASRInterface`。当前稳定类属性有：

| 属性 | 含义 |
| --- | --- |
| `provider_name` | 注册后写入的唯一 Provider 名。 |
| `supports_backend_transcription` | 是否支持后端文件转录。 |
| `supports_browser_streaming` | 是否适合浏览器原生语音识别路径。 |
| `config` | Provider 初始化时收到的配置快照。 |

### 核心同步契约：`transcribe_np()`

```python
def transcribe_np(audio: Any) -> str
```

这是本地 Provider 的核心同步契约，输入是：

- 16 kHz
- 单声道
- float32 数组

长期意义是：无论本地模型内部如何实现，进入模型前的数据面都统一成一套 OLV 风格数组格式。

### 异步包装：`async_transcribe_np()`

```python
async def async_transcribe_np(audio: Any) -> str
```

默认通过 `asyncio.to_thread()` 委托给 `transcribe_np()`，让 Provider 只写同步模型逻辑，也避免阻塞 FastAPI 事件循环。

### 默认上传转录：`async_transcribe_audio()`

```python
async def async_transcribe_audio(
    audio: bytes,
    *,
    filename: str | None = None,
    content_type: str | None = None,
    upload_metadata: ASRAudioUploadMetadata | None = None,
) -> str
```

默认实现只承担一件事：

1. 把 PCM WAV 上传转换成 OLV 风格 float32 数组。
2. 再调用 `async_transcribe_np()`。

这意味着：

- 本地 Provider 至少天然支持符合契约的 WAV 上传；
- 若某个 Provider 能解码更多格式，应自行覆盖此方法；
- 当前系统并没有把所有上传格式都统一交给 ffmpeg 预处理。

### 预加载：`preload()` / `async_preload()`

`preload()` 是同步钩子，`async_preload()` 默认放到线程里执行。

当前设计意图：

- 本地惰性模型 Provider 可在这里完成模型加载；
- 默认实现只做可用性检查；
- 是否在服务启动期预加载，由 `ASRService.preload_active_provider()` 和配置共同决定。

### 健康判断：`health()`

`health()` 默认返回 `available=True`，由具体 Provider 覆盖检查：

- Python 依赖是否已安装；
- 本地模型文件或服务地址是否存在；
- 云 Provider 必需凭据是否配置。

它不应偷偷执行一次真正转录。

## 默认 WAV 契约

`ASRInterface.audio_bytes_to_float32_array()` 当前是上传转录的公共默认适配器。

长期约束：

- 只接受看起来像 WAV 的输入；
- 支持 8/16/32-bit PCM WAV；
- 采样率必须等于 `16000`；
- 多声道会被平均降混成单声道；
- 最终输出被裁剪到 `[-1, 1]` 的 float32。

当上传 metadata 与文件事实不一致时，会抛 `ASRTranscriptionError`。

这条规则直接决定：

- 浏览器录音上传和传统表单上传要么严格满足 16 kHz WAV 契约；
- 要么由具体 Provider 自己覆盖并支持更宽输入格式。

## 工厂注册流程

当前 ASR Provider 采用装饰器注册：

```text
import src.asr.providers
  -> provider module imports
  -> @ASRFactory.register(...)
  -> provider class enters class-scoped registry
```

### `ASRProviderMetadata`

工厂层维护的静态元数据包括：

```python
ASRProviderMetadata(
    name: str,
    display_name: str,
    provider_type: str,
    supports_backend_transcription: bool,
    supports_browser_streaming: bool,
    description: str,
)
```

这份元数据的长期作用是：

- 前端列表展示；
- 决定浏览器侧是否走 Web Speech 路径；
- 决定后端是否允许把它作为 `/api/asr/transcribe` 的目标。

### 注册与实例化

`ASRFactory.register()` 会把能力标志写回类属性，再放入类级 `_registry` / `_metadata`。

`ASRFactory.create(name, **kwargs)`：

- 按 Provider 名查找；
- 找不到时抛 `ValueError`；
- 找到后把配置直接传给构造函数。

这意味着 Provider 构造函数本身就是配置边界的一部分。

## 服务层设计

`ASRService` 是路由层唯一长期入口。

### 配置与切换

| 方法 | 作用 |
| --- | --- |
| `get_config()` | 返回掩码后的配置。 |
| `update_config()` | 深合并局部补丁，持久化后清理 Provider 缓存。 |
| `switch_provider()` | 更新 `asr_model`，并丢弃旧缓存实例。 |

长期约束：

- 敏感字段在 API 响应里统一掩码；
- 掩码值再次提交时会被剔除；
- `persistent_provider` / `preload_provider` 是后端专有根字段，前端 patch 会被忽略；
- Provider 配置仍有前端写白名单。

### Provider 常驻缓存

`ASRService` 和 `TTSService` 的一个关键差异，是它支持本地 Provider 常驻实例缓存：

- `_provider_cache`
- `_provider_locks`
- `_cache_lock`

缓存只在以下条件同时满足时启用：

1. `persistent_provider=true`
2. `provider_type == local`
3. `supports_backend_transcription=true`
4. Provider 不是 `web_speech_api`

这样做的原因是：

- 本地 ASR 模型加载成本高；
- 同一个 recognizer 常常不具备安全并发性；
- 因此前端并发上传时，服务层要复用同一实例并串行进入转录。

这条设计已经被近期 VAD/ASR 联调日志证明是当前系统的重要稳定行为。

### 预加载

`preload_active_provider()` 只在 `preload_provider=true` 且当前 provider 适合常驻缓存时执行。

当前它不是全局“把所有 ASR 都预热”的机制，只是对活跃本地 Provider 的定向预加载。

### 上传转录

`transcribe_audio()` 的长期步骤是：

1. 解析当前或指定 Provider。
2. 检查该 Provider 是否支持后端转录。
3. 若走常驻模式，复用缓存实例并串行加锁。
4. 调用 `async_transcribe_audio()`。
5. 返回：

```python
{
    "provider": provider_name,
    "text": transcription,
}
```

这里不做：

- 多 Provider 自动 fallback；
- 后端持续流式转录 WebSocket；
- 统一批处理转录。

## 路由层异常映射

`src/routes/asr.py` 当前把领域异常映射为：

| 异常 | HTTP |
| --- | --- |
| `ASRConfigError` | `400` |
| `ASRProviderUnavailableError` | `503` |
| `ASRTranscriptionError` | `400` |
| 其他异常 | `500` |

这意味着 Provider 和服务层只描述 ASR 失败，不依赖 HTTP。

## Provider 扩展清单

新增 ASR Provider 时，长期上至少要完成：

1. 在 `src/asr/providers/xxx.py` 实现 `ASRInterface`。
2. 用 `@ASRFactory.register(...)` 声明能力元数据。
3. 被 `src/asr/providers/__init__.py` 导入。
4. 明确它是否支持：
   - 后端上传转录
   - 浏览器原生识别路径
5. 如需前端写部分字段，补 `PROVIDER_WRITE_ALLOWLISTS`。
6. 若需要本地常驻模型，保证 `preload()` 和线程安全边界清晰。
7. 若支持非 WAV 上传，覆盖 `async_transcribe_audio()`。

## 与旧设计文档的取舍

旧 `ASR模块设计文档.md` 中这些部分没有直接迁入当前长期文档：

- 独立 ASR WebSocket；
- 统一流式 `transcribe_stream()` 主路径；
- 已经不在当前代码里的旧 Provider 现状描述；
- 批处理、缓存、性能优化等未落地能力。

迁移保留下来的，是当前代码仍然执行的骨架：

- `ASRInterface` 契约；
- 装饰器工厂注册；
- 上传 WAV 契约；
- 服务层常驻 Provider 缓存；
- 路由层异常映射；
- 前后端配置所有权边界。

## 相关文档

- [architecture.zh-CN.md](architecture.zh-CN.md)
- [config.zh-CN.md](config.zh-CN.md)
- [provider-matrix.zh-CN.md](provider-matrix.zh-CN.md)
- [../../api/rest.zh-CN.md](../../api/rest.zh-CN.md)
