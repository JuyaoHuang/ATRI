---
status: active
owner: agent
created: 2026-07-09
updated: 2026-07-11
source:
  - src/agent/persona.py
  - src/agent/chat_agent.py
  - src/service_context.py
  - src/routes/chat_ws.py
related_code:
  - src/agent/persona.py
  - src/agent/chat_agent.py
  - src/service_context.py
  - src/routes/chat_ws.py
  - src/routes/chats.py
  - src/vision/models.py
---

# Agent 模块总设计

本文把 `agent` 模块的整体设计接起来。现有文档已经分别讲了 `Persona` 和 `ChatAgent`，但还缺一页说明：

1. Agent 模块在整个系统里扮演什么角色。
2. `Persona`、`ChatAgent`、`ServiceContext` 三者如何协同。
3. 为什么缓存键和记忆作用域要这样设计。

## 模块定位

当前 Agent 模块是“把角色、记忆和 LLM 调用拼成一个可聊天对象”的组合层。

它不做底层模型推理，也不直接管理聊天持久化文件。它的核心任务是：

- 加载角色级静态配置；
- 为某个 `(character_id, user_id, chat_id)` 组装一条聊天会话；
- 调用记忆模块构建上下文；
- 驱动 LLM 流式输出；
- 在成功路径结束后，把这一轮提交回记忆模块。

## 设计目标

当前长期目标可以概括为 4 条：

1. 让“角色配置”和“会话运行时”明确分离。
2. 让同一角色下的不同聊天拥有独立短期记忆。
3. 让长期记忆按 `(character_id, user_id)` 共享，而不是按聊天标题隔离。
4. 让调用方只拿到一个 `ChatAgent` 门面，不必自己管理 Persona、记忆与 LLM 的组合。

## 模块组成

当前 Agent 模块实际由三部分组成：

| 组件 | 代码 | 职责 |
| --- | --- | --- |
| 角色配置 | `src/agent/persona.py` | 解析 persona Markdown + frontmatter。 |
| 会话门面 | `src/agent/chat_agent.py` | 面向一条聊天会话暴露 `chat()` / `chat_collect()`。 |
| 生命周期容器 | `src/service_context.py` | 缓存 `ChatAgent` 和长期记忆实例，并在进程关闭时统一清理。 |

## `Persona` 的位置

`Persona` 当前只承载角色级静态数据：

- `character_id`
- `name`
- `avatar`
- `greeting`
- `system_prompt`
- 可选描述和时间戳元数据

长期约束：

- `character_id` 来自文件名和调用参数，不从 frontmatter 再定义第二份真相；
- frontmatter 是展示元数据；
- Markdown 正文是原样交给 LLM 的 system prompt。

因此 `Persona` 更像“角色卡的后端解析表示”，不是会话状态。

## `ChatAgent` 的位置

`ChatAgent` 是一次聊天会话的组合门面。它持有三项依赖：

- `LLMInterface`
- `MemoryManager`
- `Persona`

当前成功路径稳定顺序是：

```text
InputInform(input_text, image?)
  -> input_text -> memory_manager.build_llm_context(...)
  -> messages + image? -> llm.chat_completion_stream(...)
  -> collect reply chunks
  -> input_text + reply -> memory_manager.on_round_complete(...)
```

长期约束：

- Agent 自己不清洗用户输入；
- `input_text.content` 原样传给 `MemoryManager`；
- 可选图片只传给 LLM 调用边界；
- L1 清洗在记忆模块内部发生；
- `Persona.system_prompt` 通过 `build_llm_context()` 注入，而不是再额外给 LLM 传第二份 system。

## 错误路径边界

`ChatAgent` 当前对 `LLMError` 的稳定处理是保持异常控制流：

- 不生成错误哨兵 chunk；
- 不调用 `memory_manager.append_system_note()`；
- 不调用 `on_round_complete()`；
- 把异常传播给路由编排层。

这和 VAD interrupt 的半截回复路径不同：

- VAD partial reply 可能可见、可审计；
- LLM 调用失败由路由发送瞬态 `output:chat:error`，不进入 archive 或有效轮次。

如果模型以成功响应自然生成拒绝视觉等文本，它仍是普通成功轮次。只有 Provider/SDK 异常才进入 generation failure。

## `ServiceContext` 的位置

`ServiceContext` 是进程级容器，不是聊天本身的一部分。它负责：

- 按 key 复用 `ChatAgent`
- 按 key 复用 `LongTermMemory`
- 为关闭时统一刷写和释放资源

这是当前 Agent 模块能在 WebSocket 路径里持续保持短期记忆状态的关键。

## 缓存键设计

### `ChatAgent` 缓存键

当前 `ChatAgent` 缓存键是：

```text
(character_id, user_id, chat_id)
```

意义：

- 同一用户 + 同一角色 + 不同聊天标题
  -> 两个独立 `ChatAgent`
  -> 两套独立短期记忆

### `LongTermMemory` 缓存键

长期记忆缓存键是：

```text
(character_id, user_id)
```

意义：

- 同一用户与同一角色的不同聊天标题
  -> 共享长期事实
  -> 不共享短期状态

这组键是当前 Agent/Memory 协同里最重要的不变量之一。

## 与 WebSocket 路径的关系

当前 `src/routes/chat_ws.py` 是 Agent 模块的主要业务入口。它负责：

- 解析 `input:text`
- 通过 `ServiceContext` 获取对应 `ChatAgent`
- 驱动流式输出到前端
- 在 VAD / ASR 自动提交时再次复用同一套 Agent 获取逻辑

这意味着 Agent 模块并不知道消息是“键盘输入”还是“ASR 转写”；它只接收一段文本和当前上下文。

## 与 `/api/chats` 的关系

`src/routes/chats.py` 不通过 `ChatAgent` 生成聊天标题，而是直接走 `create_from_role('title_gen', ...)`。

这说明：

- 不是所有对话相关能力都属于 Agent；
- Agent 只负责“角色驱动聊天本身”；
- 标题生成仍然只是一个旁路 LLM 调用。

## `runtime_context` 注入边界

`ChatAgent.chat()` 接受可选 `runtime_context`，并把它转交给 `MemoryManager.build_llm_context()`。

当前长期约束：

- Agent 自己不解释 datetime 等运行时上下文；
- 只负责把它带进记忆模块；
- 最终如何插入 LLM payload，由记忆模块定义。

这保证了上下文拼接逻辑仍然集中在记忆层，而不会在 Agent 层和 Memory 层各写一半。

## 从近期 git log 确认的长期事实

近期主线日志虽然主要落在 VAD / ASR / TTS，但它们反过来确认了 Agent 的几个长期边界：

- `add chat generation state`
- `cancel chat task on speech start`
- `persist VAD generation identity`

这些提交说明：

1. 一条聊天 generation 在 WebSocket 路径里是显式对象。
2. Agent 输出可能被 VAD 中断。
3. 被中断的 generation 与正常完成的 generation，记忆语义不同。

因此 Agent 模块后续扩展时，不能再假设“每次 chat() 都一定完整结束并直接计入一轮”。

## 与旧设计和当前专题文档的取舍

目前 Agent 没有一份对应旧 `module-design` 的长讨论稿；它的设计更多来自当前实现和项目架构约束。

已经沉淀为当前事实的有：

- Persona Markdown + frontmatter
- `ChatAgent` 成功/错误路径
- `ServiceContext` 的缓存键
- 长期记忆跨聊天共享、短期记忆按聊天隔离

仍未扩展成更复杂系统的部分包括：

- 更细粒度的 agent policy 层
- 多角色协作
- tool-driven persona 行为链

## 相关文档

- [persona.zh-CN.md](persona.zh-CN.md)
- [chat-agent.zh-CN.md](chat-agent.zh-CN.md)
- [../llm/design.zh-CN.md](../llm/design.zh-CN.md)
- [../memory/design.zh-CN.md](../memory/design.zh-CN.md)
