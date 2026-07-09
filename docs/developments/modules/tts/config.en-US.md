---
status: active
owner: tts
created: 2026-07-09
updated: 2026-07-09
related_code:
  - config/tts_config.yaml
  - src/tts/config.py
  - src/tts/service.py
  - src/routes/tts.py
---

# TTS Configuration and Runtime Boundaries

This document captures the development-side rules for TTS configuration. User-facing setup steps remain in [TTS Configuration Guide](../../../configs/EN/TTS-configuration.md).

## Configuration Entry

The root `config.yaml` references the TTS configuration:

```yaml
tts_config: config/tts_config.yaml
```

Runtime loading path:

```text
config/tts_config.yaml -> runtime config["tts"] -> TTSService
```

TTS uses Provider-specific top-level blocks:

```yaml
tts_model: edge_tts
enabled: true
auto_play: true

edge_tts:
  voice: zh-CN-XiaoxiaoNeural

cosyvoice3_tts:
  client_url: http://127.0.0.1:50000/
```

## Provider Boundaries

| Provider | Type | Boundary |
| --- | --- | --- |
| `edge_tts` | Cloud service | Calls Edge TTS directly and is suitable for default pipeline verification. |
| `gpt_sovits_tts` | Local service | ATRI only calls the external HTTP API and does not load the model. |
| `siliconflow_tts` | Cloud service | Calls a speech synthesis API. |
| `cosyvoice3_tts` | Local service | ATRI uses `gradio-client` to call an external CosyVoice WebUI. |

Providers synthesize complete audio from complete text. Segmented playback is managed at the application layer. See [streaming-design.zh-CN.md](streaming-design.zh-CN.md) until an English streaming design is added.

## Frontend Write-Back Allowlist

Both the frontend settings page and `PUT /api/tts/config` must follow the write-back allowlist.

| Provider | Writable fields |
| --- | --- |
| `edge_tts` | `voice`, `rate` |
| `gpt_sovits_tts` | None |
| `siliconflow_tts` | `default_voice`, `stream` |
| `cosyvoice3_tts` | `stream`, `speed` |

Fields that are not writable usually belong to local service deployment, reference audio, credentials, or API shape. Examples:

- `gpt_sovits_tts.ref_audio_path`
- `gpt_sovits_tts.prompt_text`
- `cosyvoice3_tts.client_url`
- `cosyvoice3_tts.sft_dropdown`
- `cosyvoice3_tts.prompt_wav_upload_url`
- `siliconflow_tts.api_key`

## Sensitive Configuration

Sensitive fields must use environment variable placeholders:

```yaml
siliconflow_tts:
  api_key: ${SILICONFLOW_API_KEY}
```

API responses should mask fields such as `api_key`, `token`, `secret`, and `password`. YAML saving should preserve placeholders whenever possible and must not write runtime secrets back to files.

## Complete-Audio REST Pipeline

Non-segmented playback continues to use the complete-audio REST path:

```text
WebSocket chat:complete
  -> frontend checks enabled && auto_play
  -> POST /api/tts/synthesize
  -> TTSService.synthesize()
  -> current Provider returns complete audio bytes
  -> frontend creates ObjectURL
  -> HTMLAudioElement plays
```

Manual playback for historical messages also continues to use `POST /api/tts/synthesize`.

## Error Handling

The frontend may retry `/api/tts/synthesize` once for:

- network errors
- HTTP `429`
- HTTP `5xx`

It should not retry configuration-related `4xx` errors. Provider implementations should not automatically retry either, to avoid repeatedly hitting local model services or cloud providers with invalid configuration.

## Related Documents

- [TTS Configuration Guide](../../../configs/EN/TTS-configuration.md)
- [CosyVoice3 Provider Design](cosyvoice3-provider.en-US.md)
- [TTS Segmented Streaming Design](streaming-design.zh-CN.md)
