---
status: active
owner: memory
created: 2026-07-09
updated: 2026-07-09
source: docs/configs/EN/chat-history-storage-batch-deletion.md
related_code:
  - src/memory/chat_history.py
  - src/memory/manager.py
  - src/routes/data.py
  - config/memory_config.yaml
---

# Memory Archive Design

This document captures the archive structure used by `MemoryManager`. Operational cleanup steps live in [Chat History Cleanup](../../wiki/troubleshooting/chat-history-cleanup.en-US.md).

## Difference From Chat Storage

The project has two kinds of "history":

| Type | Main purpose | Default path |
| --- | --- | --- |
| Chat storage | Frontend sidebar, chat detail API, WebSocket persistence | `data/chats/{user_id}/{character_id}/` |
| Memory archive | Short-term memory recovery, L3/L4 replay, system audit | `data/characters/{user_id}/{character_id}/chats/{chat_id}/` |

The frontend does not read memory archive files directly. User-visible history comes from APIs backed by `src/routes/chats.py` and `src/storage/json_storage.py`.

## Current Path and Compatibility Migration

Current effective path:

```text
data/characters/{user_id}/{character_id}/chats/{chat_id}/sessions/{session_id}.json
```

Path source:

```yaml
storage:
  characters_dir: ./data/characters
```

The current code still recognizes two old paths as migration sources:

```text
data/characters/{user_id}/{character_id}/sessions/{session_id}.json
data/characters/{character_id}/sessions/{session_id}.json
```

`resolve_user_character_dir()` and `resolve_user_character_chat_dir()` migrate old files into the chat-level directory when first accessed.

## File Format

Each archive file is a JSON array maintained by `ChatHistoryWriter`:

```json
[
  {
    "role": "metadata",
    "timestamp": "2026-07-09T12:34:56Z",
    "session_id": "2026-07-09_ab12cd34",
    "character": "atri"
  },
  {
    "role": "human",
    "timestamp": "2026-07-09T12:35:01Z",
    "content": "cleaned user input",
    "name": "user"
  },
  {
    "role": "ai",
    "timestamp": "2026-07-09T12:35:03Z",
    "content": "AI reply",
    "name": "Atri"
  }
]
```

Key fields:

| Field | Meaning |
| --- | --- |
| `metadata` row | Appears once and records `session_id` and `character`. |
| `human.content` | Cleaned text written by `MemoryManager`. |
| `human.raw_input` | Present only when the caller explicitly preserves raw input. |
| `ai.generation_id` | Marks one WebSocket generation. |
| `ai.interrupted` / `interrupt_reason` | Marks a partial reply interrupted by realtime voice. |
| `system.content` | System-level notes such as LLM call failures. |

Archive files are append-oriented, but the implementation still writes a complete JSON array through an atomic replace.

## Recovery Semantics

For `MemoryManager`, the archive is the recovery source of truth.

`resume_session(session_id)` follows this order:

1. Load `short_term_memory.json`.
2. Count valid `(human, ai)` pairs in the archive.
3. Incrementally replay missing turns when short-term state is behind.
4. Rebuild from the archive when short-term state is damaged.

`ChatHistoryWriter.iter_messages()` can recover a parseable prefix when a file tail is damaged, then logs a warning.

## Short-Term Cleanup Boundary

`DELETE /api/data/characters/{character_id}/chats/{chat_id}/short-term-memory` currently:

- deletes `short_term_memory.json`;
- deletes the matching temporary file;
- resets the in-process short-term memory cache.

It does not delete archive files. After cleanup, later context can still rebuild from the archive.

## Long-Term Memory Boundary

If mem0 is enabled:

- local mode may write to `data/qdrant`;
- SaaS mode writes to an external mem0 service.

The archive is not the long-term memory store. Deleting `data/characters/.../sessions/` does not delete mem0 facts, and clearing long-term memory does not automatically remove archive files.

## Maintenance Principles

- Stop the backend before deleting files.
- Runtime deletion can race with `.tmp` atomic replacement.
- Deleting `sessions/` affects only memory archive, not chat storage or long-term memory.
- Deleting `short_term_memory.json` forces later rebuild or reinitialization.

## Related Documents

- [Chat History Cleanup](../../wiki/troubleshooting/chat-history-cleanup.en-US.md)
- [Chat History Storage Structure](../storage/chat-history-storage.en-US.md)
- [Short-Term Memory Design](short-term-memory.zh-CN.md)
