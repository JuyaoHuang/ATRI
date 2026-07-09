---
status: active
owner: tts
created: 2026-07-09
updated: 2026-07-09
source:
  - ../../module-design/CN/TTS模块设计文档.md
  - src/tts/interface.py
  - src/tts/factory.py
  - src/tts/service.py
  - src/routes/tts.py
related_code:
  - src/tts/interface.py
  - src/tts/factory.py
  - src/tts/service.py
  - src/tts/config.py
  - src/routes/tts.py
---

# TTS 接口与工厂设计

本文沉淀 `src/tts/` 的稳定接口面。它回答三个问题：

1. Provider 必须实现什么。
2. Provider 如何被注册、发现和实例化。
3. 路由层如何通过 `TTSService` 消费这套接口。

## 分层定位

当前 TTS 模块可以稳定拆成 5 层：

| 层 | 代码 | 职责 |
| --- | --- | --- |
| 路由层 | `src/routes/tts.py` | 暴露 REST 接口，做请求模型绑定与异常映射。 |
| 服务层 | `src/tts/service.py` | 统一配置、Provider 健康、切换、声音列表和文本合成。 |
| 配置层 | `src/tts/config.py` | 读写 YAML，做深合并、敏感字段保留和磁盘补丁保存。 |
| 工厂层 | `src/tts/factory.py` | 维护 Provider 注册表和静态元数据。 |
| 接口层 | `src/tts/interface.py` | 定义 Provider 最小实现面。 |

长期约束是：路由层不直接 new Provider，Provider 也不直接读写 YAML。两者都通过 `TTSService` 聚合。

## 接口数据结构

### `TTSHealth`

`TTSHealth` 是轻量健康结果，不是一次远程探活任务：

```python
TTSHealth(
    available: bool,
    reason: str | None = None,
)
```

它用于：

- `list_providers()` 返回每个 Provider 当前是否可用；
- `health()` 汇总活跃 Provider 和全量 Provider 状态；
- `synthesize()` 前做最后一次同步可用性判断。

它不承担：

- 长耗时网络探针；
- 自动重试；
- 自动 fallback 到其他 Provider。

### `TTSVoice`

`TTSVoice` 是设置页和选择器展示用的稳定语音元数据：

```python
TTSVoice(
    id: str,
    name: str,
    language: str | None = None,
    gender: str | None = None,
    description: str | None = None,
    preview_url: str | None = None,
)
```

长期约束：

- `id` 必须可直接传回 `synthesize(voice_id=...)`。
- 其余字段都属于展示增强字段，不应成为后端协议必填项。

### `TTSProviderMetadata`

`TTSProviderMetadata` 由工厂层维护，服务于 Provider 列表端点：

```python
TTSProviderMetadata(
    name: str,
    display_name: str,
    provider_type: str,
    supports_streaming: bool,
    media_type: str,
    description: str,
)
```

这份元数据是“静态声明”，不是运行时配置。它决定：

- 前端如何展示 Provider 名称与类型；
- 默认 `media_type`；
- 当前 Provider 是否声明支持流式。

## `TTSInterface` 契约

所有 Provider 都继承 `TTSInterface`。当前稳定类属性有：

| 属性 | 含义 |
| --- | --- |
| `provider_name` | 注册后写入的唯一 Provider 名。 |
| `supports_streaming` | 是否声明支持原生流式。当前内置 Provider 都是 `False`。 |
| `media_type` | 默认音频 MIME 类型。 |
| `config` | Provider 初始化时收到的配置快照。 |

### `synthesize()`

```python
async def synthesize(
    text: str,
    *,
    voice_id: str | None = None,
    **kwargs: Any,
) -> bytes
```

稳定语义：

- 输入是最终要朗读的纯文本。
- 返回值必须是完整音频字节，不返回文件路径、不返回 base64。
- 编码格式由 Provider 的 `media_type` 决定。

`kwargs` 是 Provider 扩展位，但长期要求是：

- 未识别参数由具体 Provider 自己决定忽略还是报错；
- 路由层不做 Provider 级参数解释；
- 前端只允许写入 `TTSService` 明确开放的白名单字段。

### `synthesize_stream()`

```python
async def synthesize_stream(...) -> AsyncIterator[bytes]
```

当前它是预留接口，默认抛 `NotImplementedError`。

这条约束很关键：`modules/tts/streaming-design.zh-CN.md` 里的分段流式化，**不是**基于这里的原生流式接口，而是应用层把文本切段后，多次调用 `synthesize()`。

### `get_voices()`

```python
async def get_voices() -> list[TTSVoice]
```

长期要求：

- 可以返回空列表，但不能返回不稳定的裸字典结构。
- 声音列表读取失败时，由 Provider 抛异常，上层统一映射到 API 错误。

### `health()`

```python
def health() -> TTSHealth
```

这是同步、低成本、自解释的就绪判断。它适合检查：

- 必需配置是否存在；
- 本地服务地址是否已配置；
- 必需包或最小前置条件是否满足。

不适合在这里做：

- 每次都发远程探活请求；
- 长时间模型预热；
- 带副作用的初始化。

## 工厂注册流程

当前 Provider 注册流程依赖导入副作用：

```text
import src.tts.providers
  -> provider module imports
  -> @TTSFactory.register(...)
  -> provider class enters class-scoped registry
```

### 注册

`TTSFactory.register(name, metadata=...)` 会做三件事：

1. 把 `provider_name`、`supports_streaming`、`media_type` 写到类属性。
2. 把 Provider 类写入 `_registry`。
3. 把静态元数据写入 `_metadata`。

### 发现

`TTSFactory.available()` 返回当前已注册 Provider 名称列表。

### 实例化

`TTSFactory.create(name, **kwargs)`：

- 根据 `name` 查注册表；
- 找不到时抛 `ValueError`；
- 找到后把 `kwargs` 直接传给 Provider 构造函数。

这意味着 Provider 构造函数本身就是配置边界的一部分。它必须能接受配置层传下来的字段，并对缺失或非法配置给出可读失败。

## 服务层接口

`TTSService` 是路由层唯一长期入口。

### 配置相关

| 方法 | 作用 |
| --- | --- |
| `get_config()` | 返回掩码后的当前配置。 |
| `update_config()` | 深合并局部补丁，可选择持久化。 |
| `switch_provider()` | 更新 `tts_model`。 |

关键约束：

- 敏感字段在返回 API 时统一掩码为 `********`。
- 被掩码的敏感值再次提交时会被剔除，不覆盖现有真实值。
- Provider 配置存在前端写白名单，不允许前端修改全部字段。

### 状态相关

| 方法 | 作用 |
| --- | --- |
| `list_providers()` | 返回元数据、当前健康状态、激活状态、公开配置。 |
| `health()` | 汇总活跃 Provider 和全量 Provider 健康。 |
| `get_voices()` | 获取当前或指定 Provider 的声音列表。 |

### 合成相关

`synthesize()` 的长期语义是：

1. 先去空白，空文本直接抛 `TTSSynthesisError`。
2. 解析当前或指定 Provider。
3. 用 `health()` 做最后一次可用性检查。
4. 调用 Provider `synthesize()`。
5. 返回：

```python
{
    "provider": provider_name,
    "audio": audio_bytes,
    "media_type": tts.media_type,
}
```

这里不做：

- 自动切备用 Provider；
- 结果缓存；
- 批量合成；
- 长文本自动拆段。

这些能力如果未来要加，应显式落在服务层或独立编排层，而不是偷偷塞进 Provider 基类。

## 路由层异常映射

`src/routes/tts.py` 当前把领域异常映射为 HTTP 状态码：

| 异常 | HTTP |
| --- | --- |
| `TTSConfigError` | `400` |
| `TTSProviderUnavailableError` | `503` |
| `TTSRateLimitError` | `429` |
| `TTSAPIError` | `502` |
| `TTSSynthesisError` | `400` |
| 其他异常 | `500` |

这条映射的意义是：Provider 和服务层只表达领域失败，不直接依赖 HTTP。

## Provider 扩展清单

新增 Provider 时，长期上至少要完成这些点：

1. 在 `src/tts/providers/xxx.py` 实现 `TTSInterface`。
2. 用 `@TTSFactory.register(...)` 提供稳定元数据。
3. 在 `src/tts/providers/__init__.py` 被导入。
4. 决定本 Provider 的 `media_type` 和 `supports_streaming` 声明。
5. 补充 `config/tts_config.yaml` 默认配置或兼容分支。
6. 若前端允许改部分字段，补 `PROVIDER_WRITE_ALLOWLISTS`。
7. 确保 `health()` 失败理由可读。
8. 确保 `get_voices()` 输出 `TTSVoice` 列表。

如果未来真的引入 Provider 原生流式：

- 先把 `supports_streaming=True` 与 `synthesize_stream()` 一起实现；
- 再单独设计服务层和 WebSocket 如何消费它；
- 不应直接复用当前“文本切段 + 多次 `synthesize()`”的协议语义。

## 与旧设计文档的取舍

旧 `TTS模块设计文档.md` 中这些部分没有直接迁到当前长期文档：

- 6 Provider 全量现状描述：当前代码并不成立。
- 结果缓存、批量合成、自动 fallback：当前实现没有落地，不应写成既成事实。
- Provider 原生流式作为主路径：与当前实现相反。

保留并迁移的，是仍然成立的设计骨架：

- 抽象接口；
- 装饰器工厂注册；
- 服务层聚合；
- 细粒度异常分层；
- 配置驱动与前后端所有权边界。

## 相关文档

- [design.zh-CN.md](design.zh-CN.md)
- [config.zh-CN.md](config.zh-CN.md)
- [streaming-design.zh-CN.md](streaming-design.zh-CN.md)
- [../../api/rest.zh-CN.md](../../api/rest.zh-CN.md)
