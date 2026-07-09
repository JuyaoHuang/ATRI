---
status: active
owner: agent
created: 2026-07-09
updated: 2026-07-09
---

# Agent 模块长期设计

本目录保存 Agent 相关长期设计。这里的长期文档覆盖角色配置加载、聊天组合层、上下文注入和运行时生命周期。角色创建的用户教程仍是 [角色创建指南](../../../configs/CN/角色创建指南.md)。

## 当前文档

| 文档 | 内容 |
| --- | --- |
| [design.zh-CN.md](design.zh-CN.md) | Agent 模块总设计，串起 Persona、ChatAgent、ServiceContext、缓存键和与记忆/LLM 的协同关系。 |
| [chat-agent.zh-CN.md](chat-agent.zh-CN.md) | `ChatAgent` 的成功路径、错误路径、`runtime_context` 注入、raw/cleaned 语义和 `ServiceContext` 缓存边界。 |
| [persona.zh-CN.md](persona.zh-CN.md) | Persona 文件格式、加载流程、API 输出和头像托管边界。 |
| [persona.en-US.md](persona.en-US.md) | English version of Persona file format, loading flow, API output, and avatar hosting boundaries. |

## 模块边界

Agent 模块主要由两层组成：

1. `Persona`：把 `prompts/persona/{character_id}.md` 解析为角色级静态配置。
2. `ChatAgent`：组合 `Persona`、`LLMInterface` 和 `MemoryManager`，提供面向对话的流式入口。

生命周期不由 `ChatAgent` 自己管理，而是交给 `src/service_context.py`：

- `ChatAgent` 缓存键：`(character_id, user_id, chat_id)`
- 长期记忆缓存键：`(character_id, user_id)`

这意味着同一用户与同一角色的不同聊天会共享长期记忆，但不会共享短期记忆。

## 阅读路径

建议按下面顺序阅读：

1. [design.zh-CN.md](design.zh-CN.md)
2. [persona.zh-CN.md](persona.zh-CN.md)
3. [chat-agent.zh-CN.md](chat-agent.zh-CN.md)
4. `src/agent/persona.py`
5. `src/agent/chat_agent.py`
6. `src/service_context.py`
7. `src/routes/chat_ws.py`

## 相关实现入口

- `src/agent/persona.py`
- `src/agent/chat_agent.py`
- `src/service_context.py`
- `src/routes/chat_ws.py`
- `frontend/src/composables/useChat.ts`
