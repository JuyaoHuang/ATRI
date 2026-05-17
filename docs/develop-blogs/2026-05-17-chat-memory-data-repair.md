# 手工修改聊天历史后的短期记忆修复指南

## 适用场景

当你手工删除或改写某个角色的聊天历史后，需要同步修复短期记忆文件。

典型场景：

- 删除了不希望保留的对话轮次。
- 修改了前端聊天历史，但记忆归档还没同步。
- 修改了归档 session，但 `short_term_memory.json` 仍是旧轮次。
- 重启服务后担心上下文压缩从错误轮次开始。
- 希望保留已经满意的 L3/L4 `summary`，只修正轮次元数据。

这类问题不要只改一处 JSON。前端历史、归档历史、短期记忆三者必须一起对齐。

## 三类文件

前端渲染用历史：

```text
data/chats/{user_id}/{character_id}/index.json
data/chats/{user_id}/{character_id}/sessions/{chat_id}.json
```

记忆压缩来源：

```text
data/characters/{user_id}/{character_id}/chats/{chat_id}/sessions/{session_id}.json
```

短期记忆状态：

```text
data/characters/{user_id}/{character_id}/chats/{chat_id}/short_term_memory.json
```

`data/chats` 负责前端展示。`data/characters` 负责上下文压缩与 LLM 输入。

## 核心原则

修复时以归档 session 为唯一轮次来源：

```text
data/characters/{user_id}/{character_id}/chats/{chat_id}/sessions/{session_id}.json
```

有效轮次的定义：

```text
一条 human 消息 + 下一条有效 ai 消息 = 1 轮
```

无效 AI 回复不会计入轮次。常见无效回复包括空内容或以 `Error` 开头的内容。

## 必须满足的不变量

修复后的 `short_term_memory.json` 必须满足：

```text
total_rounds = 归档 session 的有效轮次数
max(covers_rounds.end) + recent_rounds = total_rounds
recent_rounds = recent_messages 条数 / 2
recent_messages 必须严格 human/ai 成对
recent_messages 必须来自归档 session 的尾部轮次
```

还要确认：

```text
recent_messages 条数 < 80
```

当前配置为：

```text
compress_rounds = 20
keep_recent_rounds = 20
```

因此 L3 触发阈值是：

```text
(20 + 20) * 2 = 80 条消息
```

如果 `recent_messages` 已经达到 `80` 条，下一次服务处理可能会触发 L3。

## 不要误解 covers_rounds

`covers_rounds` 不会作为聊天内容发送给 LLM。

上下文发送逻辑使用：

- `meta_blocks[*].summary`
- `active_blocks[*].summary`
- `recent_messages`

但 `covers_rounds` 仍然重要。它决定下一次 L3 从哪一轮开始：

```text
下一次 L3 起点 = max(covers_rounds.end) + 1
```

所以 `covers_rounds` 可以只作为轮次标记修正，但不能乱填。

## 推荐修复流程

### 1. 备份文件

先备份目标目录，至少备份这四个文件：

```text
data/chats/{user_id}/{character_id}/index.json
data/chats/{user_id}/{character_id}/sessions/{chat_id}.json
data/characters/{user_id}/{character_id}/chats/{chat_id}/sessions/{session_id}.json
data/characters/{user_id}/{character_id}/chats/{chat_id}/short_term_memory.json
```

不要直接在唯一副本上手改。

### 2. 统计归档 session 的有效轮次

从 `data/characters/.../sessions/{session_id}.json` 统计有效 `(human, ai)` 对。

记录：

```text
N = 有效轮次数
```

后续 `short_term_memory.total_rounds` 必须等于 `N`。

### 3. 决定 recent_messages 保留多少轮

如果你要保留当前 `recent_messages`，先确认它是否来自 session 尾部。

例如当前保留 `R = 25` 轮：

```text
recent_messages = session 第 N-R+1 到 N 轮
```

如果不确定，推荐从 session 尾部重新生成 `recent_messages`，只保留：

```json
{"role": "human", "content": "..."}
{"role": "ai", "content": "..."}
```

不要混入前端用的 `timestamp`、`name`、`avatar` 字段。

### 4. 计算压缩块最大结束轮次

公式：

```text
max_block_end = N - R
```

例如：

```text
N = 277
R = 25
max_block_end = 252
```

所有 `meta_blocks` 和 `active_blocks` 的 `covers_rounds` 最大结束值必须是 `252`。

### 5. 重新分配 covers_rounds

保留你满意的 `summary` 和 `block_id`。

只调整：

```text
covers_rounds
total_rounds
recent_messages
```

如果你要保留现有 L4 摘要，不需要重新压缩 L4。L4 的 `summary` 会继续加入上下文。

### 6. 同步前端 index

如果你修改了前端聊天历史：

```text
data/chats/{user_id}/{character_id}/sessions/{chat_id}.json
```

就必须同步：

```text
data/chats/{user_id}/{character_id}/index.json
```

其中：

```text
index.json 的 message_count = sessions/{chat_id}.json 中 messages 的实际条数
```

## 本次案例

本次修复对象：

```text
user_id = JuyaoHuang
character_id = 11
chat_id = 20260513_f2bb7b12
session_id = 2026-05-13_656ffee8
```

归档 session 有效轮次：

```text
N = 277
```

保留最近轮次：

```text
R = 25
recent_messages = 第 253-277 轮
```

因此：

```text
max_block_end = 277 - 25 = 252
```

最终 `covers_rounds`：

```text
meta_c44a2ea9   [1, 80]
meta_6743a00d   [81, 160]
meta_5fa01aec   [161, 184]
meta_23bfff2a   [185, 208]
meta_5a80c280   [209, 232]
block_3a88154a  [233, 252]
```

校验：

```text
252 + 25 = 277
recent_messages = 50 条
50 < 80
```

因此服务加载后不会立即触发 L3。

## 覆盖数据的顺序

如果你先在临时目录修复数据，例如 `11/data`，再迁移到实际工作目录，例如 `atri/data`，推荐顺序是：

1. 修复临时目录里的 `short_term_memory.json`。
2. 修复临时目录里的 `index.json`。
3. 校验临时目录的轮次关系。
4. 将临时目录的四个目标 JSON 覆盖到实际工作目录。
5. 再次校验实际工作目录。

本次覆盖路径：

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

## 最终校验清单

修复后必须确认：

- `session` 有效轮次等于 `short_term_memory.total_rounds`。
- `recent_messages` 条数为偶数。
- `recent_messages` 严格按 `human/ai` 成对。
- `recent_messages` 等于 session 尾部 `R` 轮。
- `max(covers_rounds.end) + R = total_rounds`。
- `recent_messages` 条数小于 `80`，避免立即触发 L3。
- 前端 `index.json.message_count` 等于前端 session 的实际 `messages` 条数。
- 临时目录和实际工作目录的目标文件一致。

## 常见错误

### 只修改 total_rounds

这不够。下一次 L3 起点仍由 `covers_rounds` 推导。

### 只修改 covers_rounds

这也不够。`recent_messages` 必须对应剩余尾部轮次。

### recent_messages 使用前端消息格式

不推荐。短期记忆只需要 `role` 和 `content`。

### 忘记同步 index.json

前端聊天列表会继续显示旧的 `message_count`。

### 忘记长期记忆

本指南只修复本地 JSON。mem0、Qdrant 或其他长期记忆存储不会自动清理。

如果不希望保留某些长期记忆，需要单独检查长期记忆存储。
