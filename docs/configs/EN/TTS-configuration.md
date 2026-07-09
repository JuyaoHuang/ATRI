# TTS Configuration Guide

> **Applicable Scope**: Phase 10 TTS Voice Output
> **Configuration File**: `atri/config/tts_config.yaml`
> **Settings Page**: `/settings/modules/speech` in `atri-webui`
> **Last Updated**: 2026-04-25

This document describes the TTS (Text-to-Speech) configuration structure, Provider selection, frontend settings page mapping, and common troubleshooting methods.

Development-side configuration boundaries, write-back rules, and runtime pipeline notes:

- [TTS Configuration and Runtime Boundaries](../../developments/modules/tts/config.en-US.md)
- [TTS Segmented Streaming Design](../../developments/modules/tts/streaming-design.zh-CN.md)

---

## 1. Quick Start

It is recommended to start with `edge_tts`. It does not require an API Key and is suitable for verifying the TTS main pipeline.

```yaml
tts_model: edge_tts
enabled: true
auto_play: true
show_player_on_home: false
volume: 1

edge_tts:
  voice: zh-CN-XiaoxiaoNeural
  rate: +0%
```

After starting, open the frontend:

```text
/settings/modules/speech
```

On this page you can:

- Enable or disable the TTS module
- Enable or disable automatic reading of AI replies
- Switch TTS Provider
- Adjust Provider parameters allowed to be modified by the frontend
- Test text-to-speech
- Control whether to show the playback control component on the `/` page

---

## 2. Configuration Loading Method

The root configuration file `atri/config.yaml` references the TTS configuration through the following entry:

```yaml
tts_config: config/tts_config.yaml
```

The backend `config_loader` loads it into the `tts` node of the runtime configuration:

```python
config["tts"]
```

Therefore, the TTS module actually reads:

```text
atri/config/tts_config.yaml -> runtime config["tts"]
```

---

## 3. Top-Level Configuration Structure

The current configuration uses the Open-LLM-VTuber style: `tts_model` specifies the current Provider, and Provider parameters are saved in a top-level block with the same name.

```yaml
tts_model: edge_tts
enabled: true
auto_play: true
show_player_on_home: false
volume: 1

edge_tts:
  voice: zh-CN-XiaoxiaoNeural
  rate: +0%

gpt_sovits_tts:
  api_url: http://127.0.0.1:9880/tts
  text_lang: zh
  ref_audio_path: ''
  prompt_lang: zh
  prompt_text: ''

siliconflow_tts:
  api_key: ${SILICONFLOW_API_KEY}
  default_model: FunAudioLLM/CosyVoice2-0.5B
  default_voice: FunAudioLLM/CosyVoice2-0.5B:claire
  stream: false

cosyvoice3_tts:
  client_url: http://127.0.0.1:50000/
  mode_checkbox_group: 预训练音色
  sft_dropdown: 中文女
  stream: false
  speed: 1.0
```

### Top-Level Fields

| Field | Type | Description |
| --- | --- | --- |
| `tts_model` | string | Name of the currently enabled TTS Provider. |
| `enabled` | boolean | Whether to enable the TTS module. When disabled, voice synthesis is not performed. |
| `auto_play` | boolean | Whether to automatically read aloud after AI reply is complete. |
| `show_player_on_home` | boolean | Whether to show the floating playback control component on the `/` page. |
| `volume` | number | Browser playback volume, typically ranges from `0.0` to `1.0`. |

Currently available `tts_model` options:

| Provider | Type | Description |
| --- | --- | --- |
| `edge_tts` | Cloud Service | Microsoft Edge neural voices, free, no API Key required. |
| `gpt_sovits_tts` | Local | GPT-SoVITS HTTP API, voice determined by reference audio and prompt. |
| `siliconflow_tts` | Cloud Service | SiliconFlow audio synthesis API. |
| `cosyvoice3_tts` | Local | Calls local CosyVoice3 Gradio WebUI. |

---

## 4. Provider Configuration

### 4.1 `edge_tts`

Edge TTS uses the `edge-tts` Python package to call Microsoft Edge neural voices.

```yaml
tts_model: edge_tts
edge_tts:
  voice: zh-CN-XiaoxiaoNeural
  rate: +0%
  pitch: +0Hz
  volume: +0%
  format: mp3
```

| Field | Frontend Writable | Description |
| --- | --- | --- |
| `voice` | Yes | Edge voice ID, e.g., `zh-CN-XiaoxiaoNeural`. |
| `rate` | Yes | Speech rate, e.g., `+10%`, `-10%`. |
| `pitch` | No | Pitch, e.g., `+10Hz`, `-10Hz`. |
| `volume` | No | Synthesis stage volume, e.g., `+0%`. |
| `format` | No | Output format. Currently defaults to `mp3`. |

View available voices:

```powershell
cd D:\Coding\GitHub_Resuorse\emotion-robot\atri
uv run edge-tts --list-voices
```

The frontend `Voice model` will fetch the Edge voice list from `/api/tts/voices?provider=edge_tts`.

### 4.2 `gpt_sovits_tts`

GPT-SoVITS is a local HTTP service. ATRI does not directly load models; it only calls the GPT-SoVITS server API.

Navigate to the GPT-SoVITS directory, then execute `runtime\python.exe api_v2.py` to start the gpt-sovits service.

```yaml
tts_model: gpt_sovits_tts
gpt_sovits_tts:
  api_url: http://127.0.0.1:9880/tts
  text_lang: zh
  ref_audio_path: D:/path/to/ref.wav
  prompt_lang: zh
  prompt_text: Reference audio corresponding text
  text_split_method: cut5
  batch_size: '1'
  media_type: wav
  streaming_mode: 'false'
  timeout_seconds: 120
```

| Field | Frontend Writable | Description |
| --- | --- | --- |
| `api_url` | No | GPT-SoVITS HTTP API address. |
| `text_lang` | No | Language of the text to be synthesized. |
| `ref_audio_path` | No | Reference audio path. Voice is primarily determined by this. |
| `prompt_lang` | No | Language of the reference audio prompt text. |
| `prompt_text` | No | Text corresponding to the reference audio. |
| `text_split_method` | No | Text splitting method, e.g., `cut5`. |
| `batch_size` | No | Batch size. |
| `media_type` | No | Returned audio format, commonly `wav`. |
| `streaming_mode` | No | GPT-SoVITS server-side streaming toggle. ATRI currently still returns complete audio. |
| `timeout_seconds` | No | HTTP request timeout. |

The frontend does not display GPT-SoVITS Provider parameters. To modify these fields, directly edit `config/tts_config.yaml`.

### 4.3 `siliconflow_tts`

SiliconFlow is a cloud audio synthesis Provider that requires an API Key.

```yaml
tts_model: siliconflow_tts
siliconflow_tts:
  api_key: ${SILICONFLOW_API_KEY}
  api_url: https://api.siliconflow.cn/v1/audio/speech
  default_model: FunAudioLLM/CosyVoice2-0.5B
  default_voice: FunAudioLLM/CosyVoice2-0.5B:claire
  sample_rate: 32000
  response_format: mp3
  stream: false
  speed: 1
  gain: 0
  timeout_seconds: 120
```

| Field | Frontend Writable | Description |
| --- | --- | --- |
| `api_key` | No | API Key. Must use environment variable placeholder. |
| `api_url` | No | SiliconFlow speech synthesis API address. |
| `default_model` | No | Default model. |
| `default_voice` | Yes | Default voice, e.g., `FunAudioLLM/CosyVoice2-0.5B:claire`. |
| `sample_rate` | No | Output sample rate. |
| `response_format` | No | Output format, commonly `mp3`, `wav`. |
| `stream` | Yes | Request server-side streaming generation. ATRI currently still returns complete audio. |
| `speed` | No | Speech rate multiplier. |
| `gain` | No | Gain. |
| `timeout_seconds` | No | Request timeout. |

Environment variable example:

```powershell
$env:SILICONFLOW_API_KEY = "YOUR_API_KEY"
```

Do not write real API Keys into `tts_config.yaml`.

### 4.4 `cosyvoice3_tts`

CosyVoice3 is a locally deployed Provider. ATRI currently calls the CosyVoice Gradio WebUI via `gradio-client`.

```yaml
tts_model: cosyvoice3_tts
cosyvoice3_tts:
  client_url: http://127.0.0.1:50000/
  mode_checkbox_group: 预训练音色
  sft_dropdown: 中文女
  prompt_text: ''
  prompt_wav_upload_url: https://github.com/gradio-app/gradio/raw/main/test/test_files/audio_sample.wav
  prompt_wav_record_url: https://github.com/gradio-app/gradio/raw/main/test/test_files/audio_sample.wav
  instruct_text: ''
  stream: false
  seed: 0
  speed: 1.0
  api_name: /generate_audio
```

| Field | Frontend Writable | Description |
| --- | --- | --- |
| `client_url` | No | CosyVoice Gradio WebUI address. |
| `mode_checkbox_group` | No | Inference mode, e.g., `预训练音色` (Pre-trained Voice), `3s极速复刻` (3s Quick Clone), `跨语种复刻` (Cross-lingual Clone). |
| `sft_dropdown` | No | Pre-trained voice/model dropdown value in the WebUI. Frontend read-only display. |
| `prompt_text` | No | Text corresponding to the reference audio. |
| `prompt_wav_upload_url` | No | Uploaded reference audio path or URL. |
| `prompt_wav_record_url` | No | Recorded reference audio path or URL. |
| `instruct_text` | No | Natural language control instructions. |
| `stream` | Yes | Request CosyVoice WebUI to use streaming inference. ATRI currently still returns complete audio. |
| `seed` | No | Random seed. |
| `speed` | Yes | Speech rate multiplier. |
| `api_name` | No | Gradio API name, defaults to `/generate_audio`. |

For more detailed instructions, see:

```text
docs/developments/modules/tts/cosyvoice3-provider.en-US.md
```

---

## 5. Frontend and Backend Write-Back Rules

The frontend settings page only allows writing to a few safe fields. The backend also filters protected fields in direct API calls.

| Provider | Allowed Write-Back Fields |
| --- | --- |
| `edge_tts` | `voice`, `rate` |
| `gpt_sovits_tts` | None |
| `siliconflow_tts` | `default_voice`, `stream` |
| `cosyvoice3_tts` | `stream`, `speed` |

This means that even when directly calling `PUT /api/tts/config`, you cannot override GPT-SoVITS's `ref_audio_path`, `prompt_text`, or CosyVoice3's `client_url`, `sft_dropdown`, reference audio paths, and other fields through the API.

---

## 6. Sensitive Configuration Rules

TTS configuration supports `${ENV_NAME}` environment variable placeholders. Sensitive fields like `api_key` must use placeholders.

Correct:

```yaml
siliconflow_tts:
  api_key: ${SILICONFLOW_API_KEY}
```

Incorrect:

```yaml
siliconflow_tts:
  api_key: sk-real-secret-key
```

The backend has two layers of protection:

- Runtime can read the expanded environment variable values.
- When saving YAML, placeholders are preserved as much as possible; runtime secrets are not written back to the configuration file.
- When the API returns configuration, `api_key`, `token`, `secret`, `password` are masked as `********`.

If you find that a real key has been written to the configuration file, immediately:

1. Delete the key and change it back to `${SILICONFLOW_API_KEY}`.
2. Rotate the API Key in the service provider's backend.
3. Scan the repository to confirm no plaintext secrets remain.

---

## 7. Frontend Settings Page Mapping

Settings page path:

```text
/settings/modules/speech
```

Page sections and configuration mapping:

| Page Section | Corresponding Configuration | Description |
| --- | --- | --- |
| TTS Module | `enabled` | Controls whether TTS is enabled. |
| Providers | `tts_model` | Switch current Provider. |
| Auto-play AI replies | `auto_play` | Whether to automatically read after AI reply is complete. |
| Show playback control on home | `show_player_on_home` | Whether to show floating playback control on `/`. |
| Playback volume | `volume` | Browser playback volume. |
| Edge Voice model | `edge_tts.voice` | Edge voice. |
| Edge Rate | `edge_tts.rate` | Edge speech rate. |
| SiliconFlow Voice model | `siliconflow_tts.default_voice` | SiliconFlow voice. |
| SiliconFlow Request streaming mode | `siliconflow_tts.stream` | Request streaming generation. |
| CosyVoice3 Model | `cosyvoice3_tts.sft_dropdown` | Read-only display of current local model/voice configuration. |
| CosyVoice3 Request streaming mode | `cosyvoice3_tts.stream` | Request CosyVoice WebUI streaming inference. |
| CosyVoice3 Speed | `cosyvoice3_tts.speed` | Speech rate multiplier. |

---

## 8. Runtime Pipeline

### Auto-Play

```text
WebSocket chat:complete
  -> Frontend confirms enabled && auto_play
  -> POST /api/tts/synthesize
  -> TTSService
  -> Current Provider synthesizes complete audio
  -> Frontend generates ObjectURL
  -> HTMLAudioElement playback
```

The current TTS processing mechanism is: after the LLM generates the complete reply text, it is fed to the TTS Provider for synthesis. It is not a real-time streaming pipeline that plays while generating.

### Single Message Playback

```text
User clicks the play button on an AI message
  -> POST /api/tts/synthesize
  -> Play the returned audio
```

### Playback Queue

The frontend `useAudioPlayer` maintains a queue. After the current audio finishes playing, the next one plays automatically. Currently provides pause, resume, and stop functionality.

---

## 9. API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/tts/providers` | Get Provider list, availability, and current configuration. |
| `GET` | `/api/tts/config` | Get current TTS configuration. Sensitive values are masked. |
| `PUT` | `/api/tts/config` | Merge and save TTS configuration. Subject to write-back whitelist restrictions. |
| `POST` | `/api/tts/switch` | Switch current Provider. |
| `GET` | `/api/tts/health` | Get TTS health status. |
| `GET` | `/api/tts/voices` | Get Provider voice list. |
| `POST` | `/api/tts/synthesize` | Synthesize complete audio. |

Switch Provider example:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8430/api/tts/switch" `
  -ContentType "application/json" `
  -Body '{"provider":"edge_tts"}'
```

Synthesize speech example:

```powershell
Invoke-WebRequest `
  -Method Post `
  -Uri "http://127.0.0.1:8430/api/tts/synthesize" `
  -ContentType "application/json" `
  -Body '{"text":"Hello, I am ATRI."}' `
  -OutFile "tts-test.mp3"
```

---

## 10. Error Handling and Retry

When the frontend calls `/api/tts/synthesize`, it automatically retries once. The retry conditions are:

- Network error, or request did not receive a response.
- HTTP `429`.
- HTTP `5xx`.

HTTP `4xx` configuration errors are not retried. For example, a `400` caused by GPT-SoVITS parameter errors should be fixed by correcting the configuration, not by repeating the request.

The backend Provider layer does not retry on its own. This avoids repeated requests to local model services or cloud services under error configurations.

---

## 11. Streaming TTS Status

Currently, ATRI TTS uses complete audio mode:

```text
Text -> Backend waits for Provider synthesis to complete -> Returns complete Blob -> Frontend plays
```

True streaming TTS has high complexity and requires simultaneous changes to:

- Backend route: from `Response(bytes)` to `StreamingResponse`.
- TTS interface: implement `synthesize_stream()`.
- Provider: adapt each one for real chunked output.
- Frontend: from Blob/ObjectURL to MediaSource or Web Audio chunked playback.
- Queue management: handle the state of "still downloading but already playing".
- Error recovery: handle half-audio failures, cancellation, retry, and resource release.

Therefore, it is currently recommended to implement it as a separate small Phase later, not mixed with Phase 10's complete text synthesis.

---

## 12. Common Configuration Examples

### Example A: Edge TTS Chinese Voice

```yaml
tts_model: edge_tts
enabled: true
auto_play: true
edge_tts:
  voice: zh-CN-XiaoxiaoNeural
  rate: +0%
```

Suitable for quick verification. Recommended as default configuration.

### Example B: GPT-SoVITS Local Voice

```yaml
tts_model: gpt_sovits_tts
gpt_sovits_tts:
  api_url: http://127.0.0.1:9880/tts
  text_lang: zh
  ref_audio_path: D:/path/to/ref.wav
  prompt_lang: zh
  prompt_text: Reference audio corresponding text
  text_split_method: cut5
  media_type: wav
```

Suitable for local voice cloning. The frontend does not write back these fields.

### Example C: SiliconFlow CosyVoice2

```yaml
tts_model: siliconflow_tts
siliconflow_tts:
  api_key: ${SILICONFLOW_API_KEY}
  default_model: FunAudioLLM/CosyVoice2-0.5B
  default_voice: FunAudioLLM/CosyVoice2-0.5B:claire
  stream: false
```

Suitable for cloud TTS. The frontend can switch `default_voice` and `stream`.

### Example D: CosyVoice3 Local WebUI

```yaml
tts_model: cosyvoice3_tts
cosyvoice3_tts:
  client_url: http://127.0.0.1:50000/
  mode_checkbox_group: 预训练音色
  sft_dropdown: 中文女
  stream: false
  speed: 1.0
```

Suitable for local CosyVoice3 deployment. The frontend read-only displays `sft_dropdown`, and can adjust `stream` and `speed`.

---

## 13. Self-Check Commands

Backend TTS tests:

```powershell
cd D:\Coding\GitHub_Resuorse\emotion-robot\atri
uv run ruff check src/tts tests/routes/test_tts.py
uv run python -m mypy src/ --ignore-missing-imports
uv run pytest tests/routes/test_tts.py -v
```

Frontend checks:

```powershell
cd D:\Coding\GitHub_Resuorse\emotion-robot\atri-webui
npm run type-check
npm run build
```

---

## 14. Common Issues

### Provider shows unavailable

The cause is usually uninstalled dependencies, local service not started, incorrect model path, or unconfigured API Key.

Resolution:

1. Check the status prompt on the Provider card in `/settings/modules/speech`.
2. Confirm the corresponding Python package is installed.
3. Confirm the local service port or environment variable is correct.

### Edge TTS cannot synthesize

Resolution:

- Confirm the `edge-tts` dependency is installed.
- Confirm the current network can access the Microsoft Edge TTS service.
- Try a different `voice`.

### GPT-SoVITS returns 400 or 502

`400` usually comes from GPT-SoVITS server-side parameter validation failure. ATRI wraps upstream errors as `502 Bad Gateway`.

Resolution:

- Check if `ref_audio_path` exists and is accessible by the GPT-SoVITS service.
- Check if `prompt_text` matches the reference audio.
- Check if `text_lang`, `prompt_lang`, `text_split_method` are values supported by the server.
- Confirm the GPT-SoVITS service is listening on `api_url`.

### SiliconFlow Provider unavailable

Resolution:

- Set `$env:SILICONFLOW_API_KEY`.
- Confirm `api_key` uses the `${SILICONFLOW_API_KEY}` placeholder.
- Confirm `default_voice` belongs to the current `default_model`.

### CosyVoice3 does not show complete voice list

This is by design. CosyVoice3 uses a local WebUI call mode, not a fixed cloud voice list like Edge.

The frontend read-only displays the current `sft_dropdown`. Available values depend on the CosyVoice WebUI dropdown you started.

### TTS is enabled but AI replies are not automatically read

Resolution:

1. Confirm `enabled: true`.
2. Confirm `auto_play: true`.
3. Confirm the frontend has reloaded the configuration.
4. Check the browser console and backend logs.

---

## 15. Modification Suggestions

Prioritize modifying TTS configuration through `/settings/modules/speech`. Direct YAML editing is only recommended in the following scenarios:

- Initial configuration of environment variable placeholders.
- Configuring GPT-SoVITS reference audio.
- Configuring CosyVoice3 local WebUI.
- Batch adjusting local Provider parameters.
- Frontend settings page cannot start, need to manually restore default Provider.

After directly editing YAML, restart the backend service for the configuration to take effect.

Do not use YAML formatting tools when saving configuration. The current backend only patches specified fields, aiming to preserve comments, order, and quotes.
