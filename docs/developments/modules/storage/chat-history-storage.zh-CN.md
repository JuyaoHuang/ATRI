---
status: active
owner: storage
created: 2026-07-09
updated: 2026-07-09
source: docs/configs/CN/对话历史存储与批量删除说明.md
related_code:
  - src/routes/chats.py
  - src/routes/chat_ws.py
  - src/storage/json_storage.py
  - src/storage/interface.py
  - config/storage_config.yaml
---

# 聊天历史存储结构

本文沉淀用户可见聊天历史的开发侧存储结构。批量删除操作步骤见 [对话历史存储与批量删除说明](../../../configs/CN/对话历史存储与批量删除说明.md)。

## 存储定位

前端侧边栏的聊天标题和消息详情来自后端 API，不来自浏览器直接读磁盘文件：

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
data/chats/{user_id}/{character_id}/index.json
data/chats/{user_id}/{character_id}/sessions/{chat_id}.json
```

## 文件职责

| 文件 | 职责 |
| --- | --- |
| `index.json` | 聊天列表索引，保存标题、创建时间、更新时间和消息数量。 |
| `sessions/{chat_id}.json` | 单个聊天的消息容器，当前结构为 `{"messages": [...]}`。 |

`index.json` 是前端列表展示的入口。孤立的 session 文件不会自动显示到侧边栏。

## `index.json` 结构

当前索引结构：

```json
{
  "chats": [
    {
      "id": "20260709_ab12cd34",
      "title": "聊天标题",
      "character_id": "atri",
      "created_at": "2026-07-09T12:34:56+00:00",
      "updated_at": "2026-07-09T12:35:10+00:00",
      "message_count": 2
    }
  ]
}
```

`JSONChatStorage.create_chat()` 会同时创建这条索引记录和一个空的 session 文件。

## `sessions/{chat_id}.json` 结构

当前 session 文件结构：

```json
{
  "messages": [
    {
      "role": "human",
      "content": "你好",
      "timestamp": "2026-07-09T12:35:01+00:00",
      "name": "default"
    },
    {
      "role": "ai",
      "content": "你好呀",
      "timestamp": "2026-07-09T12:35:03+00:00",
      "name": "atri",
      "generation_id": "gen_123",
      "interrupted": false
    }
  ]
}
```

消息元数据当前只保留三个字段：

- `generation_id`
- `interrupted`
- `interrupt_reason`

`JSONChatStorage` 会丢弃其他未知 `metadata` 键，避免 session 文件变成无边界的透传容器。

## 用户维度

认证关闭时，`get_request_user_id()` 和 `get_websocket_user_id()` 会回退到：

```text
default
```

因此本地默认路径通常会变成：

```text
data/chats/default/{character_id}/
```

认证开启后，存储层以真实认证用户作为隔离维度。任何涉及用户隔离的改动，都要同时检查 Auth 和 Storage 两侧实现。

## 写入路径

当前消息写入主要有两条入口：

1. REST `POST /api/chats`：创建聊天索引与空 session
2. WebSocket `src/routes/chat_ws.py`：在流式回复完成或被打断时追加 human/ai 消息

`append_message_for_user()` 每次写入都会：

1. 读取 session 文件
2. 追加一条消息
3. 原子写回 session 文件
4. 更新 `index.json` 中对应聊天的 `message_count` 与 `updated_at`

## 删除语义

通过前端删除单个聊天时，后端应同时：

1. 从 `index.json` 移除对应条目。
2. 删除 `sessions/{chat_id}.json`。

手工删除时，也应保持这两个文件的一致性。否则会出现索引指向不存在 session，或 session 孤立但前端不可见。

删除聊天不会自动清理 Memory 模块下的 `data/characters/...` 归档或 mem0 长期记忆。那是独立的数据面。

## 运行目录约束

`data/chats` 是相对路径。若后端从非仓库根目录启动，相对路径会相对启动目录解析。

无法确认真实路径时，应优先检查：

- 后端启动命令的工作目录。
- `config/storage_config.yaml`。
- 后端日志中的存储初始化路径。

## 相关文档

- [对话历史存储与批量删除说明](../../../configs/CN/对话历史存储与批量删除说明.md)
- [MemoryManager 角色记忆归档](../memory/chat-history-archive.zh-CN.md)
- [角色存储设计](character-storage.zh-CN.md)
