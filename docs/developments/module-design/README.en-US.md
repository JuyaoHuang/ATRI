---
status: superseded
owner: docs
created: 2026-07-09
updated: 2026-07-09
---

# Legacy Module Design Notes

This directory keeps older long-form design drafts and discussion documents.

Their current role is:

- historical design source
- migration reference material
- temporary legacy entry points before full cleanup

They are **not** the authoritative entry points for the current implementation.

## Current Authoritative Locations

Read these directories first:

| Type | Directory |
| --- | --- |
| long-term module design | `../modules/` |
| stable interface protocols | `../api/` |
| project-level architecture | `../architecture/` |
| feature process records | `../features/` |
| wiki pre-publish drafts | `../wiki/` |

## Usage Rule

When reading files under this directory:

1. Treat the current codebase as ground truth first.
2. Treat the corresponding documents under `docs/developments/modules/` as the formal design source next.
3. Use files here only as historical intent, alternative design discussion, or migration material.

## Current Migration Status

At this stage, these legacy topics already have corresponding destinations in the new structure:

- LLM calling -> `../modules/llm/`
- TTS -> `../modules/tts/`
- ASR -> `../modules/asr/`
- VAD -> `../modules/vad/`
- Frontend -> `../modules/frontend/`
- Live2D -> `../modules/live2d/`
- Memory -> `../modules/memory/`
- Storage / route structure -> `../modules/storage/` and `../modules/routes/`
