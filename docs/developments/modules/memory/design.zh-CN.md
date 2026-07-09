---
status: active
owner: memory
created: 2026-07-09
updated: 2026-07-09
source:
  - ../../module-design/CN/记忆系统设计讨论.md
  - src/memory/manager.py
  - src/memory/short_term.py
  - src/memory/chat_history.py
  - src/memory/long_term.py
  - src/memory/retrieval_policy.py
  - src/memory/search_cache.py
  - src/memory/compressor.py
related_code:
  - src/memory/manager.py
  - src/memory/short_term.py
  - src/memory/chat_history.py
  - src/memory/long_term.py
  - src/memory/retrieval_policy.py
  - src/memory/search_cache.py
  - src/memory/compressor.py
---

# 记忆系统总设计

本文把 `memory` 模块的整体设计逻辑接起来。现有子文档已经分别讲了短期、长期和 archive，但还缺一页说明：

1. 为什么这三者要这样协同。
2. 一轮对话在记忆系统里如何流动。
3. 哪些旧设计已经落地，哪些仍然只是历史讨论。

## 设计目标

结合旧设计文档和当前实现，记忆系统的长期目标已经收敛为 5 条：

1. 记忆作用域必须对齐 `(user_id, character_id, chat_id)`。
2. 短期记忆负责当前上下文压缩，不负责用户可见聊天列表。
3. 长期记忆通过 mem0 提供事实检索，但不能让 mem0 故障阻塞主聊天。
4. archive 必须足够稳健，能在短期状态损坏时重建上下文。
5. 记忆系统自己负责“如何组装给 LLM 的上下文”，而不是把这件事分散给调用方。

## 模块组成

当前 `src/memory/` 可以稳定拆成 6 个组件：

| 组件 | 代码 | 职责 |
| --- | --- | --- |
| 编排器 | `manager.py` | 维护一条聊天会话的短期状态、触发 L3/L4、调用长期检索、组装 LLM 上下文。 |
| 短期存储 | `short_term.py` | 读写 `short_term_memory.json`。 |
| 会话归档 | `chat_history.py` | 维护 append-only `sessions/{session_id}.json`。 |
| 长期记忆 | `long_term.py` | 统一封装 mem0 `sdk` / `local_deploy` 两种模式。 |
| 检索策略 | `retrieval_policy.py` | 决定当前轮次是否真的要调 `mem0.search()`。 |
| 搜索缓存 | `search_cache.py` | 对同一 user/agent/query 做 TTL + LRU 缓存。 |

## 作用域与路径

当前设计的核心变化，是把旧的“角色级目录”改成了聊天级作用域：

```text
data/characters/{user_id}/{character_id}/chats/{chat_id}/
```

这个目录下面至少有两类文件：

```text
short_term_memory.json
sessions/{session_id}.json
```

长期约束：

- `short_term_memory.json` 是当前聊天级短期状态；
- `sessions/*.json` 是 append-only archive；
- 旧的角色级路径仍可被迁移读取，但不是新的真相路径。

## 一轮对话的数据流

当前一轮完整对话在记忆系统里的顺序是：

```text
user input
  -> L1 snip
  -> append human/ai to archive
  -> if valid round:
       update recent_messages
       total_rounds += 1
       maybe trigger L3
       maybe trigger L4
  -> save short_term_memory.json
```

这里有两个长期边界：

1. archive 会记录更多东西，包括错误轮次和系统注记；
2. `total_rounds` 只统计有效轮次，不是“文件里写了几条消息”。

## 轮次定义

当前有效轮次由 `manager._is_valid_round()` 决定。只有满足以下条件的 AI 回复才计入 `total_rounds`：

- `role == 'ai'`
- `content` 非空
- 不是 `Error...` 开头
- `interrupted` 不是 `True`

这意味着：

- 聊天失败后的系统错误消息会被 archive 保留，但不进入短期轮次；
- VAD interrupt 产生的半截 AI 回复可以审计、可以展示，但不进入正常记忆压缩；
- `recent_messages` 永远只反映“有效轮次”的 user/ai 对。

## 短期记忆结构

短期状态由这些核心字段组成：

| 字段 | 含义 |
| --- | --- |
| `session_id` | 当前活动 session 标识 |
| `character` | 角色 ID |
| `updated_at` | 最近写入时间 |
| `total_rounds` | 有效轮次计数 |
| `meta_blocks` | L4 产物 |
| `active_blocks` | L3 产物 |
| `recent_messages` | 尚未被压缩的最近原始轮次 |

长期语义是：

- `meta_blocks` 表示更高层模式摘要；
- `active_blocks` 表示事件级摘要；
- `recent_messages` 表示当前尾部原始上下文。

## 压缩策略

### L1

L1 只作用于用户输入，负责裁剪和清洗，不直接调用 LLM。

### L3

当 `recent_messages` 中积累到足够原始轮次，且还能保留 `keep_recent_rounds` 时，触发 L3：

- 压缩窗口大小来自 `compress_rounds`
- 结果写入 `active_blocks`
- 被压缩窗口从 `recent_messages` 删除
- 若启用长期记忆，同一窗口 best-effort 写入 mem0

### L4

当 `active_blocks` 数量达到 `trigger_blocks` 时，触发 L4：

- 读取若干个 L3 block
- 产出一个 `meta_block`
- 新的 `meta_block` 存到 `meta_blocks`
- 被吸收的 `active_blocks` 从 active 列表移除

长期约束：

- 当前实现不采用旧文档里的 L2 Micro；
- L3/L4 都通过压缩专用 LLM role 调用；
- 压缩失败不能破坏 archive 和短期状态基本持久化。

## 长期记忆设计

长期记忆由 `LongTermMemory` 封装，支持两种模式：

| 模式 | 后端 |
| --- | --- |
| `sdk` | `mem0.MemoryClient` |
| `local_deploy` | `mem0.Memory.from_config(...)` |

关键设计点：

- `MemoryManager` 不关心后端模式；
- mem0 写入走 best-effort，不让失败阻塞当前轮次；
- 检索前先经过 `LongTermRetrievalPolicy`；
- 命中结果可进入 `SearchCache`；
- 删除是提交到 mem0 scope，不等于删本地 archive。

## 检索策略与缓存

当前长期检索并不是每轮必查。`LongTermRetrievalPolicy` 支持：

- `always`
- `interval`
- `triggered`
- `hybrid`

这让系统可以节省 mem0 quota，同时保留关键词触发能力。

搜索缓存是同一进程内的 TTL + LRU：

- key 由 `user_id + agent_id + normalized query + limit + threshold` 组成；
- `add()` 或 `delete_all()` 后会失效对应 scope；
- 缓存只是性能层，不改变事实来源。

## 会话恢复设计

当前恢复优先级是：

1. 尝试加载 `short_term_memory.json`
2. 对照 archive 统计有效 `(human, ai)` 对
3. 如状态落后，增量回放缺失轮次
4. 如状态损坏，直接从 archive 全量重建

这也是为什么 archive 被设计成更稳健的 source of truth：

- 写入是原子替换；
- 读取支持尾部损坏容错；
- 即使短期状态损坏，也尽量能从 archive 恢复。

## 构建给 LLM 的上下文

`MemoryManager.build_llm_context()` 当前明确承担上下文组装责任，顺序是：

1. `system_prompt`
2. 长期记忆检索结果
3. `meta_blocks`
4. `active_blocks`
5. `recent_messages`
6. 当前 `user_input`

长期意义：

- 记忆模块不只存数据，还负责定义“LLM 看到的历史顺序”；
- 调用方不必重复拼接 L3/L4 和长期命中；
- runtime datetime context 也在这里以隐藏上下文方式拼进最终 user turn。

## 与聊天、VAD、前端的边界

### 与聊天存储

聊天列表和消息详情的用户可见真相仍在 `data/chats/...`，不在 memory archive。

### 与 VAD interrupt

被 interrupt 的 AI partial reply：

- 可以进入 archive；
- 可以给前端显示；
- 不计入有效轮次；
- 不触发短期压缩；
- 不写入长期记忆。

### 与前端

前端不会直接读 `data/characters/...`。记忆修复和清理都必须通过后端接口或离线文件操作完成。

## 从近期 git log 确认的长期事实

近期和 `src/memory` 紧密相关的演化，更多体现在 VAD/ASR 打断治理日志里：

- `add chat generation state`
- `cancel chat task on speech start`
- `auto submit ASR transcript chat`
- `persist VAD generation identity`

这些提交共同确认了一点：记忆系统现在必须和 generation / interrupt 语义配合，不能再把所有 AI 输出一概当作有效轮次。

## 与旧设计文档的取舍

旧 `记忆系统设计讨论.md` 中这些内容已经变成当前实现事实，并被本目录吸收：

- L1/L3/L4 分层压缩
- mem0 双模式
- archive 作为恢复权威来源
- 上下文组装顺序

这些内容仍未被当作当前事实迁入：

- L2 Micro 层
- Graph Memory
- 某些向量库/部署选型讨论
- 作为草案存在但未落地的 prompt 或策略分支

也就是说，旧文档现在更像“设计讨论和备选方案库”，而不是当前实现说明。

## 相关文档

- [README.zh-CN.md](README.zh-CN.md)
- [short-term-memory.zh-CN.md](short-term-memory.zh-CN.md)
- [long-term-memory.zh-CN.md](long-term-memory.zh-CN.md)
- [chat-history-archive.zh-CN.md](chat-history-archive.zh-CN.md)
