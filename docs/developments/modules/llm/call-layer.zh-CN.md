---
status: active
owner: llm
created: 2026-07-09
updated: 2026-07-11
related_code:
  - src/llm/__init__.py
  - src/llm/interface.py
  - src/llm/factory.py
  - src/llm/exceptions.py
  - src/llm/multimodal.py
  - src/llm/providers/openai_compatible.py
  - src/llm/providers/siliconflow.py
  - src/llm/providers/xiaomi.py
  - config/llm_config.yaml
  - src/service_context.py
  - src/routes/chats.py
---

# LLM 调用层设计

本文描述当前仓库中的 LLM 调用层，也就是 `src/llm/` 目录提供的无状态接口、工厂注册表、Provider 封装和错误边界。

## 模块边界

调用层负责：

- 定义统一的聊天调用契约
- 从配置解析具体 Provider
- 统一异常类型
- 把可选的当前轮图片序列化为 Provider 支持的多模态消息
- 为后续 tool calling 预留接口形态

调用层不负责：

- Persona 与记忆上下文组装
- 重试策略
- 向用户展示什么错误文案
- mem0 内部事实抽取模型的配置

## 导入约定

`src/llm/__init__.py` 有一个重要副作用：导入包时会自动导入内置 Provider 模块，从而完成注册。

这意味着下游只需要：

```python
from src.llm import create_from_role
```

不需要手动再导入 `src.llm.providers.*`。

## 接口契约

核心接口是 `LLMInterface`：

```python
class LLMInterface(ABC):
    def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        *,
        input_image: InputImage | None = None,
    ) -> AsyncIterator[str]:
        ...

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        *,
        input_image: InputImage | None = None,
    ) -> str:
        ...
```

设计约束：

- 接口是无状态的，不在实例上保存 system prompt 或 history。
- 子类必须实现 `chat_completion_stream()`。
- `chat_completion()` 默认通过收集流式结果实现；子类可以覆盖，但当前内置 Provider 没有覆盖。
- `input_image` 只表示当前轮的一张短生命周期图片，不是历史附件集合。

### 消息形态

`messages` 使用 OpenAI 风格词汇：

- `user`
- `assistant`
- `system`

如果上游内部仍使用 `human` / `ai`，应在进入调用层前完成映射。当前这一步由 `MemoryManager.build_llm_context()` 负责。

### 当前轮图片

当 `input_image` 存在时，`build_multimodal_messages()` 只把最后一条当前 `user` 消息改造成：

```json
{
  "role": "user",
  "content": [
    { "type": "text", "text": "当前用户文本" },
    {
      "type": "image_url",
      "image_url": {
        "url": "data:image/jpeg;base64,<opaque-base64>",
        "detail": "auto"
      }
    }
  ]
}
```

稳定约束：

- 没有图片时返回原有纯文本消息形态；
- 有图片时复制列表与最终 user mapping，不原地修改调用方数据；
- 历史 user 消息保持纯文本；
- 最后一条消息不是当前 user 时拒绝组装；
- 当前只允许 `detail=auto|low|high`；
- 图片内容不得进入日志、异常消息或完整 request params 输出。

OpenAI-compatible 与 Xiaomi 的 SDK 异常会映射为原有 `LLMConnectionError`、`LLMRateLimitError` 或 `LLMAPIError`，但项目异常只使用固定安全文本。映射在离开 SDK `except` 后抛出，不保留可能回显 data URL 的原始 message、cause 或 context；路由仍只向前端发送固定 generation failure 文案。

## 工厂与角色映射

### 注册表

`LLMFactory` 通过装饰器注册 Provider：

```python
@LLMFactory.register("openai_compatible")
class OpenAICompatibleLLM(LLMInterface):
    ...
```

对维护者来说，新增 Provider 的最低要求是：

1. 新建一个实现 `LLMInterface` 的类
2. 用 `@LLMFactory.register("<name>")` 注册
3. 在 `config/llm_config.yaml` 中增加对应配置分支

不需要修改工厂核心代码。

### `create_from_role()`

当前主入口是：

```python
create_from_role(role: str, llm_config: dict[str, Any]) -> LLMInterface
```

解析顺序：

1. 从 `llm_roles[role]` 找到池名
2. 从 `llm_configs[pool_name]` 找到配置条目
3. 解析激活 Provider 分支
4. 调用 `LLMFactory.create(provider, **kwargs)`

当前仓库里，角色映射不止聊天与压缩，还包含标题生成：

```yaml
llm_roles:
  chat: chat_main
  l3_compress: compress_light
  l4_compact: compress_light
  title_gen: title_gen
```

因此，角色集合是开放的，只要配置里声明即可。

## 配置形态

当前工厂支持两种配置形态：

### 单 Provider 形态

```yaml
chat_main:
  provider: openai_compatible
  model: gpt-4o
  base_url: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}
```

### 多 Provider 分支形态

```yaml
chat_main:
  provider: siliconflow
  providers:
    openai_compatible:
      model: deepseek-ai/DeepSeek-V4-Flash
      ...
    siliconflow:
      model: deepseek-ai/DeepSeek-V4-Flash
      image_detail: auto
      ...
    xiaomi:
      model: mimo-v2.5-pro
      ...
```

当前代码只验证激活分支的占位符。未激活分支保留 `${ENV_VAR}` 也不会阻断启动，这让同一个配置池可以安全容纳多个备用 Provider。

## 当前内置 Provider

| 注册名 | 实现类 | 说明 |
| --- | --- | --- |
| `openai` | `OpenAICompatibleLLM` | 复用 OpenAI 协议路径。 |
| `siliconflow` | `SiliconFlowLLM` | 独立 Provider，继承通用 OpenAI 兼容实现。 |
| `openai_compatible` | `OpenAICompatibleLLM` | 通用 OpenAI `/v1/chat/completions` 兼容实现。 |
| `xiaomi` | `XiaomiLLM` | 小米 MiMo 的兼容实现，单独收口 `request_options`。 |

### `OpenAICompatibleLLM`

特点：

- 使用 `openai.AsyncOpenAI`
- 支持 `model`、`base_url`、`api_key`、`temperature`
- 当 `system` 存在时，会在消息列表前追加一条 `role=system`
- 只产出非空 `delta.content`
- 通过 `build_multimodal_messages()` 支持可选的当前轮单图

### `SiliconFlowLLM`

SiliconFlow 使用 OpenAI 兼容协议，但拥有独立的模块、类和
`@LLMFactory.register("siliconflow")` 注册入口。

当前类继承 `OpenAICompatibleLLM`，因此保持原有构造参数、流式调用、单图消息
序列化和异常映射行为。独立类为后续 SiliconFlow 专用请求参数、多模态差异或
错误处理提供扩展位置，而不把这些差异继续堆入通用 Provider。

SiliconFlow 的 endpoint、model、API key 和 temperature 仍全部来自
`config/llm_config.yaml`，Provider 不硬编码服务地址或模型。

Provider 支持多模态消息形态不代表当前配置的模型一定具备视觉能力。例如纯文本
模型可能拒绝请求，也可能以 HTTP 200 正常生成“无法查看图片”。前者按 SDK
异常进入 `LLMError`，后者仍作为成功文本流处理。

### `XiaomiLLM`

与通用兼容实现的区别在于，它会从 `request_options` 中显式透传一组小米特有参数，例如：

- `max_completion_tokens`
- `top_p`
- `stop`
- `frequency_penalty`
- `presence_penalty`
- `extra_body`

这让小米专有的请求形态不会污染通用 Provider。

Xiaomi Provider 同样通过共享 helper 组装当前轮单图，但最终能力仍取决于所选
MiMo 模型和上游协议支持。

## 错误边界

调用层统一暴露四类异常：

| 异常 | 含义 |
| --- | --- |
| `LLMError` | 调用层基类 |
| `LLMConnectionError` | 连接失败、超时、TLS 等问题 |
| `LLMRateLimitError` | 速率限制或配额问题 |
| `LLMAPIError` | 其他 API 级失败 |

Provider 会把 SDK 自身异常翻译成这些项目内异常。调用层本身不做重试，也不会向流里注入错误文本。

这意味着：

- `ChatAgent` 可以只依赖 `LLMError` 家族，而不用感知具体 SDK
- 标题生成、压缩器、主聊天可以各自决定自己的失败策略
- 原始 Provider 错误不应直接回显给前端，也不得连同完整多模态请求写入日志

## `tools` 预留

`LLMInterface` 已经包含 `tools` 参数，但当前所有内置 Provider 都忽略它。

这条预留的边界是：

- 允许未来增加 tool calling
- 不要求现有调用方现在就构造 tools payload
- 不改变当前流式/非流式接口的形态

如果将来接入 tool calling，优先在 Provider 内部消化具体协议差异，而不是改写上层的角色映射或记忆拼装逻辑。

## 相关文档

- [LLM 模块长期设计入口](README.zh-CN.md)
- [Agent / ChatAgent 设计说明](../agent/chat-agent.zh-CN.md)
- [长期记忆设计](../memory/long-term-memory.zh-CN.md)
- [Vision 模块长期设计](../vision/README.zh-CN.md)
