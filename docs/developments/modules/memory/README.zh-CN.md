---
status: active
owner: memory
created: 2026-07-09
updated: 2026-07-09
---

# Memory 模块长期设计

本目录保存记忆系统的长期设计。这里的文档覆盖短期记忆状态、mem0 长期记忆、会话归档和恢复边界。历史完整设计仍可参考 `docs/developments/module-design/CN/记忆系统设计讨论.md`，但实现判断应以当前源码和本目录文档为准。

## 当前文档

| 文档 | 内容 |
| --- | --- |
| [design.zh-CN.md](design.zh-CN.md) | 记忆系统总设计，串起短期、长期、archive、检索策略、恢复流程和与 VAD/chat 的边界。 |
| [short-term-memory.zh-CN.md](short-term-memory.zh-CN.md) | `MemoryManager`、`ShortTermStore`、L1/L3/L4 触发、上下文组装和恢复流程。 |
| [context-assembly.zh-CN.md](context-assembly.zh-CN.md) | LLM payload 组装顺序、长期检索注入、runtime datetime context 和角色映射边界。 |
| [long-term-memory.zh-CN.md](long-term-memory.zh-CN.md) | `LongTermMemory` 的 mem0 双模式封装、检索策略、缓存和删除语义。 |
| [recovery.zh-CN.md](recovery.zh-CN.md) | `resume_session()`、全量重建、增量追补、archive 容错解析和一致性策略。 |
| [chat-history-archive.zh-CN.md](chat-history-archive.zh-CN.md) | Memory archive 的当前路径、文件格式、恢复语义，以及它与聊天存储的区别。 |
| [chat-history-archive.en-US.md](chat-history-archive.en-US.md) | English version of MemoryManager character memory archive notes. |

## 模块边界

Memory 模块负责：

- 为单个 `(user_id, character_id, chat_id)` 维护短期记忆状态。
- 在合适时机向 mem0 写入或检索长期事实。
- 为会话恢复保留 memory archive。
- 为 LLM 调用组装上下文 payload。

它不负责：

- 前端聊天列表和聊天详情的用户可见存储。
- Persona 解析与角色管理。
- 直接调用主聊天 LLM。

## 阅读路径

建议按下面顺序阅读：

1. [design.zh-CN.md](design.zh-CN.md)
2. [short-term-memory.zh-CN.md](short-term-memory.zh-CN.md)
3. [context-assembly.zh-CN.md](context-assembly.zh-CN.md)
4. [long-term-memory.zh-CN.md](long-term-memory.zh-CN.md)
5. [recovery.zh-CN.md](recovery.zh-CN.md)
6. [chat-history-archive.zh-CN.md](chat-history-archive.zh-CN.md)
7. `src/memory/manager.py`
8. `config/memory_config.yaml`

## 相关实现入口

- `src/memory/manager.py`
- `src/memory/short_term.py`
- `src/memory/chat_history.py`
- `src/memory/compressor.py`
- `src/memory/long_term.py`
- `src/memory/retrieval_policy.py`
- `src/memory/search_cache.py`
- `src/service_context.py`
