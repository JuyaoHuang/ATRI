---
status: active
owner: storage
created: 2026-07-09
updated: 2026-07-09
source: docs/configs/EN/chat-history-storage-batch-deletion.md
related_code:
  - src/routes/chats.py
  - src/routes/data.py
  - src/storage/json_storage.py
  - src/memory/manager.py
  - frontend/src/pages/settings/data.vue
---

# Chat History Cleanup and Memory Deletion

This GitHub Wiki draft explains how to clean chat titles, short-term memory, and long-term memory without mixing their storage boundaries.

Development-side storage notes:

- [Chat History Storage Structure](../../modules/storage/chat-history-storage.zh-CN.md)
- [MemoryManager Chat Archive](../../modules/memory/chat-history-archive.zh-CN.md)

## Distinguish Three Kinds of Deletion

| Operation | Scope | Result |
| --- | --- | --- |
| Delete chat title | `data/chats` | The frontend sidebar no longer shows the chat, and the matching message session file is removed. |
| Clear short-term memory | `data/characters/{user_id}/{character_id}/chats/{chat_id}` | The chat-level `short_term_memory.json` is removed and the running cache is reset. |
| Clear long-term memory | mem0 / Qdrant | Long-term facts for the current user and character are deleted or deletion is submitted. |

Deleting a chat title does not automatically delete short-term memory. Clearing short-term memory does not remove the chat title from the frontend history.

## Prefer `/settings/data`

For routine maintenance, use the frontend data management page first:

```text
/settings/data
```

It currently provides three actions:

1. Delete one chat title.
2. Clear short-term memory for a selected chat title through `DELETE /api/data/characters/{character_id}/chats/{chat_id}/short-term-memory`.
3. Clear long-term memory for the current user and character through `DELETE /api/data/characters/{character_id}/long-term-memory`.

The long-term memory endpoint submits the deletion request. External mem0 backends may finish asynchronously.

## Prepare Before Manual Cleanup

Stop the backend before deleting files by hand. Runtime deletion can race with atomic `.tmp` writes, and in-memory caches may still hold old state.

Back up first from the repository root:

```powershell
Compress-Archive -Path .\data\chats, .\data\characters -DestinationPath .\data-history-backup.zip -Force
```

## Current Path Conventions

### Chat Titles and Messages

Default chat history paths:

```text
data/chats/{user_id}/{character_id}/index.json
data/chats/{user_id}/{character_id}/sessions/{chat_id}.json
```

In local mode, `{user_id}` is usually `default`:

```text
data/chats/default/{character_id}/...
```

When authentication is enabled, `default` becomes the authenticated user directory.

### Short-Term Memory and Archive

Current chat-level memory paths:

```text
data/characters/{user_id}/{character_id}/chats/{chat_id}/short_term_memory.json
data/characters/{user_id}/{character_id}/chats/{chat_id}/sessions/{session_id}.json
```

During compatibility migration, old character-level paths such as `data/characters/{character_id}/` may still exist. They are not the source of truth for new chat-level writes.

## Delete All Chat Titles for One Character

Delete all frontend-visible chats for one character:

```powershell
Remove-Item -LiteralPath ".\data\chats\default\CHARACTER_ID" -Recurse -Force
```

Replace `CHARACTER_ID` with the character ID. If you are not using the local default user, replace `default` with the real user directory.

## Delete All Chat Titles for the Current User

Delete all frontend chat history for the default local user:

```powershell
Remove-Item -LiteralPath ".\data\chats\default" -Recurse -Force
```

To clear the whole JSON chat root:

```powershell
Remove-Item -LiteralPath ".\data\chats" -Recurse -Force
```

The backend recreates directories and indexes when new chats are created.

## Delete Chats by Title Manually

The current backend does not provide a batch-delete-by-title REST API. Stop the backend, edit `index.json`, and delete the matching `sessions/{chat_id}.json` files.

Example for an exact title match:

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

For fuzzy matching:

```powershell
Where-Object { $_.title -like "*keyword*" }
```

## Clear Only Short-Term Memory

If you only want a chat's short-term memory to rebuild from scratch, prefer `/settings/data`.

Manual path:

```text
data/characters/{user_id}/{character_id}/chats/{chat_id}/short_term_memory.json
```

Also check the temporary file when needed:

```text
data/characters/{user_id}/{character_id}/chats/{chat_id}/short_term_memory.json.tmp
```

Notes:

- This does not delete the chat title.
- This does not delete archive sessions.
- Restart the backend after manual deletion to avoid stale in-memory cache.

## Clear Long-Term Memory

Use `/settings/data` for long-term memory deletion.

Reasons:

- mem0 may run as an external service.
- Local mode may also use extra stores such as `data/qdrant`.
- Deleting `data/characters` is not the same as deleting long-term memory.

Treat long-term memory deletion as a submitted request, not as a single local-directory removal.

## Verify After Deletion

Check the chat title index:

```powershell
$index = Get-Content -Raw ".\data\chats\default\CHARACTER_ID\index.json" | ConvertFrom-Json
$index.chats.Count
```

Check remaining session files:

```powershell
Get-ChildItem ".\data\chats\default\CHARACTER_ID\sessions" -Filter "*.json"
```

For short-term memory, re-enter the chat and send one message, then check whether `short_term_memory.json` is rebuilt as expected.

For long-term memory, check the API result and, if using external mem0, confirm completion from the backend logs or service dashboard.

## Related Documents

- [chat-history-cleanup.zh-CN.md](chat-history-cleanup.zh-CN.md)
- [../../modules/storage/chat-history-storage.zh-CN.md](../../modules/storage/chat-history-storage.zh-CN.md)
- [../../modules/memory/chat-history-archive.zh-CN.md](../../modules/memory/chat-history-archive.zh-CN.md)
