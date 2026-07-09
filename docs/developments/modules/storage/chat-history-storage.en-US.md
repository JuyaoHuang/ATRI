---
status: active
owner: storage
created: 2026-07-09
updated: 2026-07-09
source: docs/configs/EN/chat-history-storage-batch-deletion.md
related_code:
  - src/routes/chats.py
  - src/storage/json_storage.py
  - config/storage_config.yaml
---

# Chat History Storage Structure

This document captures the development-side storage structure for frontend chat list history. Operational cleanup steps live in [Chat History Cleanup](../../wiki/troubleshooting/chat-history-cleanup.en-US.md).

## Storage Role

Frontend sidebar chat titles and message details come from:

- `src/routes/chats.py`
- `src/storage/json_storage.py`

Default configuration:

```yaml
mode: json

json:
  base_path: data/chats
```

When the backend starts from the `atri` directory, the usual path is:

```text
data/chats/default/{character_id}/index.json
data/chats/default/{character_id}/sessions/{chat_id}.json
```

## File Responsibilities

| File | Responsibility |
| --- | --- |
| `index.json` | Chat list index with title, created time, updated time, and message count. |
| `sessions/{chat_id}.json` | Complete message array for one chat session. |

`index.json` is the frontend list entry point. Orphaned session files are not automatically shown in the sidebar.

## Current User Dimension

In local mode, `default` is the default user ID:

```text
data/chats/default/
```

When authentication is enabled, storage should use authenticated user identity as the isolation dimension. Any user-isolation change should be checked with both Auth and Storage design.

## Delete Semantics

When the frontend deletes a chat, the backend should:

1. remove the entry from `index.json`;
2. delete `sessions/{chat_id}.json`.

Manual cleanup should preserve the same consistency. Otherwise, the index may point to a missing session, or a session may remain on disk but become invisible to the frontend.

## Working Directory Constraint

`data/chats` is a relative path. If the backend starts from a different working directory, the path resolves relative to that directory.

When unsure, check:

- the backend startup working directory;
- `config/storage_config.yaml`;
- storage initialization logs.

## Related Documents

- [Chat History Cleanup](../../wiki/troubleshooting/chat-history-cleanup.en-US.md)
- [MemoryManager Character Memory Archive](../memory/chat-history-archive.en-US.md)
