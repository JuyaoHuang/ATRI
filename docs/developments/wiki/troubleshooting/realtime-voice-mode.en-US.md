---
status: active
owner: vad
created: 2026-07-09
updated: 2026-07-09
source: docs/configs/EN/realtime-voice-mode.md
related_code:
  - src/routes/chat_ws.py
  - src/vad/
  - src/asr/
  - frontend/src/
---

# Realtime Voice Mode Troubleshooting

This is a GitHub Wiki pre-publish troubleshooting note for realtime voice mode. User-facing usage and recommended configuration remain in [Realtime Voice Mode Guide](../../../configs/EN/realtime-voice-mode.md).

## Confirm You Are Inspecting the Business WebSocket

The business WebSocket is:

```text
/ws
```

If DevTools shows:

```text
ws://localhost:5200/?token=...
```

that is usually the Vite HMR channel, not the chat business WebSocket.

In Chrome DevTools, inspect:

```text
Network -> WS -> /ws -> Messages
```

## Expected Message Order

After enabling realtime voice mode and speaking one sentence, you should usually see:

```text
input:audio:chunk
control:listen-state
control:interrupt
output:asr:transcript
output:chat:chunk
```

If you speak while the AI is responding, you should also see:

```text
output:chat:interrupted
```

## ASR Auto-Chat Does Not Happen

Check `config/asr_config.yaml`:

```yaml
asr_model: sherpa_onnx_asr
```

If the current value is:

```yaml
asr_model: web_speech_api
```

this is an expected limitation. `web_speech_api` runs in the browser, so the backend cannot use it for VAD-triggered automatic ASR.

## Current Reply Is Not Interrupted

When the user starts speaking, you should see:

```text
control:interrupt
```

If the AI is streaming text, the old `generation_id` should not continue as a normal complete reply. Check in this order:

1. Confirm the realtime voice button is enabled.
2. Confirm the browser is sending `input:audio:chunk`.
3. Confirm the backend keeps returning `control:listen-state`.
4. Lower VAD speech-start thresholds or check microphone permissions.

## Speech Ends Too Quickly

Silero's default silence end time is roughly:

```text
required_misses = 24
24 * 32 ms = 768 ms
```

If continuous speech is split too aggressively, increase:

```yaml
silero_vad:
  required_misses: 30
```

## Too Many False Triggers

Start by increasing:

```yaml
silero_vad:
  prob_threshold: 0.5
  db_threshold: 65
```

You can also increase `required_hits` to make speech-start detection more conservative.

## ScriptProcessorNode Warning

A browser console warning about `ScriptProcessorNode` does not mean the feature failed.

The current frontend capture path may still use that API. Migrating to `AudioWorklet` is a later optimization, not a requirement for the realtime voice MVP.

## Current Limitations

- TTS may still use REST complete audio unless the later segmented streaming path is enabled.
- VAD interruption stops old TTS playback and discards later TTS results from the old generation.
- Already-sent REST TTS API requests are not cancelled at the Provider level.
- `web_speech_api` cannot be used for backend VAD-triggered automatic ASR.
- Current realtime audio payload uses JSON float arrays; binary frames can be considered later.

## Related Documents

- [Realtime Voice Mode Guide](../../../configs/EN/realtime-voice-mode.md)
- [VAD Configuration Guide](../../../configs/EN/VAD-configuration.md)
- [VAD Realtime Interruption Development Log](../../features/2026-06-vad-realtime-interrupt/dev-log.zh-CN.md)
