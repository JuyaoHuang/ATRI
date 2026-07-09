---
status: active
owner: memory
created: 2026-07-09
updated: 2026-07-09
source: docs/configs/CN/对话历史存储与批量删除说明.md
related_code:
  - src/memory/chat_history.py
  - src/memory/manager.py
  - src/routes/data.py
  - config/memory_config.yaml
---

# Memory Archive 设计

本文沉淀 `MemoryManager` 使用的会话归档结构。运维删除步骤见 [对话历史存储与批量删除说明](../../../configs/CN/对话历史存储与批量删除说明.md)。

## 与聊天存储的区别

项目中有两类“历史”：

| 类型 | 主要用途 | 默认路径 |
| --- | --- | --- |
| 聊天存储 | 前端侧边栏聊天列表、聊天详情 API、WebSocket 持久化 | `data/chats/{user_id}/{character_id}/` |
| Memory archive | 短期记忆恢复、L3/L4 回放、系统级审计 | `data/characters/{user_id}/{character_id}/chats/{chat_id}/` |

前端不会直接读取 memory archive 文件。用户可见历史由 `src/routes/chats.py` 和 `src/storage/json_storage.py` 提供的 API 输出负责。

## 当前路径与兼容迁移

当前有效路径：

```text
data/characters/{user_id}/{character_id}/chats/{chat_id}/sessions/{session_id}.json
```

路径来源：

```yaml
storage:
  characters_dir: ./data/characters
```

当前代码仍兼容两种旧路径，但它们只作为迁移来源存在：

```text
data/characters/{user_id}/{character_id}/sessions/{session_id}.json
data/characters/{character_id}/sessions/{session_id}.json
```

`resolve_user_character_dir()` 与 `resolve_user_character_chat_dir()` 会在首次访问时把旧文件复制到聊天级目录，并写入迁移标记。

## 文件格式

单个 archive 文件是一个 JSON 数组，由 `ChatHistoryWriter` 维护：

```json
[
  {
    "role": "metadata",
    "timestamp": "2026-07-09T12:34:56Z",
    "session_id": "2026-07-09_ab12cd34",
    "character": "atri"
  },
  {
    "role": "human",
    "timestamp": "2026-07-09T12:35:01Z",
    "content": "清洗后的用户输入",
    "name": "user"
  },
  {
    "role": "ai",
    "timestamp": "2026-07-09T12:35:03Z",
    "content": "AI 回复",
    "name": "亚托莉"
  }
]
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `metadata` 行 | 只出现一次，记录 `session_id` 与 `character`。 |
| `human.content` | 当前由 `MemoryManager` 写入的清洗后文本。 |
| `human.raw_input` | 仅当调用方显式传入时才会存在，用于保留额外原始输入。 |
| `ai.generation_id` | WebSocket 路径里用于标记一轮生成。 |
| `ai.interrupted` / `interrupt_reason` | 表示该 AI 回复是被打断的 partial reply。 |
| `system.content` | 例如 LLM 调用失败等系统级备注。 |

archive 文件是追加式的，但底层写入实现仍采用“读数组 -> 追加 -> 原子替换”的方式，因此文件本身保持为完整 JSON 数组。

## 恢复语义

对于 `MemoryManager` 来说，archive 是恢复时的 source of truth。

`resume_session(session_id)` 的恢复顺序是：

1. 尝试加载 `short_term_memory.json`
2. 统计 archive 中的有效 `(human, ai)` 配对
3. 若短期状态落后，则增量补齐缺失轮次
4. 若短期状态损坏，则从 archive 全量回放重建

`ChatHistoryWriter.iter_messages()` 还带有“容错解析尾部”的能力：

- 如果 JSON 尾部有损坏记录，会先记录 WARNING
- 然后尽力恢复可解析前缀
- 恢复逻辑据此继续工作

这意味着 archive 比短期状态更适合作为恢复依据。

## 与短期清理接口的关系

`DELETE /api/data/characters/{character_id}/chats/{chat_id}/short-term-memory` 当前只会：

- 删除 `short_term_memory.json`
- 删除同名临时文件
- 重置进程内缓存的短期状态

它不会删除 archive 文件。因此清掉短期状态后，后续仍可通过 archive 重新构建上下文。

## 长期记忆边界

如果启用 mem0：

- 本地模式可能写入 `data/qdrant`。
- SaaS 模式会写入外部 mem0 服务。

archive 不等于长期记忆本体。删除 `data/characters/.../sessions/` 不会自动删除 mem0 中的事实；反过来，清理长期记忆也不会自动删 archive。

## 维护原则

- 删除文件前建议停止后端服务。
- 运行时删除可能和 `.tmp` 原子替换流程冲突。
- 删除 `sessions/` 只影响 memory archive，不等同于删除聊天存储或长期记忆。
- 删除 `short_term_memory.json` 会迫使后续重新构建或重新初始化短期记忆。

## 相关文档

- [对话历史存储与批量删除说明](../../../configs/CN/对话历史存储与批量删除说明.md)
- [聊天历史存储结构](../storage/chat-history-storage.zh-CN.md)
- [短期记忆设计](short-term-memory.zh-CN.md)
