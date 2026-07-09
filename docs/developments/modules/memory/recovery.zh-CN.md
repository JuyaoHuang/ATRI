---
status: active
owner: memory
created: 2026-07-09
updated: 2026-07-09
source:
  - ../../module-design/CN/记忆系统设计讨论.md
  - src/memory/manager.py
  - src/memory/chat_history.py
  - src/memory/short_term.py
related_code:
  - src/memory/manager.py
  - src/memory/chat_history.py
  - src/memory/short_term.py
---

# 记忆恢复与一致性设计

本文专门说明短期记忆恢复和一致性校验策略。重点不是“文件放哪”，而是：

1. 为什么 `chat_history` 是恢复权威来源。
2. `resume_session()` 遇到不一致时怎么修。
3. 哪些损坏场景当前能恢复，哪些只会降级处理。

## 核心原则

当前恢复设计只有一条总原则：

`chat_history` 比 `short_term_memory.json` 更可信。

原因：

- `chat_history` 是 append-only；
- 写入语义更简单；
- 读取支持尾部损坏容错；
- `short_term_memory.json` 是“当前压缩状态快照”，天然更容易在原地更新时失真。

## 恢复入口

当前恢复主入口是：

```python
await MemoryManager.resume_session(session_id)
```

它会先重绑定：

- `ShortTermStore`
- `ChatHistoryWriter`

然后再判断现有短期状态是否可信。

## 恢复判定顺序

当前判定顺序是：

1. 尝试加载 `short_term_memory.json`
2. 若 JSON 解析失败或 payload 结构异常，走完全重建
3. 若加载成功，则统计 archive 中有效 `(human, ai)` 对数量
4. 比较 `chat_rounds` 与 `stored_rounds`

结果分成三种：

| 场景 | 当前行为 |
| --- | --- |
| `chat_rounds == stored_rounds` | 原样恢复 |
| `chat_rounds > stored_rounds` | 增量追补缺失轮次 |
| `chat_rounds < stored_rounds` | 记录 WARNING，保留存储状态 |

## 增量追补

当 archive 比短期状态更新时，当前实现不会直接全量重建，而是：

1. 找出缺失尾部轮次
2. 对这些轮次重新执行：
   - L1 snip
   - recent_messages 追加
   - `total_rounds += 1`
   - `_maybe_trigger_l3()`
3. 最后重新保存 `short_term_memory.json`

长期意义：

- 若只是进程在保存后半段前崩溃，不必重放整个历史；
- 恢复逻辑尽量复用正常对话路径，而不是写第二套“恢复专用压缩器”。

## 完全重建

当 `short_term_memory.json` 本身损坏时，当前会：

1. 以空 skeleton 启动
2. 从 `chat_history` 里收集所有有效 `(human, ai)` 对
3. 对每一对重新执行正常路径：
   - L1
   - recent_messages 追加
   - `total_rounds += 1`
   - `_maybe_trigger_l3()`
   - `_trigger_l4()` 级联
4. 保存重建后的短期状态

长期约束：

- 恢复路径不跳过压缩器；
- L3 期间若启用了 `LongTermMemory`，会再次触发 best-effort `add()`；
- mem0 的 ADD-only 语义让这种重放在数据层面可接受。

## `chat_history` 的容错解析

`ChatHistoryWriter.iter_messages()` 当前不是“读不出来就直接炸”，而是：

1. 先尝试正常 `json.load`
2. 若尾部损坏：
   - 记录 WARNING
   - 用 `raw_decode` 做对象级 tolerant parse
   - 返回可解析前缀

这条设计直接决定了恢复能力：

- 文件尾部半写不至于让整个恢复失败；
- 最多损失最后一条不完整记录；
- 前面完整的历史仍可用于重建。

## 有效轮次抽取

恢复时并不是简单“按 human/ai 交替配对”，而是：

- 跳过 `metadata`
- 跳过 `system`
- 丢弃未配对的 `human`
- 丢弃无效 AI 回复

这让恢复逻辑和正常轮次定义保持一致：

- `Error...` AI 回复不计轮；
- `interrupted=true` 的 AI partial reply 不计轮；
- 但这些记录仍然可能存在于 archive 中供审计和前端展示。

## 与长期记忆的关系

恢复时，长期记忆不是权威来源，只是可能被再次补写的旁路：

- archive -> short-term state 是主恢复链
- `LongTermMemory.add()` 是恢复过程中 L3 触发时的副作用

长期意义：

- 即使 mem0 不可用，短期状态仍可从 archive 恢复；
- 长期记忆缺失不会阻断会话恢复；
- mem0 失败最多影响长期事实完整性，不影响聊天上下文最小可用性。

## 典型故障场景

### 1. `short_term_memory.json` 损坏

当前行为：

- 直接完全重建

### 2. `chat_history` 尾部半写

当前行为：

- 尝试容错解析可用前缀
- 用可用前缀恢复

### 3. `short_term_memory` 落后于 archive

当前行为：

- 增量追补缺失尾部

### 4. `stored_rounds` 反而大于 archive

当前行为：

- 打 WARNING
- 暂时保留存储状态

这里说明当前系统更偏向“保守不覆盖”，而不是在不确定情况下强行重建。

## 与旧设计稿的对齐和差异

与旧设计稿对齐的部分：

- `chat_history` 是 source of truth
- 恢复路径优先复用正常逻辑
- mem0 重复 ADD 可接受

当前实现比旧稿更明确的地方：

- 具体的三分支判定
- `iter_messages()` 的尾部损坏容错
- 增量追补优先于完全重建

## 当前明确不做的事

当前恢复设计**不**做这些事：

- WAL
- 写入事务日志
- 独立恢复快照版本链
- 基于 mem0 反推短期状态

这和旧设计稿里的取舍一致：单用户/轻量场景下，恢复成本比预防性复杂度更低。

## 相关文档

- [design.zh-CN.md](design.zh-CN.md)
- [short-term-memory.zh-CN.md](short-term-memory.zh-CN.md)
- [chat-history-archive.zh-CN.md](chat-history-archive.zh-CN.md)
