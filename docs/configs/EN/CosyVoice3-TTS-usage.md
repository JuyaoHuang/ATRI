# CosyVoice3 TTS Usage Guide

This document describes the current implementation status, configuration methods, parameter meanings, and voice model mechanisms of the `cosyvoice3_tts` in the ATRI backend.

## Current Implementation Status

The factory for `cosyvoice3_tts` has been implemented.

Related code:

- `src/tts/providers/cosyvoice3_tts.py`
  - Registered to the TTS factory via `@TTSFactory.register("cosyvoice3_tts", ...)`.
  - Provider class is `CosyVoice3TTSProvider`.
  - Calls the CosyVoice Gradio service via `gradio_client.Client(client_url).predict(...)`.
- `src/tts/providers/__init__.py`
  - Has imported `cosyvoice3_tts`, registration is completed when the service starts.
- `src/tts/service.py`
  - Only allows frontend/API write-back for `stream` and `speed` fields.

The current implementation "calls an external CosyVoice Gradio WebUI" rather than directly loading the CosyVoice3 model within the ATRI process.

## Official Links

- CosyVoice GitHub Repository: <https://github.com/FunAudioLLM/CosyVoice>
- CosyVoice3 Official Demo Page: <https://funaudiollm.github.io/cosyvoice3/>
- CosyVoice3 Hugging Face Model Card: <https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512>
- Official WebUI Example Source: <https://github.com/FunAudioLLM/CosyVoice/blob/main/webui.py>
- CosyVoice3 Paper: <https://arxiv.org/abs/2505.17589>

## Basic Usage Flow

1. Start the CosyVoice Gradio WebUI separately.

   ATRI connects by default to:

   ```yaml
   cosyvoice3_tts:
     client_url: http://127.0.0.1:50000/
   ```

   Therefore, the CosyVoice WebUI needs to listen on port `50000`, or change `client_url` to the actual address.

2. Select the provider in `config/tts_config.yaml`:

   ```yaml
   tts_model: cosyvoice3_tts
   ```

3. Confirm backend dependencies exist:

   ```bash
   uv sync
   ```

   `pyproject.toml` already includes `gradio-client`.

4. Select `CosyVoice3` in the frontend settings page, then configure fields allowed for frontend adjustment:

   - `Request streaming mode`: writes to `stream`
   - `Speed`: writes to `speed`

   `sft_dropdown` will be displayed as read-only. To modify it, directly edit `config/tts_config.yaml`.

## Voice Model Mechanism

CosyVoice3 does not use a fixed cloud voice list like Edge TTS, such as `zh-CN-XiaoxiaoNeural`.

CosyVoice's "voice" mainly comes from two types of mechanisms:

- Pre-trained voices, which correspond to `sft_dropdown` in the WebUI.
- Reference audio cloning, which provides reference audio through `prompt_wav_upload_url` or `prompt_wav_record_url`.

In the official WebUI, the pre-trained voice list comes from the server model object's `list_available_spks()`. This means the available voices depend on the model directory you loaded locally, not an ATRI frontend built-in list.

Currently, ATRI's `/api/tts/voices?provider=cosyvoice3_tts` only returns the current `sft_dropdown` from the configuration file and does not actively fetch the complete voice list from the CosyVoice WebUI. The actual available `sft_dropdown` values should be based on the CosyVoice WebUI dropdown you started.

## Configuration Example

```yaml
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

## Parameter Descriptions

| Field | Frontend Write-Back Allowed | Description |
| --- | --- | --- |
| `client_url` | No | CosyVoice Gradio WebUI address. ATRI calls the local or remote CosyVoice service through this address. |
| `mode_checkbox_group` | No | Inference mode. Common values: `预训练音色` (Pre-trained Voice), `3s极速复刻` (3s Quick Clone), `跨语种复刻` (Cross-lingual Clone), `自然语言控制` (Natural Language Control). |
| `sft_dropdown` | No | Pre-trained voice ID. Only meaningful in pre-trained voice mode and some natural language control modes. |
| `prompt_text` | No | Text corresponding to the reference audio. The 3-second clone mode usually requires it to match the reference audio content. |
| `prompt_wav_upload_url` | No | Path or URL of the uploaded reference audio. Used in clone/cross-lingual modes. |
| `prompt_wav_record_url` | No | Path or URL of the recorded reference audio. The current implementation passes it to the Gradio API. |
| `instruct_text` | No | Natural language control instructions, such as requesting emotion, dialect, speech rate, volume, etc. |
| `stream` | Yes | Request CosyVoice WebUI to use streaming inference. ATRI currently still returns the result as complete audio to the frontend. |
| `seed` | No | Random seed. Fixing it helps reproduce similar results. |
| `speed` | Yes | Speech rate multiplier. Typically `1.0` is normal speed, below 1 is slower, above 1 is faster. |
| `api_name` | No | Gradio API name. Currently adapted to the default `/generate_audio`. |

## Inference Mode Descriptions

### Pre-trained Voice

Uses `sft_dropdown` to specify a server-side existing voice.

Suitable scenarios:

- Only want to use the model's built-in voices.
- Don't want to prepare reference audio.
- Want the simplest configuration.

In this mode, `prompt_text`, `prompt_wav_upload_url`, `prompt_wav_record_url`, and `instruct_text` are usually ignored by the server.

### 3s Quick Clone

Uses reference audio to clone a voice.

Key parameters:

- `prompt_wav_upload_url` or `prompt_wav_record_url`
- `prompt_text`

`prompt_text` should match the actual speech content in the reference audio. Reference audio quality directly affects the cloning result.

### Cross-lingual Clone

Uses reference audio to provide the speaker's voice, but the generated text can be in another language.

Key parameters:

- `prompt_wav_upload_url` or `prompt_wav_record_url`
- `mode_checkbox_group: 跨语种复刻`

This mode relies more on reference audio quality. The reference audio should be clear, free of background noise, and have a single speaker.

### Natural Language Control

Controls style through `instruct_text`, such as dialect, emotion, speech rate, or volume.

The CosyVoice3 official model card demonstrates usage closer to `inference_instruct2`. ATRI currently does not directly call the Python API but forwards parameters to the Gradio WebUI, so the actual behavior depends on the WebUI implementation you started.

## Difference Between `prompt_wav_upload_url` and `prompt_wav_record_url`

Both fields ultimately represent "reference audio."

- `prompt_wav_upload_url` corresponds to the audio file uploaded in the WebUI.
- `prompt_wav_record_url` corresponds to the audio file recorded in the WebUI.

In the current ATRI implementation, both are passed to the CosyVoice WebUI via `gradio_client.handle_file(...)`.

If both are configured, the server-side WebUI processing logic typically prioritizes the uploaded audio. The specific priority depends on the CosyVoice WebUI code you are running.

## Common Issues

### Why shouldn't the frontend display Edge's voice list?

Because CosyVoice3's voices are not Edge TTS's cloud voice IDs. Edge's IDs like `zh-CN-XiaoxiaoNeural` and `en-US-AriaNeural` have no meaning for CosyVoice3.

If the frontend shows Edge voices after switching to CosyVoice3, it is usually because the frontend retained the previous provider's voices cache, not because CosyVoice3 actually supports these voices.

### What should `sft_dropdown` be filled with?

Open the CosyVoice WebUI you started and check the "Select Pre-trained Voice" dropdown. The values displayed there are the available `sft_dropdown` options.

Different model directories may have different pre-trained voices. If the model does not have SFT pre-trained voices, the WebUI may only show empty values.

### Why does the frontend not allow modification of some configuration fields?

ATRI currently only allows the frontend to modify high-frequency, safe runtime parameters:

- `stream`
- `speed`

Other fields are typically related to local service deployment, reference audio paths, and Gradio API structure. Allowing the frontend to write back these fields could easily overwrite manual configurations.

### Does CosyVoice3 support voice cloning?

Yes. The official model card introduces zero-shot multilingual speech synthesis and demonstrates zero-shot, cross-lingual, and instruct usage. In ATRI, this needs to be implemented through the CosyVoice Gradio WebUI's clone mode and reference audio parameters.
