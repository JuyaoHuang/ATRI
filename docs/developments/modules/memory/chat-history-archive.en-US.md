---
status: active
owner: memory
created: 2026-07-09
updated: 2026-07-09
source: docs/configs/EN/chat-history-storage-batch-deletion.md
related_code:
  - src/memory/chat_history.py
  - src/memory/
  - config/memory_config.yaml
---

# MemoryManager Character Memory Archive

This document captures the MemoryManager character memory archive structure. Operational cleanup steps live in [Chat History Cleanup](../../wiki/troubleshooting/chat-history-cleanup.en-US.md).

## Difference From Frontend Chat History

The project has two types of "history":

| Type | Main purpose | Default path |
| --- | --- | --- |
| Frontend chat list history | Sidebar chat list and message details | `data/chats/default/{character_id}/` |
| MemoryManager character memory archive | Short-term memory recovery, compression, long-term memory writes | `data/characters/{character_id}/` |

Deleting frontend chat list history does not automatically clean MemoryManager files.

## Default Path

Default configuration:

```yaml
storage:
  characters_dir: ./data/characters
```

Usual paths:

```text
data/characters/{character_id}/short_term_memory.json
data/characters/{character_id}/sessions/{session_id}.json
```

## File Responsibilities

| File | Responsibility |
| --- | --- |
| `sessions/{session_id}.json` | Append-only conversation archive written by `src/memory/chat_history.py`. |
| `short_term_memory.json` | Current character short-term memory state, including compressed blocks and recent turns. |

`short_term_memory.json` can be rebuilt from chat archives only if the recovery logic respects turn coverage and compression block boundaries.

## Long-Term Memory Boundary

If mem0 is enabled:

- local mode may write to `data/qdrant`;
- SaaS mode writes to an external mem0 service.

The current repository does not provide a unified long-term memory batch deletion API. Deleting `data/characters` is not enough to clean all long-term memory.

## Maintenance Principles

- Stop the backend before deleting files.
- Deleting files at runtime may conflict with `.tmp` atomic replacement.
- Deleting `sessions/` affects archives but does not reset short-term memory.
- Deleting `short_term_memory.json` forces later rebuild or reinitialization.

## Related Documents

- [Chat History Cleanup](../../wiki/troubleshooting/chat-history-cleanup.en-US.md)
- [Chat History Storage Structure](../storage/chat-history-storage.en-US.md)
- `docs/developments/module-design/EN/memory-system-design.md`
