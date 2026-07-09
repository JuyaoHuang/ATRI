---
status: active
owner: tts
created: 2026-07-08
updated: 2026-07-08
related_code:
  - config/tts_config.yaml
  - src/tts/config.py
  - src/tts/service.py
  - src/routes/tts.py
---

# TTS 配置与运行边界

本文沉淀 TTS 配置的开发侧规则。用户侧配置步骤仍以 [TTS 配置说明](../../../configs/CN/TTS配置说明.md) 为准。

## 配置入口

根配置通过 `config.yaml` 引用 TTS 配置：

```yaml
tts_config: config/tts_config.yaml
```

运行时读取路径：

```text
config/tts_config.yaml -> runtime config["tts"] -> TTSService
```

TTS 配置采用 Provider 同名顶层块：

```yaml
tts_model: edge_tts
enabled: true
auto_play: true

edge_tts:
  voice: zh-CN-XiaoxiaoNeural

cosyvoice3_tts:
  client_url: http://127.0.0.1:50000/
```

## Provider 边界

当前稳定 Provider：

| Provider | 类型 | 边界 |
|---|---|---|
| `edge_tts` | 云服务 | 直接调用 Edge TTS，适合默认验证链路。 |
| `gpt_sovits_tts` | 本地服务 | ATRI 只调用外部 HTTP API，不加载模型。 |
| `siliconflow_tts` | 云服务 | 通过 OpenAI 风格音频接口合成语音。 |
| `cosyvoice3_tts` | 本地服务 | ATRI 通过 `gradio-client` 调用外部 CosyVoice WebUI。 |

Provider 负责把完整文本合成为完整音频。分段流式播放由应用层管理，详见 [streaming-design.zh-CN.md](streaming-design.zh-CN.md)。

## 前端回写白名单

前端设置页和 `PUT /api/tts/config` 都必须遵守回写白名单。

| Provider | 允许回写字段 |
|---|---|
| `edge_tts` | `voice`、`rate` |
| `gpt_sovits_tts` | 无 |
| `siliconflow_tts` | `default_voice`、`stream` |
| `cosyvoice3_tts` | `stream`、`speed` |

不允许前端回写的字段通常属于本地服务部署、参考音频、密钥或接口形状。例如：

- `gpt_sovits_tts.ref_audio_path`
- `gpt_sovits_tts.prompt_text`
- `cosyvoice3_tts.client_url`
- `cosyvoice3_tts.sft_dropdown`
- `cosyvoice3_tts.prompt_wav_upload_url`
- `siliconflow_tts.api_key`

## 敏感配置规则

敏感字段必须通过环境变量占位符引用：

```yaml
siliconflow_tts:
  api_key: ${SILICONFLOW_API_KEY}
```

API 返回配置时应 mask `api_key`、`token`、`secret`、`password` 等字段。保存 YAML 时应尽量保留占位符，不把运行时密钥写回文件。

## REST 完整音频链路

非分段流式场景仍走完整音频 REST 链路：

```text
WebSocket chat:complete
  -> frontend checks enabled && auto_play
  -> POST /api/tts/synthesize
  -> TTSService.synthesize()
  -> current Provider returns complete audio bytes
  -> frontend creates ObjectURL
  -> HTMLAudioElement plays
```

手动播放历史消息也继续使用 `POST /api/tts/synthesize`。

## 错误处理

前端可对 `/api/tts/synthesize` 做一次有限重试：

- 网络错误
- HTTP `429`
- HTTP `5xx`

不应重试配置类 `4xx` 错误。Provider 层不做自动重试，避免错误配置导致本地模型服务或云端服务被重复打爆。

## 相关文档

- [TTS 配置说明](../../../configs/CN/TTS配置说明.md)
- [CosyVoice3 Provider 设计](cosyvoice3-provider.zh-CN.md)
- [TTS 分段流式化设计](streaming-design.zh-CN.md)
