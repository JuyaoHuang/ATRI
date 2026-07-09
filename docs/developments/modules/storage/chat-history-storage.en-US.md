---
status: active
owner: storage
created: 2026-07-09
updated: 2026-07-09
source: docs/configs/EN/chat-history-storage-batch-deletion.md
related_code:
  - src/routes/chats.py
  - src/routes/chat_ws.py
  - src/storage/json_storage.py
  - src/storage/interface.py
  - config/storage_config.yaml
---

# Chat History Storage Structure

This document captures the development-side storage structure for user-visible chat history. Operational cleanup steps live in [Chat History Cleanup](../../wiki/troubleshooting/chat-history-cleanup.en-US.md).

## Storage Role

Frontend sidebar titles and chat detail views come from backend APIs, not direct browser access to disk files:

- `src/routes/chats.py`
- `src/storage/json_storage.py`

Default configuration:

```yaml
mode: json

json:
  base_path: data/chats
```

When the backend starts from the `atri` directory, the usual paths are:

```text
data/chats/{user_id}/{character_id}/index.json
data/chats/{user_id}/{character_id}/sessions/{chat_id}.json
```

## File Responsibilities

| File | Responsibility |
| --- | --- |
| `index.json` | Chat list index with title, creation time, update time, and message count. |
| `sessions/{chat_id}.json` | Message container for one chat, currently shaped as `{"messages": [...]}`. |

`index.json` is the frontend list entry point. Orphaned session files are not automatically shown in the sidebar.

## `index.json` Shape

Current index shape:

```json
{
  "chats": [
    {
      "id": "20260709_ab12cd34",
      "title": "Chat title",
      "character_id": "atri",
      "created_at": "2026-07-09T12:34:56+00:00",
      "updated_at": "2026-07-09T12:35:10+00:00",
      "message_count": 2
    }
  ]
}
```

`JSONChatStorage.create_chat()` creates both the index entry and an empty session file.

## `sessions/{chat_id}.json` Shape

Current session shape:

```json
{
  "messages": [
    {
      "role": "human",
      "content": "hello",
      "timestamp": "2026-07-09T12:35:01+00:00",
      "name": "default"
    },
    {
      "role": "ai",
      "content": "hello",
      "timestamp": "2026-07-09T12:35:03+00:00",
      "name": "atri",
      "generation_id": "gen_123",
      "interrupted": false
    }
  ]
}
```

Message metadata currently preserves these fields:

- `generation_id`
- `interrupted`
- `interrupt_reason`

`JSONChatStorage` drops other unknown metadata keys so session files do not become an unbounded pass-through container.

## User Dimension

When authentication is disabled, `get_request_user_id()` and `get_websocket_user_id()` fall back to:

```text
default
```

So local paths usually become:

```text
data/chats/default/{character_id}/
```

When authentication is enabled, storage uses the authenticated user as the isolation dimension. Any user-isolation change should be checked against both Auth and Storage designs.

## Write Paths

Current message writes mainly enter through two paths:

1. REST `POST /api/chats` creates the chat index and empty session.
2. WebSocket `src/routes/chat_ws.py` appends human/AI messages when a streamed reply completes or is interrupted.

`append_message_for_user()`:

1. reads the session file;
2. appends one message;
3. atomically writes the session file back;
4. updates `message_count` and `updated_at` in `index.json`.

## Delete Semantics

When the frontend deletes one chat, the backend should:

1. remove the entry from `index.json`;
2. delete `sessions/{chat_id}.json`.

Manual cleanup should preserve the same consistency. Otherwise, the index may point to a missing session, or a session may remain on disk but be invisible to the frontend.

Deleting a chat does not automatically clean Memory module archives under `data/characters/...` or mem0 long-term memory. That is a separate data plane.

## Working Directory Constraint

`data/chats` is a relative path. If the backend starts outside the repository root, the path resolves relative to that startup directory.

When unsure, check:

- backend startup working directory;
- `config/storage_config.yaml`;
- storage initialization logs.

## Related Documents

- [Chat History Cleanup](../../wiki/troubleshooting/chat-history-cleanup.en-US.md)
- [MemoryManager Chat Archive](../memory/chat-history-archive.en-US.md)
- [Character Storage Design](character-storage.zh-CN.md)
