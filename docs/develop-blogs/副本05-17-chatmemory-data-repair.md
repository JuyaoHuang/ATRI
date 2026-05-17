# 聊天历史与短期记忆轮次修复记录

## 背景

本次修复处理角色 `JuyaoHuang/11` 的一次手工数据清理。

用户已经在 `11/data` 目录中准备了新的聊天历史与记忆数据，希望用这些文件替换 `atri/data` 中的原始数据。同时，手工清理后 `short_term_memory.json` 中的轮次信息不再匹配归档会话，导致上下文压缩状态存在风险。

本次处理目标是：

- 以 `11/data` 中的新 JSON 数据作为目标数据。
- 保留已经人工调整满意的压缩摘要 `summary`。
- 不重新调用 LLM，不重新生成 L3/L4 摘要。
- 修正 `covers_rounds`、`total_rounds` 和 `recent_messages` 的轮次关系。
- 将修正后的数据覆盖到 `atri/data` 的实际工作目录。

## 相关数据文件

前端聊天历史：

```text
data/chats/JuyaoHuang/11/index.json
data/chats/JuyaoHuang/11/sessions/20260513_f2bb7b12.json
```

记忆系统归档与短期记忆：

```text
data/characters/JuyaoHuang/11/chats/20260513_f2bb7b12/sessions/2026-05-13_656ffee8.json
data/characters/JuyaoHuang/11/chats/20260513_f2bb7b12/short_term_memory.json
```

## 问题

手工清理后，目标归档 session 的有效轮次已经变为 `277` 轮，但 `short_term_memory.json` 仍记录旧状态：

```text
total_rounds = 445
recent_messages = 50 条，即 25 轮
```

旧的压缩块仍覆盖到第 `420` 轮，与新的 session 轮次不匹配。

这会造成两个问题：

- `total_rounds` 与归档 session 的实际有效轮次不一致。
- 下一次压缩起点会根据旧的 `covers_rounds` 推导，可能跳过或重复处理错误区间。

## 代码规则

当前压缩逻辑的关键规则来自 `MemoryManager`：

- 有效轮次来自归档 session 中的 `(human, ai)` 对。
- `recent_messages` 保存未压缩的原始轮次。
- L3 触发条件是 `recent_messages` 达到 `compress_rounds + keep_recent_rounds`。
- 当前配置为 `compress_rounds = 20`、`keep_recent_rounds = 20`。
- 因此 L3 触发阈值是 `40` 轮，即 `80` 条 `recent_messages`。
- `_next_uncompressed_round()` 使用所有 block 的最大 `covers_rounds[1]` 推导下一次 L3 起点。
- `build_llm_context()` 发送给 LLM 的内容是 block 的 `summary` 和 `recent_messages`，不会把 `covers_rounds` 当作用户消息发送。

因此，修复重点不是重写摘要，而是让这些关系成立：

```text
max(covers_rounds.end) + recent_rounds = total_rounds
recent_messages_count < 80
recent_messages 与 session 尾部轮次一致
```

## 修复方案

本次采用的轮次分配：

```text
total_rounds = 277
recent_messages = 第 253-277 轮，共 25 轮 / 50 条消息
```

所有既有 block 保留，不删除，不修改 `summary`。

`covers_rounds` 调整为：

```text
meta_c44a2ea9   [1, 80]
meta_6743a00d   [81, 160]
meta_5fa01aec   [161, 184]
meta_23bfff2a   [185, 208]
meta_5a80c280   [209, 232]
block_3a88154a  [233, 252]
```

这样压缩块覆盖到第 `252` 轮，`recent_messages` 覆盖第 `253-277` 轮。

校验关系：

```text
252 + 25 = 277
50 条 recent_messages < 80 条 L3 触发阈值
```

因此服务加载后不会立即触发 L3。继续新增 `15` 个有效轮次后，`recent_messages` 达到 `40` 轮，才会正常触发下一次 L3。

## 执行变更

先修正 `11/data` 中的目标数据：

- 更新 `11/data/characters/JuyaoHuang/11/chats/20260513_f2bb7b12/short_term_memory.json`
- 更新 `11/data/chats/JuyaoHuang/11/index.json`

随后覆盖到 `atri/data`：

```text
11/data/characters/JuyaoHuang/11/chats/20260513_f2bb7b12/sessions/2026-05-13_656ffee8.json
-> atri/data/characters/JuyaoHuang/11/chats/20260513_f2bb7b12/sessions/2026-05-13_656ffee8.json

11/data/characters/JuyaoHuang/11/chats/20260513_f2bb7b12/short_term_memory.json
-> atri/data/characters/JuyaoHuang/11/chats/20260513_f2bb7b12/short_term_memory.json

11/data/chats/JuyaoHuang/11/sessions/20260513_f2bb7b12.json
-> atri/data/chats/JuyaoHuang/11/sessions/20260513_f2bb7b12.json

11/data/chats/JuyaoHuang/11/index.json
-> atri/data/chats/JuyaoHuang/11/index.json
```

同时将前端聊天索引的 `message_count` 从旧值 `902` 修正为实际消息数 `818`。

## 验证结果

覆盖后验证：

```text
归档 session 有效轮次: 277
short_term_memory.total_rounds: 277
recent_messages: 50 条，即 25 轮
recent_messages 角色顺序: human/ai 成对
recent_messages 来源: session 第 253-277 轮
max(covers_rounds.end): 252
coverage relation: 252 + 25 = 277
would_trigger_l3_now: False
前端 session 消息数: 818
index.json message_count: 818
11/data 与 atri/data 对应文件哈希一致: True
```

## 注意事项

本次修复只处理本地 JSON 数据：

- 前端渲染历史：`data/chats`
- 记忆归档与短期上下文：`data/characters`

如果 mem0、Qdrant 或其他长期记忆存储中已经写入了不希望保留的记忆，本次 JSON 覆盖不会自动清理它们。长期记忆需要单独检查和清理。

## 后续建议

如果以后继续手工编辑聊天历史，应同步检查：

- `data/chats/.../index.json` 的 `message_count`
- `data/chats/.../sessions/*.json` 的前端消息数
- `data/characters/.../sessions/*.json` 的有效 `(human, ai)` 轮次
- `short_term_memory.json.total_rounds`
- `max(covers_rounds.end) + recent_messages/2`
- `recent_messages` 是否严格 `human/ai` 成对

这些字段不一致时，服务未必立刻报错，但下一轮上下文压缩可能会从错误轮次开始。
