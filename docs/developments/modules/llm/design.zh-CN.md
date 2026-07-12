---
status: active
owner: llm
created: 2026-07-09
updated: 2026-07-11
source:
  - ../../module-design/CN/LLM调用层设计讨论.md
  - src/llm/interface.py
  - src/llm/factory.py
  - src/llm/exceptions.py
  - src/service_context.py
  - src/routes/chats.py
related_code:
  - src/llm/interface.py
  - src/llm/factory.py
  - src/llm/exceptions.py
  - src/llm/multimodal.py
  - src/llm/providers/openai_compatible.py
  - src/llm/providers/siliconflow.py
  - src/llm/providers/xiaomi.py
  - src/service_context.py
  - src/routes/chats.py
---

# LLM 模块总设计

本文把 `src/llm/` 的整体设计接起来。现有 `call-layer.zh-CN.md` 已经描述了接口与工厂细节，但还缺一页说明：

1. LLM 调用层在整个系统里的位置。
2. 角色映射和 Provider 池为什么这样设计。
3. 上层哪些模块依赖它，哪些事情刻意不放在这里做。

## 模块定位

当前 LLM 模块是一个**无状态调用层**。它不拥有聊天上下文、不拥有角色状态，也不拥有重试策略。它只负责：

- 定义统一的调用契约；
- 把角色名映射到配置池；
- 根据配置池实例化具体 Provider；
- 把当前轮可选图片转换为 Provider 多模态消息；
- 把 SDK 级错误翻译成项目内异常。

它在系统中的位置更接近：

```text
Persona / Memory / Route
  -> build messages
  -> create_from_role(...)
  -> LLMInterface
  -> provider SDK
```

## 设计目标

结合旧设计讨论和当前实现，长期目标已经收敛为 6 条：

1. 调用层必须保持无状态，避免 history 和 system prompt 被悄悄缓存到实例里。
2. Provider 扩展必须通过装饰器注册，而不是修改工厂核心代码。
3. 一套配置池要能服务多个角色出口：主聊天、压缩器、标题生成等。
4. 错误只在这里被归一化，不在这里决定重试或降级。
5. 为未来 tool calling 预留形态，但不让预留能力污染当前主链路。
6. 图片只属于当前调用，不能反向污染历史 messages 或 Memory。

## 模块组成

当前 `src/llm/` 可以稳定拆成五部分：

| 组件 | 代码 | 职责 |
| --- | --- | --- |
| 接口层 | `interface.py` | 定义 `chat_completion_stream()` / `chat_completion()` 双接口。 |
| 工厂层 | `factory.py` | Provider 注册表、角色映射、配置池解析。 |
| 异常层 | `exceptions.py` | `LLMError` 及其子类。 |
| 多模态辅助层 | `multimodal.py` | 纯函数化组装最终当前 user 的单图消息。 |
| Provider 实现层 | `providers/` | 适配具体 SDK 和接口差异。 |

## 上游依赖者

当前真正消费 LLM 模块的上游主要有三类：

| 上游 | 角色 |
| --- | --- |
| `ServiceContext` -> `ChatAgent` | `chat` |
| `MemoryManager` 压缩器 | `l3_compress` / `l4_compact` |
| `src/routes/chats.py` 标题生成 | `title_gen` |

这三类调用共享同一套工厂和异常层，但各自拥有不同的上层策略：

- 主聊天：流式输出、错误要反馈给前端；
- 压缩器：后台总结、失败不应破坏短期状态主流程；
- 标题生成：失败直接 fallback。

这正是“调用层只抛异常，不做策略”的设计价值。

## 无状态契约

`LLMInterface` 当前的长期约束是：

- `system` 每次调用显式传入；
- `messages` 每次调用显式传入；
- `input_image` 作为可选关键字参数显式传入；
- Provider 实例上不保存对话历史；
- 非流式接口默认只是收集流式结果。

`input_image` 不代表 Provider 实例会保存附件。helper 只复制当前调用的最终 user message；历史上下文仍由 MemoryManager 以纯文本组装。

这意味着：

- 上下文拼接责任明确落在 `MemoryManager.build_llm_context()`；
- Persona 注入责任落在 `ChatAgent`；
- 调用层自己不知道“你是谁”“上一轮说了什么”。

## 角色映射与配置池

当前工厂不是“按 Provider 名直接创建”，而是“按角色名解析到配置池”：

```text
role
  -> llm_roles[role]
  -> pool key
  -> llm_configs[pool key]
  -> active provider branch
  -> LLMFactory.create(provider, **kwargs)
```

这个设计的长期好处有三个：

1. 调用方只关心角色，不关心底层供应商。
2. 同一角色可以在不改代码的情况下换 Provider。
3. 一个配置池可以保留多个备用分支，只激活一个。

## 单 Provider 与多 Provider 分支

当前支持两种配置形态：

1. 单 Provider：

```yaml
chat_main:
  provider: openai_compatible
  model: ...
  api_key: ...
```

2. 多 Provider 分支：

```yaml
chat_main:
  provider: siliconflow
  providers:
    openai_compatible: ...
    siliconflow: ...
    xiaomi: ...
```

长期约束：

- 只验证当前激活分支；
- 未激活分支可以保留未解析的 `${ENV_VAR}`；
- 这样一份 YAML 可以安全容纳多个后备出口，而不影响当前运行。

## Provider 生命周期

当前 Provider 生命周期很轻：

```text
import src.llm
  -> import providers for registration
create_from_role(...)
  -> resolve config
  -> instantiate provider
  -> make one call
```

这意味着：

- 当前没有全局 LLM Provider 池；
- 也没有长生命周期连接对象缓存；
- 调用层设计更偏“按调用构造门面”，而不是“维持长期会话”。

这和 `ASRService` 的本地模型常驻缓存形成了鲜明对比，也是当前设计有意为之：LLM Provider 的主要成本和状态都在远端，不像本地 ASR 模型需要长驻。

## 当前 Provider 现实

当前内置 Provider 有三种实现类：

- `OpenAICompatibleLLM`
- `SiliconFlowLLM`
- `XiaomiLLM`

但注册名有多种：

- `openai`
- `siliconflow`
- `openai_compatible`
- `xiaomi`

这里的长期约束是：

- “注册名”不等于“实现类数量”；
- SiliconFlow 通过独立类和注册模块建立扩展边界，同时继承通用 OpenAI
  兼容协议实现；
- 调用方只看到角色和配置池，不需要知道 Provider 之间的继承与复用关系。
- Provider 能接受多模态消息不等于当前模型一定具备视觉能力，最终能力由配置中的 model 决定。

## 错误所有权

当前异常层设计非常克制：

- `LLMConnectionError`
- `LLMRateLimitError`
- `LLMAPIError`
- `LLMError`

调用层负责：

- SDK 错误到项目异常的翻译。

调用层不负责：

- 自动重试；
- fallback 到第二个 Provider；
- 给前端写错误文案；
- 记录或回显完整多模态请求与图片 Base64；
- 记日志之外的行为纠正。

因此：

- `ChatAgent` 可以在流式聊天里决定怎样处理 `LLMError`；
- `src/routes/chats.py` 可以在标题生成失败时直接降级；
- 记忆压缩器可以选择 best-effort。

## `tools` 预留的边界

旧设计讨论里已经确定 tool calling 只预留接口，不在 MVP 实现。当前代码保持这一决策：

- 接口有 `tools` 参数；
- 所有内置 Provider 都忽略它；
- 上游调用方当前也不依赖它。

长期约束是：

- 若未来引入 tool calling，优先在 Provider 内部吸收协议差异；
- 不重写 `MemoryManager` 或 `ChatAgent` 的职责边界；
- 不让“预留参数”提前变成上游的强制负担。

## 与 Agent / Memory 的关系

### 与 `ChatAgent`

`ChatAgent` 负责：

- Persona system prompt；
- 当前用户输入；
- 从记忆模块拿到完整上下文；
- 再调用 LLM。

因此 LLM 模块看到的是已经组装好的消息，而不是原始聊天语义。

### 与 `MemoryManager`

`MemoryManager` 有两种方式消费 LLM：

1. `build_llm_context()` 不直接调 LLM，只负责组装消息。
2. L3/L4 压缩通过 `llm_factory_fn(role)` 获取专用压缩模型。

这意味着压缩器和主聊天虽然都走 `src/llm/`，但它们的角色语义、成本模型和失败容忍度完全不同。

### 与 `mem0`

`mem0` 自己使用的 embedding / fact extraction / local deploy LLM，不走这里的 `llm_roles` 池，而走 `memory_config.yaml`。

这是当前系统里必须明确的一条边界，否则很容易误以为“所有模型调用都由 `src/llm/` 统一管理”。

## 与旧设计讨论的取舍

旧 `LLM调用层设计讨论.md` 中，已经被当前实现吸收的核心结论包括：

- 装饰器工厂模式
- 流式 + 非流式双接口
- 多出口配置池 + 角色引用
- 错误只抛异常
- `tools` 预留但暂不实现

当前还没有被当成既成事实写入的，是那些仍停留在讨论或可扩展层面的内容，例如更复杂的 Provider 生态、正式 tool calling 工作流等。

## 相关文档

- [call-layer.zh-CN.md](call-layer.zh-CN.md)
- [../agent/chat-agent.zh-CN.md](../agent/chat-agent.zh-CN.md)
- [../memory/design.zh-CN.md](../memory/design.zh-CN.md)
- [../vision/README.zh-CN.md](../vision/README.zh-CN.md)
