---
status: active
owner: storage
created: 2026-07-09
updated: 2026-07-09
source:
  - src/storage/interface.py
  - src/storage/factory.py
  - src/storage/json_storage.py
  - src/storage/character_storage.py
  - src/routes/chats.py
  - src/routes/data.py
related_code:
  - src/storage/interface.py
  - src/storage/factory.py
  - src/storage/json_storage.py
  - src/storage/character_storage.py
  - src/storage/db_storage.py
  - src/routes/chats.py
  - src/routes/data.py
---

# Storage 模块总设计

本文把 `src/storage/` 的整体设计接起来。现有文档已经分别讲了聊天历史和角色存储，但还缺一页说明：

1. 存储模块内部的抽象层和实现层如何划分。
2. 为什么“聊天存储”和“记忆 archive”要严格分开。
3. 最近的用户隔离、聊天范围化和数据清理演化如何落到当前代码。

## 模块定位

当前 `storage` 模块负责的是**用户可见业务数据的持久化**，不是运行时记忆状态。

它主要覆盖两类数据：

- 聊天标题与聊天消息
- 角色 Persona 文件与托管头像

它不负责：

- L1/L3/L4 短期压缩状态
- mem0 长期记忆
- Live2D 前端运行时偏好

这条边界非常重要：`storage` 持有“用户看见什么”，`memory` 持有“LLM 记住什么”。

## 模块组成

当前 `src/storage/` 可以稳定拆成五部分：

| 组件 | 代码 | 职责 |
| --- | --- | --- |
| 抽象接口 | `interface.py` | 定义聊天存储操作契约。 |
| 工厂层 | `factory.py` | 按配置选择具体聊天存储实现。 |
| JSON 聊天存储 | `json_storage.py` | 当前正式使用的聊天持久化实现。 |
| 角色存储 | `character_storage.py` | Persona Markdown 与托管头像的后端存储。 |
| 数据库占位 | `db_storage.py` | Phase 7 预留，不是当前可用实现。 |

`live2d_storage.py` 虽然也在 `src/storage/` 下，但当前文档上已经作为独立 `modules/live2d/` 处理，不在本页展开。

## 聊天存储抽象

`ChatStorageInterface` 当前定义了完整聊天存储契约，包含：

- 创建聊天
- 列表查询
- 按用户/角色范围查元数据
- 更新标题
- 删除聊天
- 追加消息
- 分页读取消息

长期设计意义：

- 路由层依赖的是行为契约，而不是文件格式；
- JSON 与未来数据库实现保持同一 API 面；
- 用户作用域和角色作用域已经进入接口层，而不是只存在于具体实现里。

## 当前正式实现：`JSONChatStorage`

当前真正被工厂返回并用于生产路径的实现只有 `JSONChatStorage`。

它的长期特征是：

1. 以 `data/chats/{user_id}/{character_id}/` 为根。
2. 用 `index.json` 保存聊天列表索引。
3. 用 `sessions/{chat_id}.json` 保存消息数组。
4. 所有 JSON 写入都通过 `.tmp + atomic_replace` 保持原子性。

这意味着当前聊天持久化是：

- 文件系统驱动；
- 人类可读；
- 易于手工排障；
- 但不等于未来数据库设计已经落地。

## 用户隔离与聊天范围化

近期 `git log` 里和存储最相关的演化包括：

- `feat: add JSONChatStorage with file-based chat persistence`
- `feat: add chat CRUD REST API with LLM title generation`
- `feat: scope chat storage by user`
- `feat: add settings data cleanup endpoints`
- `feat: 添加聊天范围内存管理功能，支持聊天 ID 以区分用户会话`

这几步共同确认了当前长期事实：

1. 聊天存储已经按 `user_id` 隔离。
2. 聊天消息和聊天标题是显式按 `chat_id` 管理的。
3. 记忆清理能力已经进入 `/api/data`，但那不是聊天存储自身的职责。

## 聊天数据流

当前用户可见聊天数据的主要写入路径是：

```text
POST /api/chats
  -> create_chat()
  -> index.json + empty session

WebSocket chat complete / interrupted
  -> append_message_for_user()
  -> sessions/{chat_id}.json
  -> update index.json metadata
```

这里的长期约束是：

- 聊天标题由 `/api/chats` 创建；
- 聊天消息由 WebSocket 流结束或中断时写入；
- 用户可见聊天列表和消息详情都来自这套存储；
- 这套存储不关心短期记忆是否同步压缩成功。

## 消息元数据边界

当前聊天 session 文件并不是“任意 metadata 透传容器”。`JSONChatStorage` 会显式清洗，只保留：

- `generation_id`
- `interrupted`
- `interrupt_reason`

长期意义：

- session 文件结构可控；
- VAD/TTS 语义可以在消息层被追踪；
- 不会因为某次临时调试往消息里塞一大坨未知字段。

## 角色存储设计

`CharacterStorage` 当前负责：

- 角色 Persona Markdown 文件
- frontmatter 渲染
- 名称唯一性校验
- 托管头像上传与清理
- 系统角色删除保护

角色数据的事实来源是：

```text
prompts/persona/{character_id}.md
data/avatars/{managed-file}
```

这意味着角色存储比聊天存储更接近“内容源文件管理”，而不是简单 JSON 容器。

## 名称、ID 与托管头像

当前角色存储的长期约束：

- `character_id` 是文件名级标识；
- `name` 是展示名；
- 自定义角色名只允许字母和数字；
- 若请求 ID 冲突，会自动加后缀；
- 托管头像只允许 PNG/JPG/WEBP，大小不超过 2MB；
- 删除托管角色时会同步删掉其托管头像文件。

这条边界让前端角色 CRUD 能稳定地依赖后端存储，而不用自己处理文件系统细节。

## 工厂与数据库占位

`create_chat_storage(config)` 当前只支持：

- `mode = json`

`mode = database` 仍然明确抛：

```text
NotImplementedError("Database storage is reserved for Phase 7")
```

这条约束必须写清楚，因为旧规划或未来想象里“数据库模式”容易被误当成已经存在。

当前结论是：

- 抽象层已经准备好了；
- 数据库实现只是占位；
- 当前所有真实业务路径都应按 JSON 存储来理解和验证。

## 与 `/api/data` 的关系

`src/routes/data.py` 虽然不直接属于聊天存储模块，但它是存储清理边界的一部分：

- 清理短期记忆
- 提交长期记忆删除

这里的长期边界是：

- `/api/data` 不删除聊天标题真相，除非显式走 `/api/chats/{id}/delete`
- 短期记忆清理是 `memory` 侧行为；
- 聊天历史删除是 `storage` 侧行为；
- 二者不能混为一个“清空聊天”的动作。

## 与 `memory` 的边界

当前最关键的系统边界之一就是：

| 数据面 | 路径 | 用途 |
| --- | --- | --- |
| 聊天存储 | `data/chats/...` | 前端侧边栏和聊天详情 |
| 记忆 archive | `data/characters/.../sessions/` | 恢复短期状态、审计、L3/L4 重建 |
| 短期状态 | `data/characters/.../short_term_memory.json` | LLM 上下文拼装 |

同一轮聊天会同时写到聊天存储和记忆 archive，但两者语义不同，不能互相替代。

## 与旧设计材料的取舍

`wiki/Storage/存储设计.md` 当前几乎没有实际可迁移内容，因此本页主要依据当前代码和 git 演化整理。

已经是当前事实的部分：

- 聊天文件按用户/角色隔离
- `ChatStorageInterface`
- JSON 文件实现
- 角色 Persona 与头像托管
- 数据库模式仍未实现

还不是当前事实的部分：

- 真正可用的数据库后端
- 聊天与记忆统一存储层
- 前端直接读取磁盘文件

## 相关文档

- [README.zh-CN.md](README.zh-CN.md)
- [chat-history-storage.zh-CN.md](chat-history-storage.zh-CN.md)
- [character-storage.zh-CN.md](character-storage.zh-CN.md)
- [../memory/design.zh-CN.md](../memory/design.zh-CN.md)
