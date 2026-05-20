# Chat History Storage and Batch Deletion Guide

This document describes the storage locations of character chat history in the backend and how to batch delete history records.

The current project has two types of easily confused "history":

- Frontend chat list history: Read/written by `/api/chats`, determines which chat titles and messages are visible in the sidebar.
- MemoryManager character memory archive: Read/written by `src/memory/chat_history.py`, used for short-term memory recovery, compression, and long-term memory writing.

## Frontend Chat List History

The chat titles and message details in the frontend sidebar come from `src/routes/chats.py` and `src/storage/json_storage.py`.

Default configuration is in `config/storage_config.yaml`:

```yaml
mode: json

json:
  base_path: data/chats
```

When the backend is started from the `atri` directory as usual, the actual path is:

```text
atri/data/chats/default/{character_id}/index.json
atri/data/chats/default/{character_id}/sessions/{chat_id}.json
```

Description:

- `default` is the hardcoded `user_id` in the current Phase 5.
- `{character_id}` is the character ID, e.g., `atri` or a custom character ID.
- `index.json` stores chat list metadata, including `id`, `title`, `created_at`, `updated_at`, `message_count`.
- `sessions/{chat_id}.json` stores the message array for that chat, in the format `{"messages": [...]}`.
- When the frontend deletes a chat, it calls `POST /api/chats/{chat_id}/delete`, and the backend simultaneously removes the index entry from `index.json` and the corresponding `sessions/{chat_id}.json`.

If the backend is started from a different working directory, the relative path `data/chats` will be resolved relative to the startup directory. If unsure, check the working directory of the backend startup command.

## MemoryManager Character Memory Archive

The chat agent also writes each conversation turn to the MemoryManager's character directory. Default configuration is in `config/memory_config.yaml`:

```yaml
storage:
  characters_dir: ./data/characters
```

The usual path is:

```text
atri/data/characters/{character_id}/short_term_memory.json
atri/data/characters/{character_id}/sessions/{session_id}.json
```

Description:

- `sessions/{session_id}.json` is an append-only archive written by `src/memory/chat_history.py`.
- `short_term_memory.json` stores the current character's short-term memory state, including compressed blocks and recent turns.
- Deleting frontend chat list history does not automatically clean up these MemoryManager files.
- If mem0 long-term memory is enabled, local mode may also write to `atri/data/qdrant`; SaaS mode writes to the external mem0 service. The current repository does not have a unified long-term memory batch deletion interface.

## Preparation Before Deletion

Before batch deleting files, it is recommended to stop the backend service first. Deleting files while the backend is running may conflict with the `.tmp` atomic replacement process being written.

It is recommended to backup first:

```powershell
Compress-Archive -Path .\data\chats, .\data\characters -DestinationPath .\data-history-backup.zip -Force
```

The above command should be executed in the `atri` directory.

## Delete Frontend Chat History for a Single Character

Delete all chats visible in the frontend sidebar for a specific character:

```powershell
Remove-Item -LiteralPath ".\data\chats\default\CHARACTER_ID" -Recurse -Force
```

Replace `CHARACTER_ID` with the character ID.

After deletion, restart the backend or refresh the frontend chat list.

## Delete All Frontend Chat History

Delete all frontend chat history for the current default user:

```powershell
Remove-Item -LiteralPath ".\data\chats\default" -Recurse -Force
```

If you only want to clear all JSON chat data, you can also delete the entire `data/chats`:

```powershell
Remove-Item -LiteralPath ".\data\chats" -Recurse -Force
```

The next time a chat is created, the backend will recreate the directory and index files.

## Delete Character Memory Archive

Only delete a character's session archive, preserving short-term memory state:

```powershell
Remove-Item -LiteralPath ".\data\characters\CHARACTER_ID\sessions" -Recurse -Force
```

Also reset the character's short-term memory:

```powershell
Remove-Item -LiteralPath ".\data\characters\CHARACTER_ID\short_term_memory.json" -Force
```

Completely delete a character's MemoryManager local memory files:

```powershell
Remove-Item -LiteralPath ".\data\characters\CHARACTER_ID" -Recurse -Force
```

Note: This does not delete the character Persona file. The character card file is at `prompts/persona/{character_id}.md`, maintained by the character management feature.

## Batch Delete Frontend Chats by Title

The current backend does not have a "batch delete by title" REST API. You can modify `index.json` and delete matching session files via PowerShell after stopping the backend.

The following example deletes chats with titles exactly equal to `TITLE_TO_DELETE` under a specified character:

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

For fuzzy matching by title, change the match condition to:

```powershell
Where-Object { $_.title -like "*keyword*" }
```

## Post-Deletion Verification

Check the remaining number of chats for a character:

```powershell
$index = Get-Content -Raw ".\data\chats\default\CHARACTER_ID\index.json" | ConvertFrom-Json
$index.chats.Count
```

Check if there are any remaining session files:

```powershell
Get-ChildItem ".\data\chats\default\CHARACTER_ID\sessions" -Filter "*.json"
```

If you manually deleted `index.json` but kept the `sessions` files, the frontend will no longer display these orphaned sessions. The backend reads by list based on `index.json`.
