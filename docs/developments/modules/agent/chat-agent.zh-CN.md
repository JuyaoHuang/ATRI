---
status: active
owner: agent
created: 2026-07-09
updated: 2026-07-09
related_code:
  - src/agent/chat_agent.py
  - src/service_context.py
  - src/memory/manager.py
  - src/routes/chat_ws.py
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
| `chat(user_input, runtime_context=None, commit_round=True)` | 流式产出 LLM 文本块。 |
| `chat_collect(user_input, runtime_context=None, commit_round=True)` | 收集 `chat()` 的全部输出并返回一个完整字符串。 |

`chat_collect()` 没有独立的 LLM 调用途径，只是迭代 `chat()`，因此默认也会遵守同样的提交语义。

## 成功路径

直接调用 `ChatAgent.chat()` 且保留 `commit_round=True` 时，成功路径如下：

1. 取 `persona.system_prompt` 作为 `MemoryManager.build_llm_context()` 的 `system_prompt` 参数。
2. 若调用方提供 `runtime_context`，一并传给 `build_llm_context()`。
3. `MemoryManager` 返回已经组装好的 OpenAI 风格 `messages` 列表。
4. `ChatAgent` 调用 `llm.chat_completion_stream(messages)`，逐块 `yield` 给上层，同时在内存中拼接完整回复。
5. 流结束后，如果 `commit_round=True`，调用一次 `memory_manager.on_round_complete(...)` 提交本轮。

一个关键约束是：`ChatAgent` 不会再次把 `persona.system_prompt` 以 `system=` 关键字传给 `LLMInterface`。系统提示已经在 `build_llm_context()` 中写入 `messages`，再次前置会导致重复注入。

## 错误路径

`ChatAgent` 只捕获 `LLMError` 体系内的调用层异常：

1. 构造错误哨兵文本：`[LLM call failed: <ExceptionType>: <message>]`
2. 将该文本作为最后一个 chunk `yield` 给调用方
3. 调用 `memory_manager.append_system_note(error_text)`
4. 直接返回，不调用 `on_round_complete()`

这条路径的设计语义是：

- 失败要让前端看见。
- 失败要进入 memory archive，便于审计和恢复。
- 失败不能算作一次有效轮次。

如果调用方选择 `commit_round=False`，就必须自行维护这套语义，否则容易把错误哨兵当作普通 AI 回复处理。

## Raw 与 Cleaned 语义

`ChatAgent` 自己不做文本清洗，它只处理原始输入和原始 LLM 输出。

### 用户输入

- `user_input` 原样传给 `MemoryManager.build_llm_context()`。
- `user_input` 原样传给 `MemoryManager.on_round_complete()`。
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

1. 调用 `agent.chat(..., commit_round=False)`
2. 先把用户消息和 AI 回复写入聊天存储
3. 再手动调用 `agent.memory_manager.on_round_complete(...)`

这样做的原因是聊天存储需要先落盘，再向客户端发送 `output:chat:complete`。对维护者来说，这意味着：

- `ChatAgent` 的默认成功路径和 WebSocket 的生产路径并不完全相同。
- 调整错误处理或 round commit 语义时，要同时检查 `ChatAgent` 和 `src/routes/chat_ws.py`。

## 相关文档

- [Agent 模块长期设计入口](README.zh-CN.md)
- [Persona 技术说明](persona.zh-CN.md)
- [Memory 模块长期设计入口](../memory/README.zh-CN.md)
