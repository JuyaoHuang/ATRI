---
status: active
owner: agent
created: 2026-07-09
updated: 2026-07-11
related_code:
  - src/agent/chat_agent.py
  - src/service_context.py
  - src/memory/manager.py
  - src/routes/chat_ws.py
  - src/vision/models.py
  - frontend/src/composables/useChat.ts
---

# ChatAgent 设计说明

`ChatAgent` 是 Agent 模块的对话组合层。它不拥有独立业务状态，只把 `Persona`、`LLMInterface` 和 `MemoryManager` 串成一个可流式消费的聊天入口。

## 依赖关系

```text
ServiceContext
  -> load_persona(character_id)
  -> create_from_role("chat", llm_config)
  -> MemoryManager(...)
  -> ChatAgent(llm, memory_manager, persona)
```

`ServiceContext` 负责缓存与复用：

- `ChatAgent` 按 `(character_id, user_id, chat_id)` 缓存。
- `LongTermMemory` 按 `(character_id, user_id)` 缓存。

因此不同聊天标题拥有独立短期记忆，但仍能共享同一用户与同一角色之间的长期事实。

## 对外接口

`ChatAgent` 公开两个方法：

| 方法 | 作用 |
| --- | --- |
| `chat(user_input, runtime_context=None, commit_round=True)` | 接受 `str | InputInform`，流式产出 LLM 文本块。 |
| `chat_collect(user_input, runtime_context=None, commit_round=True)` | 接受相同输入，收集 `chat()` 的全部输出。 |

原始字符串会被规范化为纯文本 `InputInform`。`chat_collect()` 没有独立的 LLM 调用途径，只是迭代 `chat()`，因此默认也会遵守同样的提交与异常语义。

## 成功路径

直接调用 `ChatAgent.chat()` 且保留 `commit_round=True` 时，成功路径如下：

1. 把输入规范化为 `InputInform(input_text, image?)`。
2. 只取 `input_text.content` 作为 `MemoryManager.build_llm_context()` 的用户文本，并传入 `persona.system_prompt`。
3. 若调用方提供 `runtime_context`，一并传给 `build_llm_context()`。
4. `MemoryManager` 返回已经组装好的 OpenAI 风格纯文本 `messages` 列表。
5. 若本轮有图片，调用 `llm.chat_completion_stream(messages, input_image=image)`；否则保持原有纯文本调用。
6. `ChatAgent` 逐块 `yield` 给上层，同时在内存中拼接完整回复。
7. 流结束后，如果 `commit_round=True`，只用文本和 AI 回复调用一次 `memory_manager.on_round_complete(...)`。

一个关键约束是：`ChatAgent` 不会再次把 `persona.system_prompt` 以 `system=` 关键字传给 `LLMInterface`。系统提示已经在 `build_llm_context()` 中写入 `messages`，再次前置会导致重复注入。

图片不会传给 `MemoryManager`，也不会出现在 `on_round_complete()` 的消息中。它只在当前 LLM 调用期间存在。

## 错误路径

`ChatAgent` 不把 LLM 异常转换成文本，也不生成错误哨兵。Provider 抛出的 `LLMError` 会原样保持异常控制流并传播给调用方。

因此 LLM 失败时：

- 不会额外 `yield` 一段看似正常的 AI 文本；
- 不调用 `append_system_note()`；
- 不调用 `on_round_complete()`；
- 不把失败原因或 Provider 原始消息写入 Memory。

生产 WebSocket 路径由 `src/routes/chat_ws.py` 统一决定安全展示。若 failure 发生在 durable success effects 开始前，路由发送固定的 `output:chat:error`，并让该 generation 进入 failed 终态。该瞬态提示只存在于当前前端页面，不进入聊天归档或 Memory。

如果模型以 HTTP 200 正常生成“无法查看图片”等自然语言，这仍是成功回复，不属于异常路径。

## Raw 与 Cleaned 语义

`ChatAgent` 自己不做文本清洗，它只处理原始输入和原始 LLM 输出。

### 用户输入

- `InputInform.input_text.content` 原样传给 `MemoryManager.build_llm_context()`。
- `InputInform.input_text.content` 原样传给 `MemoryManager.on_round_complete()`。
- `InputInform.image` 不进入任何 Memory 方法。
- L1 Snip 清洗发生在 `MemoryManager.on_round_complete()` 内部，而不是 `ChatAgent` 内部。

这意味着：

- `ChatAgent` 看见的是 raw user input。
- `short_term_memory.json` 和 memory archive 中保存的人类消息内容，是 `MemoryManager` 清洗后的版本。
- 前端聊天存储 `data/chats/...` 中的消息是否保留原始文本，取决于 WebSocket/REST 调用路径，而不取决于 `ChatAgent`。

### AI 输出

- `ChatAgent` 将 LLM 返回的 chunk 原样透传，不做正文清洗。
- 只在回复去掉空白后长度小于 10 字符时记录 WARNING，作为上游截断的观测信号。
- 这个 WARNING 不会触发自动重试，也不会改变提交逻辑。

## `runtime_context` 注入

当前前端会在 `input:text` 消息里附带 `client_context`，其来源是 `frontend/src/composables/useChat.ts`：

```json
{
  "datetime": {
    "iso": "2026-07-09T12:34:56.000Z",
    "local": "2026/7/9 20:34:56",
    "time_zone": "Asia/Shanghai",
    "utc_offset": "UTC+08:00"
  }
}
```

`ChatAgent` 只负责把这个对象透传给 `MemoryManager`。真正的序列化发生在 `MemoryManager._serialize_runtime_context()`：

- 当前只识别 `datetime` 模块。
- 会被渲染成隐藏的 `<context>` 片段。
- 只追加到本轮最终的用户消息，不会写入 `recent_messages`、`chat_history` 或 `long_term.add()`。

因此 `runtime_context` 是“本轮调用时可见、会后不持久化”的附加上下文。

## 与 WebSocket 路径的关系

`src/routes/chat_ws.py` 当前不是直接使用 `ChatAgent` 的自动提交模式，而是：

1. 构造 `InputInform(input_text, image?)`。
2. 调用 `agent.chat(..., commit_round=False)`。
3. 成功流结束后，先把纯文本用户消息和 AI 回复写入聊天存储。
4. 再手动调用 `agent.memory_manager.on_round_complete(...)`。
5. 最后发送 `output:chat:complete`。

这样做的原因是聊天存储需要先落盘，再向客户端发送 `output:chat:complete`。对维护者来说，这意味着：

- `ChatAgent` 的默认成功路径和 WebSocket 的生产路径并不完全相同。
- `output:chat:complete`、`output:chat:error` 和 VAD interrupt 在 generation send lock 内竞争首个终态。
- pre-success generation failure 不允许进入 ChatStorage、Memory、上下文压缩或长期记忆。
- durable success 已开始后的辅助持久化/Memory 失败不能再伪装成 generation failure。
- 调整错误处理或 round commit 语义时，要同时检查 `ChatAgent`、`src/routes/chat_ws.py` 和前端 `failActiveGeneration()`。

## 相关文档

- [Agent 模块长期设计入口](README.zh-CN.md)
- [Persona 技术说明](persona.zh-CN.md)
- [Memory 模块长期设计入口](../memory/README.zh-CN.md)
- [Vision 模块长期设计入口](../vision/README.zh-CN.md)
