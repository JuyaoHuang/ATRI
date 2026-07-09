---
status: active
owner: memory
created: 2026-07-09
updated: 2026-07-09
related_code:
  - src/memory/manager.py
  - src/memory/short_term.py
  - src/memory/chat_history.py
  - src/memory/compressor.py
  - config/memory_config.yaml
  - src/service_context.py
---

# 短期记忆设计

本文描述当前代码中的短期记忆实现，也就是 `MemoryManager` 与 `ShortTermStore` 共同维护的会话级上下文状态。

## 作用域

短期记忆绑定到单个 `(user_id, character_id, chat_id)`：

- `ServiceContext` 为每个聊天创建一个独立的 `MemoryManager`
- `MemoryManager` 维护一个活动 `session_id`
- `ShortTermStore` 持久化当前聊天的 `short_term_memory.json`
- `ChatHistoryWriter` 追加本聊天的 memory archive

因此，短期记忆不会在两个聊天标题之间共享。

## 当前路径

当 `MemoryManager` 带有 `chat_id` 初始化时，当前有效目录是：

```text
{storage.characters_dir}/{user_id}/{character_id}/chats/{chat_id}/
  short_term_memory.json
  sessions/{session_id}.json
```

默认配置来自 `config/memory_config.yaml`：

```yaml
storage:
  characters_dir: ./data/characters
```

仓库仍保留两层旧路径迁移逻辑，但它们只是兼容输入，不再是当前设计目标：

1. 旧的角色级用户路径：`{characters_dir}/{user_id}/{character_id}/`
2. 更早的无用户路径：`{characters_dir}/{character_id}/`

首次访问时，`resolve_user_character_dir()` 和 `resolve_user_character_chat_dir()` 会把旧文件复制到新的聊天级路径，并写入迁移标记文件。

## 状态结构

`short_term_memory.json` 由 `ShortTermStore` 读写，当前结构如下：

```json
{
  "session_id": "2026-07-09_ab12cd34",
  "character": "atri",
  "updated_at": "2026-07-09T12:34:56Z",
  "total_rounds": 0,
  "meta_blocks": [],
  "active_blocks": [],
  "recent_messages": []
}
```

字段语义：

| 字段 | 含义 |
| --- | --- |
| `session_id` | 当前活动会话标识。 |
| `character` | 角色标识。 |
| `updated_at` | 最近一次持久化时间。 |
| `total_rounds` | 有效轮次数，只统计通过 `_is_valid_round()` 的 AI 回复。 |
| `meta_blocks` | L4 产物，按“最新在前”存储。 |
| `active_blocks` | L3 产物，等待被 L4 继续整合。 |
| `recent_messages` | 仍保留为原始轮次的短尾上下文。 |

## 每轮处理流程

`MemoryManager.on_round_complete(user_msg, ai_msg)` 的顺序是固定的：

1. 对用户消息执行 L1 Snip。
2. 将 human/ai 两条消息追加到 memory archive。
3. 若 AI 回复是有效轮次，则把清洗后的 human 和原样 ai 写入 `recent_messages`，并增加 `total_rounds`。
4. 评估是否触发 L3；若 L3 后 `active_blocks` 数量达到阈值，再级联触发 L4。
5. 持久化 `short_term_memory.json`。

`_is_valid_round()` 当前排除以下 AI 消息：

- `role` 不是 `ai`
- `content` 为空
- `content` 以 `Error` 开头
- `interrupted == true`

`append_system_note()` 是单独路径：它只往 archive 写一条 `role=system` 记录，不改 `total_rounds`、`recent_messages` 或压缩状态。

## L1、L3、L4 触发规则

当前实现已经从“固定轮次常量”变成“配置驱动”：

```yaml
short_term:
  collapse:
    trigger_rounds: 20      # 兼容字段，当前触发逻辑不读取
    compress_rounds: 20
    keep_recent_rounds: 20
  super_compact:
    trigger_blocks: 4
```

需要特别注意两点：

1. `trigger_rounds` 仍会被读入 `MemoryManager.trigger_rounds`，但当前 `_maybe_trigger_l3()` 不使用它。
2. L3 的真实条件是：

```text
len(recent_messages) >= (compress_rounds + keep_recent_rounds) * 2
```

也就是说，L3 会在“既能压缩一段旧尾巴，又能保留足够近期轮次”时触发，而不是写死为某个轮次数字。

L3 与 L4 的具体行为：

| 层级 | 触发条件 | 输入 | 输出 |
| --- | --- | --- | --- |
| L3 | `recent_messages` 足够覆盖 `compress_rounds + keep_recent_rounds` | 最旧的 `compress_rounds * 2` 条消息 | 一个 `active_block`，并从 `recent_messages` 删除这段窗口 |
| L4 | `len(active_blocks) >= trigger_blocks` | 最前面的 `trigger_blocks` 个 `active_block` | 一个 `meta_block`，剩余 `active_blocks` 向前收缩 |

## 上下文组装顺序

`MemoryManager.build_llm_context()` 负责为下一次对话组装 LLM payload，顺序如下：

1. `system_prompt`
2. 长期记忆搜索结果，包装成一条 `role=system`
3. `meta_blocks`，按“最旧优先”渲染
4. `active_blocks`
5. `recent_messages`
6. 本轮 `user_input`

角色映射规则：

- `human` -> `user`
- `ai` -> `assistant`
- `system` -> `system`

如果存在 `runtime_context`，当前只会把其中的 `datetime` 模块序列化为一个隐藏的 `<context>` 片段，并追加到最终用户消息尾部。它不会写回 `recent_messages`。

## 生命周期

### 初始化

`MemoryManager` 构造时会立即自举一个隐式会话，使测试或简单调用可以直接执行 `on_round_complete()`。

### `start_session()`

- 生成新的 `session_id`
- 重新绑定 `ShortTermStore` 和 `ChatHistoryWriter`
- 写入 archive metadata
- 重置 dirty 标志

### `close_session()`

- 如果本生命周期内还有未被 L3 带走的 `recent_messages`，并且启用了长期记忆，则把这段尾巴推送到 `LongTermMemory.add()`
- 最后一次保存 `short_term_memory.json`
- 清空活动会话状态

### `reset_short_term()`

- 删除当前 `short_term_memory.json` 与临时文件
- 保留活动 `session_id`
- 用空骨架重置内存状态

这条路径被 `DELETE /api/data/characters/{character_id}/chats/{chat_id}/short-term-memory` 用来做运行时热清理。

### `resume_session(session_id)`

恢复逻辑以 memory archive 为准：

1. 尝试加载 `short_term_memory.json`
2. 若 JSON 损坏，则从 archive 完全重建
3. 若 `total_rounds` 落后于 archive 中的有效轮次，则增量补齐尾部
4. 补齐过程中仍复用正常的 L1/L3/L4 流程

因此，恢复并不是一条独立算法，而是“按已有归档回放正常流程”。

## 相关文档

- [长期记忆设计](long-term-memory.zh-CN.md)
- [Memory Archive 设计](chat-history-archive.zh-CN.md)
