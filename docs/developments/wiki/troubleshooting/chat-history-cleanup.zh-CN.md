---
status: active
owner: storage
created: 2026-07-09
updated: 2026-07-09
source: docs/configs/CN/对话历史存储与批量删除说明.md
related_code:
  - src/routes/chats.py
  - src/routes/data.py
  - src/storage/json_storage.py
  - src/memory/manager.py
  - frontend/src/pages/settings/data.vue
---

# 聊天历史清理与记忆删除

本文是准备迁移到 GitHub Wiki 的中文排障稿，说明聊天标题、短期记忆和长期记忆的清理边界。

开发侧存储结构见：

- [聊天历史存储结构](../../modules/storage/chat-history-storage.zh-CN.md)
- [MemoryManager 角色记忆归档](../../modules/memory/chat-history-archive.zh-CN.md)

## 先分清三种“删除”

当前项目里最容易混淆的，是下面三类操作：

| 操作 | 作用范围 | 结果 |
| --- | --- | --- |
| 删除聊天标题 | `data/chats` | 前端侧边栏不再显示该聊天，对应消息 session 文件也会一起删除 |
| 清理短期记忆 | `data/characters/{user_id}/{character_id}/chats/{chat_id}` | 删除该聊天的 `short_term_memory.json`，并重置运行中缓存 |
| 清理长期记忆 | mem0 / Qdrant | 删除当前用户与角色的长期事实，完成时间可能滞后 |

删除聊天标题不会自动删除短期记忆；删除短期记忆也不会自动把聊天标题从前端历史里移除。

## 优先使用 `/settings/data`

如果你只是做常规维护，优先走前端数据管理页：

```text
/settings/data
```

这个页面当前提供三类动作：

1. 删除单个聊天标题：
   - 语义与首页侧边栏删除完全一致。
2. 清理某个聊天标题的短期记忆：
   - 调用 `DELETE /api/data/characters/{character_id}/chats/{chat_id}/short-term-memory`
   - 后端会同时清理磁盘文件和当前运行中的缓存。
3. 清理当前用户 + 角色的长期记忆：
   - 调用 `DELETE /api/data/characters/{character_id}/long-term-memory`
   - 后端只提交删除请求，不保证外部 mem0 立刻完成。

## 手工清理前准备

手工删文件前，建议先停止后端服务。原因有两个：

1. `data/chats` 和 `data/characters` 里都有原子写入过程，运行时删除容易和 `.tmp` 文件竞争。
2. 即使文件删对了，运行中的内存缓存也可能还持有旧数据。

推荐先备份：

```powershell
Compress-Archive -Path .\data\chats, .\data\characters -DestinationPath .\data-history-backup.zip -Force
```

上面命令应在仓库根目录 `atri` 下执行。

## 当前路径约定

### 聊天标题与消息

默认聊天历史路径：

```text
data/chats/{user_id}/{character_id}/index.json
data/chats/{user_id}/{character_id}/sessions/{chat_id}.json
```

本地模式通常是：

```text
data/chats/default/{character_id}/...
```

认证开启后，`default` 会变成真实用户隔离目录。

### 短期记忆与归档

当前聊天级短期记忆路径：

```text
data/characters/{user_id}/{character_id}/chats/{chat_id}/short_term_memory.json
data/characters/{user_id}/{character_id}/chats/{chat_id}/sessions/{session_id}.json
```

兼容迁移期间，角色级旧路径 `data/characters/{character_id}/` 可能仍存在，但不再是新的聊天级写入真相。

## 删除单个角色的所有聊天标题

删除某个角色在前端历史里可见的全部聊天：

```powershell
Remove-Item -LiteralPath ".\data\chats\default\CHARACTER_ID" -Recurse -Force
```

将 `CHARACTER_ID` 替换为角色 ID。若当前不是本地默认用户，请把 `default` 改成真实用户目录。

## 删除当前用户的全部聊天标题

删除当前默认用户的全部聊天历史：

```powershell
Remove-Item -LiteralPath ".\data\chats\default" -Recurse -Force
```

如果你想清空整个聊天 JSON 根目录，也可以删除：

```powershell
Remove-Item -LiteralPath ".\data\chats" -Recurse -Force
```

后续新建聊天时，后端会重新创建目录与索引文件。

## 按标题手工删除聊天

当前后端没有“按标题批量删除”的 REST API。需要停服务后，手工改 `index.json` 并删除对应 `sessions/{chat_id}.json`。

下面示例会删除指定角色下标题完全等于 `TITLE_TO_DELETE` 的聊天：

```powershell
$characterId = "CHARACTER_ID"
$title = "TITLE_TO_DELETE"
$chatDir = ".\data\chats\default\$characterId"
$indexPath = Join-Path $chatDir "index.json"
$sessionsDir = Join-Path $chatDir "sessions"

$index = Get-Content -Raw -LiteralPath $indexPath | ConvertFrom-Json
$matched = @($index.chats | Where-Object { $_.title -eq $title })

foreach ($chat in $matched) {
  $sessionPath = Join-Path $sessionsDir "$($chat.id).json"
  Remove-Item -LiteralPath $sessionPath -Force -ErrorAction SilentlyContinue
}

$index.chats = @($index.chats | Where-Object { $_.title -ne $title })
$index | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $indexPath -Encoding UTF8
```

模糊匹配时，可以把条件改成：

```powershell
Where-Object { $_.title -like "*keyword*" }
```

## 只清理短期记忆

如果你只想让某个聊天标题的短期记忆从头重建，优先使用 `/settings/data`。

手工路径是：

```text
data/characters/{user_id}/{character_id}/chats/{chat_id}/short_term_memory.json
```

必要时也一并检查：

```text
data/characters/{user_id}/{character_id}/chats/{chat_id}/short_term_memory.json.tmp
```

注意：

- 这不会删除聊天标题。
- 这不会删除归档 session。
- 若后端进程还活着，手工删文件后仍建议重启，避免缓存继续使用旧状态。

## 清理长期记忆

长期记忆请优先通过 `/settings/data` 提交删除。

原因是：

- mem0 可能运行在外部服务。
- 本地模式还可能有 `data/qdrant` 等额外存储。
- 只删 `data/characters` 不等于删掉长期记忆。

因此，长期记忆的正确心智模型是“提交删除请求”，不是“本地删一个目录就完成”。

## 删除后验证

### 验证聊天标题索引

```powershell
$index = Get-Content -Raw ".\data\chats\default\CHARACTER_ID\index.json" | ConvertFrom-Json
$index.chats.Count
```

### 验证 session 文件是否残留

```powershell
Get-ChildItem ".\data\chats\default\CHARACTER_ID\sessions" -Filter "*.json"
```

### 验证短期记忆是否已重建或已清空

- 重新进入聊天并发送一轮消息。
- 观察 `short_term_memory.json` 是否按预期重建。
- 若用了 `/settings/data` 清理接口，确认返回提示里已经包含“已同步当前运行中的记忆状态”。

### 验证长期记忆删除

- 检查接口返回是否为 `submitted`。
- 如果接入的是外部 mem0，再去对应 Dashboard 或后端日志确认异步删除完成。

## 什么时候还要看记忆修复文档

如果你不是“整段删除”，而是手工修改了聊天 JSON、裁掉了部分轮次、保留了部分 summary，那么这篇不够用。请继续看：

- [手工修改聊天历史后的记忆修复](chat-history-memory-repair.zh-CN.md)

## 相关文档

- [chat-history-cleanup.en-US.md](chat-history-cleanup.en-US.md)
- [../../modules/storage/chat-history-storage.zh-CN.md](../../modules/storage/chat-history-storage.zh-CN.md)
- [../../modules/memory/chat-history-archive.zh-CN.md](../../modules/memory/chat-history-archive.zh-CN.md)
