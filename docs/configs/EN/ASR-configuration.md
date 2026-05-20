# ASR Configuration Guide

> **Applicable Scope**: Phase 9 ASR Voice Input
> **Configuration File**: `atri/config/asr_config.yaml`
> **Settings Page**: `/settings/modules/hearing` in `atri-webui`
> **Last Updated**: 2026-04-25

This document describes the ASR (Automatic Speech Recognition) configuration structure, Provider selection, frontend settings page mapping, and common troubleshooting methods.

---

## 1. Quick Start

The default configuration uses the browser's built-in Web Speech API. It does not require a backend model or an API Key.

```yaml
asr_model: web_speech_api
auto_send:
  enabled: false
  delay_ms: 2000
```

After starting, open the frontend:

```text
/settings/modules/hearing
```

On this page you can:

- Select microphone input device
- Switch ASR Provider
- Configure recognition language, model, and path
- Test speech-to-text
- Configure whether to automatically send transcribed text to chat

---

## 2. Configuration Loading Method

The root configuration file `atri/config.yaml` references the ASR configuration through the following entry:

```yaml
asr_config: config/asr_config.yaml
```

The backend `config_loader` loads it into the `asr` node of the runtime configuration:

```python
config["asr"]
```

Therefore, the ASR module actually reads:

```text
atri/config/asr_config.yaml -> runtime config["asr"]
```

---

## 3. Top-Level Configuration Structure

The current configuration uses the Open-LLM-VTuber style: `asr_model` specifies the current Provider, and Provider parameters are saved in a top-level block with the same name.

```yaml
asr_model: web_speech_api
auto_send:
  enabled: false
  delay_ms: 2000

web_speech_api:
  language: zh-CN
  continuous: true
  interim_results: true
  max_alternatives: 1

faster_whisper:
  model_path: distil-medium.en
  download_root: models/whisper
  language: en
  device: auto
  compute_type: int8
  prompt: ''

whisper_cpp:
  model_name: small
  model_dir: models/whisper
  print_realtime: false
  print_progress: false
  language: auto
  prompt: ''

openai_whisper:
  model: whisper-1
  api_key: ${OPENAI_API_KEY}
  base_url: ''
  language: ''
  prompt: ''
```

### Top-Level Fields

| Field | Type | Description |
| --- | --- | --- |
| `asr_model` | string | Name of the currently enabled ASR Provider. |
| `auto_send.enabled` | boolean | Whether to automatically send to the chat input pipeline after transcription is complete. Disabled by default. |
| `auto_send.delay_ms` | number | Auto-send delay in milliseconds. Defaults to `2000`. |

Currently available `asr_model` options:

| Provider | Type | Backend Transcription | Browser Streaming | Description |
| --- | --- | --- | --- | --- |
| `web_speech_api` | Browser | No | Yes | Uses browser SpeechRecognition. Default recommendation. |
| `faster_whisper` | Local | Yes | No | Local faster-whisper, references OLV pipeline. |
| `whisper_cpp` | Local | Yes | No | Local pywhispercpp, references OLV pipeline. |
| `openai_whisper` | Cloud Service | Yes | No | OpenAI-compatible audio transcription. |

The `whisper` configuration block is currently reserved for OLV compatibility and future expansion. Phase 9 does not currently register a `whisper` Provider. Do not set `asr_model` to `whisper`.

---

## 4. Provider Configuration

### 4.1 `web_speech_api`

Browser-side speech recognition Provider. The backend only saves configuration and status, and does not receive audio transcription.

```yaml
asr_model: web_speech_api
web_speech_api:
  language: zh-CN
  continuous: true
  interim_results: true
  max_alternatives: 1
```

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `language` | string | `zh-CN` | Browser recognition language. Common values: `zh-CN`, `en-US`, `ja-JP`. |
| `continuous` | boolean | `true` | Whether to continuously listen. |
| `interim_results` | boolean | `true` | Whether to return interim recognition results. |
| `max_alternatives` | number | `1` | Number of candidate results returned by the browser. |

Usage suggestions:

- Chrome, Edge, and Safari have good support for Web Speech API.
- Firefox is usually unavailable or has limited support.
- This Provider does not require Python dependencies or model files.

### 4.2 `faster_whisper`

Local faster-whisper Provider. Suitable for local offline transcription.

```yaml
asr_model: faster_whisper
faster_whisper:
  model_path: distil-medium.en
  download_root: models/whisper
  language: en
  device: auto
  compute_type: int8
  prompt: ''
```

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `model_path` | string | `distil-medium.en` | Model name, local path, or Hugging Face model ID. |
| `download_root` | string | `models/whisper` | Model download and cache directory. |
| `language` | string | `en` | Recognition language. Empty string or `auto` for auto-detection. |
| `device` | string | `auto` | Inference device. Common values: `auto`, `cpu`, `cuda`. |
| `compute_type` | string | `int8` | Inference precision. `int8` is commonly used for CPU. |
| `prompt` | string | `''` | Initial prompt, can improve proper noun recognition. |

Dependency instructions:

```powershell
cd D:\Coding\GitHub_Resuorse\emotion-robot\atri
uv add faster-whisper
```

If the dependency or model is unavailable, the Provider will show as unavailable and will not prevent the backend from starting.

### 4.3 `whisper_cpp`

Local whisper.cpp Provider, using `pywhispercpp`.

```yaml
asr_model: whisper_cpp
whisper_cpp:
  model_name: small
  model_dir: models/whisper
  print_realtime: false
  print_progress: false
  language: auto
  prompt: ''
```

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `model_name` | string | `small` | pywhispercpp model name. Common values: `tiny`, `base`, `small`, `medium`. |
| `model_dir` | string | `models/whisper` | Model directory. |
| `print_realtime` | boolean | `false` | Whether to print real-time segments. |
| `print_progress` | boolean | `false` | Whether to print progress. |
| `language` | string | `auto` | Recognition language. |
| `prompt` | string | `''` | Initial prompt. |

Dependency instructions:

```powershell
cd D:\Coding\GitHub_Resuorse\emotion-robot\atri
uv add pywhispercpp
```

### 4.4 `openai_whisper`

OpenAI-compatible cloud transcription Provider.

```yaml
asr_model: openai_whisper
openai_whisper:
  model: whisper-1
  api_key: ${OPENAI_API_KEY}
  base_url: ''
  language: ''
  prompt: ''
```

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `model` | string | `whisper-1` | Transcription model name. |
| `api_key` | string | `${OPENAI_API_KEY}` | API Key. Must use environment variable placeholder. |
| `base_url` | string | `''` | OpenAI-compatible endpoint. Empty string uses SDK default. |
| `language` | string | `''` | Recognition language. Empty string for auto-detection. |
| `prompt` | string | `''` | Initial prompt. |

Dependency instructions:

```powershell
cd D:\Coding\GitHub_Resuorse\emotion-robot\atri
uv add openai
```

Environment variable example:

```powershell
$env:OPENAI_API_KEY = "YOUR_API_KEY"
```

Do not write real API Keys into `asr_config.yaml`.

---

## 5. Sensitive Configuration Rules

ASR configuration supports `${ENV_NAME}` environment variable placeholders. Sensitive fields like `api_key` must use placeholders.

Correct:

```yaml
openai_whisper:
  api_key: ${OPENAI_API_KEY}
```

Incorrect:

```yaml
openai_whisper:
  api_key: sk-real-secret-key
```

The backend has two layers of protection:

- Runtime can read the expanded environment variable values.
- When saving YAML, placeholders are preserved as much as possible; runtime secrets are not written back to the configuration file.
- When the API returns configuration, `api_key`, `token`, `secret`, `password` are masked as `********`.

If you find that a real key has been written to the configuration file, immediately:

1. Delete the key and change it back to `${OPENAI_API_KEY}`.
2. Rotate the API Key in the service provider's backend.
3. Scan the repository to confirm no plaintext secrets remain.

---

## 6. Frontend Settings Page Mapping

Settings page path:

```text
/settings/modules/hearing
```

Page sections and configuration mapping:

| Page Section | Corresponding Configuration | Description |
| --- | --- | --- |
| Audio Input Device | Browser localStorage | Select microphone device. |
| Providers | `asr_model` | Switch current Provider. |
| Web Speech API Settings | `web_speech_api` | Configure browser recognition language and interim results. |
| Faster Whisper Settings | `faster_whisper` | Configure model, language, and download directory. |
| Whisper.cpp Settings | `whisper_cpp` | Configure model name and model directory. |
| OpenAI Whisper Settings | `openai_whisper` | Configure model and base URL. |
| Auto-send Settings | `auto_send` | Control whether to auto-send after transcription. |
| Audio Monitor | Not persisted | Test microphone volume and voice threshold. |
| Transcription | Current Provider | Test speech-to-text pipeline. |

---

## 7. Runtime Pipeline

### `web_speech_api`

```text
Browser Microphone
  -> SpeechRecognition
  -> Frontend receives transcript
  -> Fill into chat input box
  -> User manually sends, or sends per auto_send rules
```

The backend does not receive audio files.

### Backend Providers

Applicable to `faster_whisper`, `whisper_cpp`, `openai_whisper`.

```text
Browser Microphone
  -> MediaRecorder
  -> POST /api/asr/transcribe
  -> ASRService
  -> Provider transcription
  -> Returns transcript
  -> Frontend fills into chat input box
```

---

## 8. API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/asr/providers` | Get Provider list, availability, and current configuration. |
| `GET` | `/api/asr/config` | Get current ASR configuration. Sensitive values are masked. |
| `PUT` | `/api/asr/config` | Merge and save ASR configuration. |
| `POST` | `/api/asr/switch` | Switch current Provider. |
| `GET` | `/api/asr/health` | Get ASR health status. |
| `POST` | `/api/asr/transcribe` | Upload audio and transcribe. Only supported by backend Providers. |

Switch Provider example:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8430/api/asr/switch" `
  -ContentType "application/json" `
  -Body '{"provider":"web_speech_api"}'
```

---

## 9. Common Configuration Examples

### Example A: Chinese Browser Recognition

```yaml
asr_model: web_speech_api
web_speech_api:
  language: zh-CN
  continuous: true
  interim_results: true
  max_alternatives: 1
auto_send:
  enabled: false
  delay_ms: 2000
```

Suitable for quick verification. Recommended as default configuration.

### Example B: Local faster-whisper English Recognition

```yaml
asr_model: faster_whisper
faster_whisper:
  model_path: distil-medium.en
  download_root: models/whisper
  language: en
  device: auto
  compute_type: int8
  prompt: ''
```

Suitable for offline English transcription.

### Example C: Local whisper.cpp Auto Language Recognition

```yaml
asr_model: whisper_cpp
whisper_cpp:
  model_name: small
  model_dir: models/whisper
  print_realtime: false
  print_progress: false
  language: auto
  prompt: ''
```

Suitable for lightweight local transcription.

### Example D: Cloud OpenAI-compatible Transcription

```yaml
asr_model: openai_whisper
openai_whisper:
  model: whisper-1
  api_key: ${OPENAI_API_KEY}
  base_url: ''
  language: ''
  prompt: ''
```

Suitable for scenarios where you don't want to load models locally.

---

## 10. Self-Check Commands

Backend ASR tests:

```powershell
cd D:\Coding\GitHub_Resuorse\emotion-robot\atri
uv run ruff check src tests/routes/test_asr.py
uv run python -m mypy src/ --ignore-missing-imports
uv run pytest tests/routes/test_asr.py -v
```

Frontend checks:

```powershell
cd D:\Coding\GitHub_Resuorse\emotion-robot\atri-webui
npm run type-check
npm run build
```

---

## 11. Common Issues

### Provider shows unavailable

The cause is usually uninstalled dependencies, incorrect model path, or unconfigured API Key.

Resolution:

1. Check the status prompt on the Provider card in `/settings/modules/hearing`.
2. Confirm the corresponding Python package is installed.
3. Confirm the model directory or environment variable is correct.

### Web Speech API unavailable

The cause is usually the browser not supporting `SpeechRecognition`.

Resolution:

- Use Chrome, Edge, or Safari.
- Or switch to `faster_whisper`, `whisper_cpp`, or `openai_whisper`.

### Backend upload transcription returns 503

If the current Provider is `web_speech_api`, this is expected behavior. It only supports browser-side recognition.

Resolution:

- Switch to `faster_whisper`, `whisper_cpp`, or `openai_whisper`.
- Confirm dependencies and model/API Key are available.

### Transcription successful but not auto-sent

The default behavior is manual sending. Speech transcription first fills the chat input box, and the user can edit before sending.

To enable auto-sending:

1. Open `/settings/modules/hearing`.
2. Enable **Auto-send transcribed text**.
3. Set `Auto-send delay`.

---

## 12. Modification Suggestions

Prioritize modifying ASR configuration through `/settings/modules/hearing`. Direct YAML editing is only recommended in the following scenarios:

- Initial configuration of environment variable placeholders.
- Batch adjusting local model paths.
- Frontend settings page cannot start, need to manually restore default Provider.

After directly editing YAML, restart the backend service for the configuration to take effect.
