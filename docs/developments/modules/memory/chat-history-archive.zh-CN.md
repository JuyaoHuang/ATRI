---
status: active
owner: memory
created: 2026-07-09
updated: 2026-07-09
source: docs/configs/CN/对话历史存储与批量删除说明.md
related_code:
  - src/memory/chat_history.py
  - src/memory/
  - config/memory_config.yaml
---

# MemoryManager 角色记忆归档

本文沉淀 MemoryManager 的角色记忆归档结构。运维删除步骤见 [对话历史存储与批量删除说明](../../../configs/CN/对话历史存储与批量删除说明.md)。

## 与聊天列表历史的区别

项目中有两类“历史”：

| 类型 | 主要用途 | 默认路径 |
| --- | --- | --- |
| 前端聊天列表历史 | 侧边栏聊天列表和消息详情 | `data/chats/default/{character_id}/` |
| MemoryManager 角色记忆归档 | 短期记忆恢复、压缩、长期记忆写入 | `data/characters/{character_id}/` |

删除前端聊天列表历史不会自动清理 MemoryManager 文件。

## 默认路径

默认配置：

```yaml
storage:
  characters_dir: ./data/characters
```

通常路径：

```text
data/characters/{character_id}/short_term_memory.json
data/characters/{character_id}/sessions/{session_id}.json
```

## 文件职责

| 文件 | 职责 |
| --- | --- |
| `sessions/{session_id}.json` | `src/memory/chat_history.py` 写入的追加式会话归档。 |
| `short_term_memory.json` | 当前角色短期记忆状态，包括压缩块和最近轮次。 |

`short_term_memory.json` 可以通过聊天归档恢复，但恢复策略必须遵守记忆系统设计中的轮次覆盖和压缩块边界。

## 长期记忆边界

如果启用 mem0：

- 本地模式可能写入 `data/qdrant`。
- SaaS 模式会写入外部 mem0 服务。

当前仓库没有统一的长期记忆批量删除接口。涉及长期记忆清理时，不能只删除 `data/characters`。

## 维护原则

- 删除文件前建议停止后端服务。
- 运行时删除可能和 `.tmp` 原子替换流程冲突。
- 删除 `sessions/` 只影响归档，不等同于删除短期记忆。
- 删除 `short_term_memory.json` 会迫使后续重新构建或重新初始化短期记忆。

## 相关文档

- [对话历史存储与批量删除说明](../../../configs/CN/对话历史存储与批量删除说明.md)
- [聊天历史存储结构](../storage/chat-history-storage.zh-CN.md)
- `docs/developments/module-design/CN/记忆系统设计讨论.md`
