---
status: active
owner: memory
created: 2026-07-09
updated: 2026-07-09
source: docs/develop-blogs/2026-05-17-chat-memory-data-repair.md
related_code:
  - src/memory/chat_history.py
  - src/memory/manager.py
  - src/routes/data.py
  - frontend/src/pages/settings/data.vue
---

# 手工修改聊天历史后的记忆修复

本文是准备迁移到 GitHub Wiki 的排障稿，适用于“已经手工删改了聊天历史文件，现在要把短期记忆一起修正”的场景。

它不覆盖长期记忆清理，也不替代 [聊天历史清理与记忆删除](chat-history-cleanup.zh-CN.md) 中的常规删除说明。

## 什么时候需要看这篇

如果你已经手工改过 JSON，且出现以下现象，通常就需要同步修复短期记忆：

- 侧边栏聊天记录已经删掉或改短，但模型还会引用旧轮次。
- `short_term_memory.json` 的 `recent_messages` 明显和真实 session 尾部不一致。
- 重启服务后，L3/L4 压缩从错误轮次继续。
- 你想保留已有 summary，只修正轮次覆盖关系。

只改一处文件通常不够。前端聊天历史、归档 session 和短期记忆必须一起对齐。

## 先分清三类文件

前端聊天列表历史：

```text
data/chats/{user_id}/{character_id}/index.json
data/chats/{user_id}/{character_id}/sessions/{chat_id}.json
```

聊天级记忆归档：

```text
data/characters/{user_id}/{character_id}/chats/{chat_id}/sessions/{session_id}.json
```

聊天级短期记忆状态：

```text
data/characters/{user_id}/{character_id}/chats/{chat_id}/short_term_memory.json
```

补充说明：

- `data/chats` 只决定前端看到哪些标题和消息。
- `data/characters/.../chats/{chat_id}` 决定该聊天的短期记忆恢复与压缩。
- 历史迁移期间，角色级旧路径 `data/characters/{character_id}/` 可能仍存在，只作为兼容来源，不应再当作当前聊天级状态真相。

## 修复前原则

1. 优先停止后端后再手改文件。否则进程内缓存的 `MemoryManager` 可能仍持有旧状态。
2. 归档 session 是轮次真相来源，不以侧边栏消息条数直接推导。
3. 有效轮次定义仍是：

```text
一条 human 消息 + 下一条有效 ai 消息 = 1 轮
```

4. 以 `Error` 开头或空内容的 AI 回复，不应计入有效轮次。
5. 长期记忆不会因为你修了本地 JSON 而自动同步。

## 必须满足的不变量

修复后的 `short_term_memory.json` 至少要满足：

```text
total_rounds = 归档 session 的有效轮次数
max(covers_rounds.end) + recent_rounds = total_rounds
recent_rounds = recent_messages 条数 / 2
recent_messages 严格 human/ai 成对
recent_messages 来自归档 session 的尾部轮次
```

如果当前配置仍是：

```text
compress_rounds = 20
keep_recent_rounds = 20
```

那么还应额外检查：

```text
recent_messages 条数 < 80
```

这样可以避免服务一启动就立刻再次触发 L3 压缩。

## 推荐修复流程

### 1. 先备份

至少备份以下四个目标：

```text
data/chats/{user_id}/{character_id}/index.json
data/chats/{user_id}/{character_id}/sessions/{chat_id}.json
data/characters/{user_id}/{character_id}/chats/{chat_id}/sessions/{session_id}.json
data/characters/{user_id}/{character_id}/chats/{chat_id}/short_term_memory.json
```

不要直接在唯一副本上修。

### 2. 统计归档 session 的有效轮次

从 `data/characters/.../sessions/{session_id}.json` 重新统计有效 `(human, ai)` 对，记为 `N`。

后续至少要把：

- `short_term_memory.total_rounds`
- 压缩块覆盖终点
- `recent_messages`

全部对齐到这个 `N`。

### 3. 重新确定 recent_messages

如果不确定现有 `recent_messages` 是否可靠，最稳妥的做法是直接从 session 尾部重建。

推荐只保留：

```json
{"role": "human", "content": "..."}
{"role": "ai", "content": "..."}
```

不要把前端展示用的 `timestamp`、`avatar`、`name` 等字段塞回 `recent_messages`。

### 4. 重新计算 covers_rounds

假设你决定保留最后 `R` 轮作为 recent window，那么：

```text
max_block_end = N - R
```

所有 `meta_blocks[*].covers_rounds` 和 `active_blocks[*].covers_rounds` 的最大结束轮次，都必须与这个值一致。

如果 summary 本身没有问题，通常只需要调整：

- `covers_rounds`
- `total_rounds`
- `recent_messages`

而不必重写 summary 文本。

### 5. 同步前端聊天索引

如果你也改了：

```text
data/chats/{user_id}/{character_id}/sessions/{chat_id}.json
```

别忘了同步：

```text
data/chats/{user_id}/{character_id}/index.json
```

至少要保证：

```text
index.json 中该聊天的 message_count = session 文件里 messages 的实际条数
```

### 6. 让运行中缓存失效

如果后端在修复前已经运行过这条聊天：

- 最稳妥的方法是修完后重启后端。
- 若你只是想清空缓存并重建，可以先用数据维护接口清掉该聊天的短期记忆，再让系统按归档重建。

只改磁盘文件而不处理运行中缓存，常见结果是“文件对了，但下一轮上下文还是旧的”。

## 常见错误

### 只改 `total_rounds`

不够。下一次压缩的起点仍取决于 `covers_rounds`。

### 只改 `covers_rounds`

也不够。`recent_messages` 仍可能和真实 session 尾部不匹配。

### 用前端消息格式回填 `recent_messages`

不推荐。短期记忆只需要最小必要字段。

### 忘记同步 `index.json`

前端聊天标题列表仍可能显示旧 `message_count`，甚至出现“标题还在，但消息内容对不上”。

### 忘记运行中缓存

修完文件后不重启、不清缓存，进程内的 `MemoryManager` 仍可能继续使用旧状态。

### 忘记长期记忆

本文只处理本地 JSON 与短期记忆恢复问题。mem0、Qdrant 或其他长期记忆存储需要单独清理。

## 相关文档

- [聊天历史清理与记忆删除](chat-history-cleanup.zh-CN.md)
- [../../modules/storage/chat-history-storage.zh-CN.md](../../modules/storage/chat-history-storage.zh-CN.md)
- [../../modules/memory/chat-history-archive.zh-CN.md](../../modules/memory/chat-history-archive.zh-CN.md)
