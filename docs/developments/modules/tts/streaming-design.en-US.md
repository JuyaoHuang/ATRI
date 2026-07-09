---
status: active
owner: tts
created: 2026-07-09
updated: 2026-07-09
source: docs/developments/modules/tts/streaming-design.zh-CN.md
related_code:
  - src/tts/sentence_divider.py
  - src/tts/segment_manager.py
  - src/routes/chat_ws.py
  - frontend/src/utils/websocket.ts
  - frontend/src/composables/useWebSocket.ts
  - frontend/src/composables/useAudioPlayer.ts
---

# TTS Segmented Streaming Design

This document summarizes the long-term design for application-level segmented TTS streaming. The Chinese design remains the canonical detailed version: [streaming-design.zh-CN.md](streaming-design.zh-CN.md).

## Positioning

TTS is a downstream consumer of LLM text output. It should not block other consumers such as the frontend text stream, translation, or future modules.

The first version uses application-level sentence segmentation:

```text
LLM text response
  -> sentence divider
  -> TTSSegmentManager
  -> existing TTSService.synthesize()
  -> WebSocket audio segment events
  -> frontend generation + sequence playback queue
```

This version does not require every Provider to implement native `synthesize_stream()`.

## Explicit Non-Goals

The first version does not introduce:

- `heard_response`;
- Provider-native streaming synthesis;
- audio generation directly from partial LLM tokens;
- Provider-level cancellation for already-started REST synthesis requests.

## Why Application-Level Segmentation

The existing TTS providers already support complete text to complete audio. Reusing `TTSService.synthesize()` gives a lower-risk streaming experience:

- providers stay compatible;
- existing REST manual playback stays unchanged;
- streaming can be controlled at the WebSocket/application layer;
- ordered delivery and interruption logic are centralized.

The tradeoff is that each segment is still synthesized as a complete small audio file.

## Sentence Divider

The sentence divider is responsible for:

- detecting sentence boundaries;
- avoiding tiny segments where possible;
- optionally enabling faster first response;
- supporting Chinese and English punctuation.

The divider should be deterministic enough for tests and should not make Provider-specific assumptions.

## Segment Manager

`TTSSegmentManager` is responsible for:

- assigning `generation_id`;
- assigning `sequence`;
- synthesizing sentence segments through `TTSService.synthesize()`;
- limiting concurrency;
- preserving ordered delivery;
- dropping stale work when a newer generation supersedes the old one.

It should coordinate synthesis without changing Provider interfaces.

## WebSocket Audio Events

The backend sends audio events over the existing chat WebSocket.

Expected event types:

| Event | Meaning |
| --- | --- |
| `output:audio:segment` | One synthesized audio segment is ready. |
| `output:audio:complete` | All segments for the generation are complete. |
| `output:audio:error` | Segment synthesis failed. |

Events should include enough metadata for frontend ordering:

- `generation_id`
- `sequence`
- segment identifier
- audio payload or URL-compatible payload format

## Interruption and Stale Generations

When VAD interruption or a new generation starts, old TTS work should no longer be allowed to affect playback.

The system should:

- stop frontend playback for the interrupted generation;
- discard old-generation audio segments;
- cancel manager-side pending work where possible;
- tolerate already-started Provider synthesis finishing late.

The frontend must treat `generation_id` as the primary stale-result guard.

## Frontend Playback Queue

The frontend audio player should maintain a queue by:

- `generation_id`;
- `sequence`.

Playback should be ordered even if synthesis finishes out of order. When a new generation starts or an interrupt arrives, stale segments must be ignored.

When streaming TTS is enabled, the frontend should not also trigger the old REST auto-play after `chat:complete`. Manual playback of historical messages should continue to use REST TTS.

## Compatibility

When streaming is disabled:

- existing REST TTS behavior remains unchanged;
- `POST /api/tts/synthesize` remains the manual playback path;
- Provider configuration and write-back rules remain unchanged.

## Related Documents

- [TTS Configuration and Runtime Boundaries](config.en-US.md)
- [TTS Configuration Guide](../../../configs/EN/TTS-configuration.md)
- [Chinese canonical design](streaming-design.zh-CN.md)
