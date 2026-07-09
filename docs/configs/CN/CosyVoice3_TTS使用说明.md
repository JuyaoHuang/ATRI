# CosyVoice3 TTS 使用说明

CosyVoice3 的详细 Provider 实现说明已迁移到开发文档：

- [CosyVoice3 Provider 设计](../../developments/modules/tts/cosyvoice3-provider.zh-CN.md)

如果只是配置和使用 CosyVoice3，请优先阅读：

- [TTS 配置说明](TTS配置说明.md)

## 最小配置

```yaml
tts_model: cosyvoice3_tts

cosyvoice3_tts:
  client_url: http://127.0.0.1:50000/
  mode_checkbox_group: 预训练音色
  sft_dropdown: 中文女
  stream: false
  speed: 1.0
```

使用前需要单独启动 CosyVoice Gradio WebUI，并确认 `client_url` 指向实际服务地址。

前端设置页只允许修改：

- `stream`
- `speed`

`client_url`、`sft_dropdown`、参考音频路径等字段需要直接编辑 `config/tts_config.yaml`。
