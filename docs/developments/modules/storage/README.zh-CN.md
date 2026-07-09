---
status: active
owner: storage
created: 2026-07-09
updated: 2026-07-09
---

# Storage 模块长期设计

本目录保存存储模块的长期设计。当前文档覆盖两类开发者需要长期依赖的存储：

1. 用户可见的聊天列表与聊天消息存储
2. 角色 Persona 与托管头像存储

用户侧维护入口仍是 [对话历史存储与批量删除说明](../../../configs/CN/对话历史存储与批量删除说明.md)。

## 当前文档

| 文档 | 内容 |
| --- | --- |
| [chat-history-storage.zh-CN.md](chat-history-storage.zh-CN.md) | 聊天列表与聊天消息的 JSON 存储结构、REST/API 边界、消息元数据和删除语义。 |
| [chat-history-storage.en-US.md](chat-history-storage.en-US.md) | English version of the frontend chat history storage structure. |
| [character-storage.zh-CN.md](character-storage.zh-CN.md) | 角色 markdown、托管头像、系统角色保护和 `/api/characters` 存储边界。 |

## 模块边界

Storage 模块负责：

- 为聊天列表和聊天详情提供持久化实现。
- 为角色创建、更新、删除和头像托管提供文件落盘能力。

它不负责：

- 组装 LLM 上下文或记忆压缩状态。
- 直接向前端暴露文件路径作为读取接口。

前端应通过 REST/WebSocket 访问存储结果，而不是直接读取 `data/` 或 `prompts/` 下的文件。

## 阅读路径

建议按下面顺序阅读：

1. [chat-history-storage.zh-CN.md](chat-history-storage.zh-CN.md)
2. [character-storage.zh-CN.md](character-storage.zh-CN.md)
3. `src/storage/json_storage.py`
4. `src/storage/character_storage.py`
5. `src/routes/chats.py`
6. `src/routes/characters.py`
