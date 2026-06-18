# VAD Configuration Guide

> **Applicable Scope**: VAD realtime voice interruption  
> **Configuration File**: `config/vad_config.yaml`  
> **Related Configuration**: `config/asr_config.yaml`  
> **Last Updated**: 2026-06-19

This document describes the VAD (Voice Activity Detection) configuration, Provider selection, realtime interruption pipeline, and common troubleshooting steps.

---

## 1. Quick Start

The current development configuration uses `silero_vad`:

```yaml
enabled: true
vad_model: silero_vad
sample_rate: 16000
pre_buffer_ms: 500

silero_vad:
  sample_rate: 16000
  prob_threshold: 0.4
  db_threshold: 60
  required_hits: 3
  required_misses: 24
  smoothing_window: 5
```

To verify the WebSocket pipeline and state machine without loading a real model, switch to `fake`:

```yaml
enabled: true
vad_model: fake

fake:
  speech_threshold: 0.05
  required_hits: 2
  required_misses: 10
```

Restart the backend service after editing YAML.

---

## 2. Configuration Loading Method

The root configuration file `config.yaml` references VAD configuration through:

```yaml
vad_config: config/vad_config.yaml
```

After loading, the VAD module reads runtime `config["vad"]`:

```text
config/vad_config.yaml -> runtime config["vad"]
```

---

## 3. Top-Level Configuration Structure

```yaml
enabled: true
vad_model: silero_vad
sample_rate: 16000
pre_buffer_ms: 500

fake:
  speech_threshold: 0.05
  required_hits: 2
  required_misses: 10

silero_vad:
  sample_rate: 16000
  prob_threshold: 0.4
  db_threshold: 60
  required_hits: 3
  required_misses: 24
  smoothing_window: 5
```

### Top-Level Fields

| Field | Type | Description |
| --- | --- | --- |
| `enabled` | boolean | Enables backend VAD processing. When disabled, realtime audio chunks do not trigger interruption or ASR auto-submit. |
| `vad_model` | string | Current VAD Provider. Available values: `fake`, `silero_vad`. |
| `sample_rate` | number | Backend VAD target sample rate. The current frontend realtime path resamples to `16000`. |
| `pre_buffer_ms` | number | Audio kept before `speech_start`, used to avoid ASR dropping the beginning of a sentence. |

---

## 4. Provider Configuration

### 4.1 `fake`

`fake` is a development and test Provider. It does not load a model and only checks the maximum absolute amplitude of the audio.

```yaml
vad_model: fake
fake:
  speech_threshold: 0.05
  required_hits: 2
  required_misses: 10
```

| Field | Description |
| --- | --- |
| `speech_threshold` | If the max absolute amplitude of one audio chunk reaches this value, it counts as one speech hit. |
| `required_hits` | Consecutive hits required before emitting `speech_start`. |
| `required_misses` | Consecutive misses during speech required before emitting `speech_end`. |

The debounce unit for `fake` is the frontend chunk sent to the backend, not Silero's 32 ms internal window. Use it for integration and tests, not as the real user-facing VAD model.

### 4.2 `silero_vad`

`silero_vad` is the current real VAD Provider. It lazily loads the model from the `silero-vad` Python package and runs on CPU.

```yaml
vad_model: silero_vad
silero_vad:
  sample_rate: 16000
  prob_threshold: 0.4
  db_threshold: 60
  required_hits: 3
  required_misses: 24
  smoothing_window: 5
```

| Field | Description |
| --- | --- |
| `sample_rate` | Silero inference sample rate. Current value is `16000`. |
| `prob_threshold` | Speech probability threshold from the Silero model. |
| `db_threshold` | Volume gate used to reduce false triggers from low-level noise. |
| `required_hits` | Consecutive Silero windows required before emitting `speech_start`. |
| `required_misses` | Consecutive missed windows during speech required before emitting `speech_end`. |
| `smoothing_window` | Number of recent windows used to smooth probability and dB values. |

At 16 kHz, Silero uses an internal 512-sample window:

```text
Silero internal window = 512 samples / 16000 Hz = 32 ms
speech_start debounce delay = required_hits * 32 ms
speech_end silence delay = required_misses * 32 ms
```

Current defaults mean:

```text
speech_start debounce delay = 3 * 32 ms = 96 ms
speech_end silence delay = 24 * 32 ms = 768 ms
```

Actual perceived delay also includes frontend chunking, network transmission, smoothing, and ASR time.

---

## 5. Relationship With ASR

VAD only decides "the user started speaking" and "the user finished speaking". Transcription after `speech_end` is handled by the ASR Provider.

Realtime voice auto-chat requires a backend-callable ASR Provider, for example:

```yaml
asr_model: sherpa_onnx_asr
```

`web_speech_api` is browser-side ASR. The backend cannot call it for `speech_end -> ASR -> auto chat`. Therefore:

- With `web_speech_api`, VAD interruption still works.
- With `web_speech_api`, the backend does not auto-transcribe or auto-submit chat after `speech_end`.
- Full realtime voice flow requires a backend Provider such as `sherpa_onnx_asr`, `faster_whisper`, `whisper_cpp`, or `openai_whisper`.

Recommended local validation:

```yaml
asr_model: sherpa_onnx_asr
persistent_provider: true
preload_provider: false
```

Model directory example:

```text
models/asr-models/sherpa-onnx-sense-voice/
```

---

## 6. Runtime Pipeline

```text
Frontend realtime VAD button enabled
  -> Frontend captures microphone
  -> Resample to 16 kHz / mono / PCM float array
  -> Send input:audio:chunk over WebSocket
  -> Backend VAD Provider detects speech_start / speech_end
  -> speech_start: backend sends control:interrupt and invalidates old generation
  -> speech_end: backend submits audio to ASR
  -> ASR succeeds: backend sends output:asr:transcript
  -> Backend starts the next chat turn automatically
```

TTS still uses the REST complete-audio pipeline. VAD interruption stops frontend playback and invalidates old-generation TTS results, but the first version does not move TTS audio to WebSocket streaming.

---

## 7. Common Issues

### Realtime voice says backend ASR is unsupported

The current `asr_model` is likely `web_speech_api`.

Switch to a backend ASR Provider such as `sherpa_onnx_asr`, then confirm model paths and dependencies are available.

### Continuous speech is split into multiple utterances

This is mainly controlled by `required_misses`. The current Silero default is `24`, so the theoretical silence delay is about `768 ms`.

If continuous speech is split too aggressively, increase:

```yaml
silero_vad:
  required_misses: 30
```

### Background noise triggers speech

First increase `prob_threshold` or `db_threshold`:

```yaml
silero_vad:
  prob_threshold: 0.5
  db_threshold: 65
```

If `speech_start` is still too sensitive, increase `required_hits`.

### First transcription is slow

Local ASR Providers have model cold-start cost. Keep:

```yaml
persistent_provider: true
```

To load the current ASR Provider when the service starts, set:

```yaml
preload_provider: true
```

Do not enable preload by default on low-memory servers.

---

## 8. Self-Check

For browser integration, open:

```text
F12 -> Network -> WS -> /ws -> Messages
```

The complete flow should include a sequence like:

```text
input:audio:chunk
control:listen-state
control:interrupt
output:asr:transcript
output:chat:chunk
```

Backend checks:

```powershell
uv run pytest tests/vad tests/routes/test_chat_ws.py tests/routes/test_asr.py -q
```

Frontend checks:

```powershell
cd frontend
npm run type-check
npm run lint
npm run build
```

