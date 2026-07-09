# CosyVoice3 TTS Usage Guide

The detailed CosyVoice3 Provider implementation notes have moved to the development documentation:

- [CosyVoice3 Provider Design](../../developments/modules/tts/cosyvoice3-provider.en-US.md)

If you only need to configure and use CosyVoice3, start with:

- [TTS Configuration Guide](TTS-configuration.md)

## Minimal Configuration

```yaml
tts_model: cosyvoice3_tts

cosyvoice3_tts:
  client_url: http://127.0.0.1:50000/
  mode_checkbox_group: 预训练音色
  sft_dropdown: 中文女
  stream: false
  speed: 1.0
```

You need to start the CosyVoice Gradio WebUI separately and make sure `client_url` points to the actual service address.

The frontend settings page only allows writing:

- `stream`
- `speed`

Fields such as `client_url`, `sft_dropdown`, and reference audio paths should be edited directly in `config/tts_config.yaml`.
