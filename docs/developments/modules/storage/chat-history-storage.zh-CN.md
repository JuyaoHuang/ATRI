---
status: active
owner: storage
created: 2026-07-09
updated: 2026-07-09
source: docs/configs/CN/对话历史存储与批量删除说明.md
related_code:
  - src/routes/chats.py
  - src/storage/json_storage.py
  - config/storage_config.yaml
---

# 聊天历史存储结构

本文沉淀前端聊天列表历史的开发侧存储结构。批量删除操作步骤见 [对话历史存储与批量删除说明](../../../configs/CN/对话历史存储与批量删除说明.md)。

## 存储定位

前端侧边栏的聊天标题和消息详情来自：

- `src/routes/chats.py`
- `src/storage/json_storage.py`

默认配置：

```yaml
mode: json

json:
  base_path: data/chats
```

通常从 `atri` 目录启动后端时，实际路径为：

```text
data/chats/default/{character_id}/index.json
data/chats/default/{character_id}/sessions/{chat_id}.json
```

## 文件职责

| 文件 | 职责 |
| --- | --- |
| `index.json` | 聊天列表索引，保存标题、创建时间、更新时间和消息数量。 |
| `sessions/{chat_id}.json` | 单个聊天的完整消息数组。 |

`index.json` 是前端列表展示的入口。孤立的 session 文件不会自动显示到侧边栏。

## 当前用户维度

本地模式下，路径中的 `default` 是默认用户 ID：

```text
data/chats/default/
```

认证开启后，存储层应以认证用户身份作为隔离维度。任何涉及用户隔离的改动，都需要同时检查 Auth 和 Storage 两侧设计。

## 删除语义

通过前端删除单个聊天时，后端应同时：

1. 从 `index.json` 移除对应条目。
2. 删除 `sessions/{chat_id}.json`。

手工删除时，也应保持这两个文件的一致性。否则会出现索引指向不存在 session，或 session 孤立但前端不可见。

## 运行目录约束

`data/chats` 是相对路径。若后端从非仓库根目录启动，相对路径会相对启动目录解析。

无法确认真实路径时，应优先检查：

- 后端启动命令的工作目录。
- `config/storage_config.yaml`。
- 后端日志中的存储初始化路径。

## 相关文档

- [对话历史存储与批量删除说明](../../../configs/CN/对话历史存储与批量删除说明.md)
- [MemoryManager 角色记忆归档](../memory/chat-history-archive.zh-CN.md)
