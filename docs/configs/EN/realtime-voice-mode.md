# Realtime Voice Mode Guide

> **Applicable Scope**: VAD button, realtime voice interruption, ASR auto-submit  
> **Entry Point**: Realtime voice toggle next to the current microphone button in the chat input box  
> **Last Updated**: 2026-06-19

This document explains how to use realtime voice mode, how to verify the pipeline, and how to troubleshoot common issues.

---

## 1. Feature Boundary

Realtime voice mode is not the traditional button-based ASR flow. Both flows exist:

| Feature | Entry Point | Behavior |
| --- | --- | --- |
| Button ASR | Original microphone button | Records one complete audio clip, transcribes it, then fills the input box. |
| Realtime voice mode | New VAD button | Continuously sends microphone audio while the backend detects speech start and speech end. |

When realtime voice mode is enabled, user speech triggers:

1. Backend sends `control:interrupt`.
2. Frontend stops current TTS playback and clears the playback queue.
3. Backend cancels the old LLM generation.
4. After the user stops speaking, backend submits audio to ASR.
5. After ASR succeeds, backend starts the next chat turn automatically.

---

## 2. Requirements Before Use

The realtime voice button is clickable only when:

1. ASR module is enabled.
2. A chat character is selected.
3. A valid chat window is open.
4. The current chat is not a `draft_` temporary chat.
5. The business WebSocket is connected.

If the button is disabled, hover it to see the reason.

---

## 3. Recommended Configuration

For the full realtime voice loop:

```yaml
# config/vad_config.yaml
enabled: true
vad_model: silero_vad
```

```yaml
# config/asr_config.yaml
asr_model: sherpa_onnx_asr
persistent_provider: true
preload_provider: false
```

If `asr_model` is `web_speech_api`, realtime interruption still works, but backend ASR auto-submit and auto-chat after `speech_end` do not work.

---

## 4. Manual Integration Steps

1. Start the backend and frontend.
2. Open the chat page.
3. Select a character, such as `atri`.
4. Create or open a normal chat window.
5. Open browser DevTools.
6. Go to `Network -> WS -> /ws -> Messages`.
7. Let the character produce one reply first.
8. Click the realtime voice button.
9. Speak one sentence into the microphone.
10. Wait for backend ASR and the next chat reply.

In a normal run, the WS messages should include:

```text
input:audio:chunk
control:listen-state
control:interrupt
output:asr:transcript
output:chat:chunk
```

If you interrupt while the AI is streaming text, you should also see:

```text
output:chat:interrupted
```

---

## 5. How To Confirm Success

### VAD realtime audio works

Frontend continuously sends:

```text
input:audio:chunk
```

Backend continuously returns:

```text
control:listen-state
```

### Interruption works

When the user starts speaking, you see:

```text
control:interrupt
```

If the AI was streaming text, the old `generation_id` should not later emit `output:chat:complete`.

### ASR auto-submit works

After the user stops speaking, you see:

```text
output:asr:transcript
output:chat:chunk
```

This proves the flow is:

```text
VAD -> ASR -> backend auto chat
```

It is not traditional button ASR and not manual text input.

### Interrupted reply handling works

If the AI is interrupted while streaming, you should see:

```text
output:chat:interrupted
```

The partial reply is shown in the frontend and written to auditable `chat_history`, but it is not treated as a normal complete reply in short-term memory.

---

## 6. DevTools Location

The business WebSocket is:

```text
/ws
```

If you see:

```text
ws://localhost:5200/?token=...
```

that is the Vite HMR channel, not the business chat WebSocket.

In Chrome DevTools, open the single `/ws` connection and inspect the "Messages" panel. Messages are shown as a frame list.

---

## 7. Common Issues

### Button opens but ASR auto-chat does not happen

Check `config/asr_config.yaml`:

```yaml
asr_model: sherpa_onnx_asr
```

If it is:

```yaml
asr_model: web_speech_api
```

this is expected. `web_speech_api` can only transcribe in the browser, so the backend cannot use it for VAD-triggered ASR.

### Browser console shows a ScriptProcessorNode warning

This warning appears because the current frontend capture path uses `ScriptProcessorNode`. It does not mean the feature failed.

Migrating to `AudioWorklet` is a later optimization and is not required for the current realtime voice MVP.

### Speech ends too quickly

The current Silero theoretical silence delay is about `768 ms`:

```text
required_misses = 24
24 * 32 ms = 768 ms
```

If continuous speech is split, increase `config/vad_config.yaml`:

```yaml
silero_vad:
  required_misses: 30
```

### Too many false triggers

First increase:

```yaml
silero_vad:
  prob_threshold: 0.5
  db_threshold: 65
```

You can also increase `required_hits` to make speech start detection more conservative.

### Will button errors stack up?

No. A new error overwrites the previous one. The visible error is cleared automatically after 3 seconds.

---

## 8. Current Limitations

1. TTS still uses REST complete-audio responses, not WebSocket audio streaming.
2. VAD interruption stops old TTS playback and discards later TTS results from old generations.
3. Already-started REST TTS API requests are not cancelled at the Provider level.
4. `web_speech_api` cannot power backend VAD auto-ASR.
5. The current realtime audio payload is a JSON float array. Binary frames may be evaluated later.

