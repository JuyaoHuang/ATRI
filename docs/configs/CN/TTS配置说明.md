# TTS 配置说明

> **适用范围**: Phase 10 TTS 语音输出  
> **配置文件**: `atri/config/tts_config.yaml`  
> **设置页面**: `atri-webui` 的 `/settings/modules/speech`  
> **最后更新**: 2026-04-25

本文说明 TTS（Text-to-Speech，文本转语音）的配置结构、Provider 选择、前端设置页对应关系和常见排障方法。

---

## 1. 快速开始

默认推荐先使用 `edge_tts`。它不需要 API Key，适合验证 TTS 主链路。

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

启动后打开前端：

```text
/settings/modules/speech
```

你可以在该页面完成以下操作：

- 开启或关闭 TTS 模块
- 开启或关闭 AI 回复自动朗读
- 切换 TTS Provider
- 调整允许前端修改的 Provider 参数
- 测试文本转语音
- 控制是否在 `/` 页面显示播放控制组件

---

## 2. 配置加载方式

根配置文件 `atri/config.yaml` 通过下面的入口引用 TTS 配置：

```yaml
tts_config: config/tts_config.yaml
```

后端 `config_loader` 会把它加载到运行时配置的 `tts` 节点下：

```python
config["tts"]
```

因此 TTS 模块实际读取的是：

```text
atri/config/tts_config.yaml -> runtime config["tts"]
```

---

## 3. 顶层配置结构

当前配置采用 Open-LLM-VTuber 风格：`tts_model` 指定当前 Provider，Provider 参数使用同名顶层块保存。

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

### 顶层字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tts_model` | string | 当前启用的 TTS Provider 名称。 |
| `enabled` | boolean | 是否启用 TTS 模块。关闭后不会主动合成语音。 |
| `auto_play` | boolean | AI 回复完成后是否自动朗读。 |
| `show_player_on_home` | boolean | 是否在 `/` 页面显示浮动播放控制组件。 |
| `volume` | number | 浏览器播放音量，范围通常为 `0.0` 到 `1.0`。 |

当前可选的 `tts_model`：

| Provider | 类型 | 说明 |
| --- | --- | --- |
| `edge_tts` | 云服务 | Microsoft Edge neural voices，免费、无需 API Key。 |
| `gpt_sovits_tts` | 本地 | GPT-SoVITS HTTP API，音色由参考音频和 prompt 决定。 |
| `siliconflow_tts` | 云服务 | SiliconFlow 音频合成 API。 |
| `cosyvoice3_tts` | 本地 | 调用本地 CosyVoice3 Gradio WebUI。 |

---

## 4. Provider 配置

### 4.1 `edge_tts`

Edge TTS 使用 `edge-tts` Python 包调用 Microsoft Edge neural voices。

```yaml
tts_model: edge_tts
edge_tts:
  voice: zh-CN-XiaoxiaoNeural
  rate: +0%
  pitch: +0Hz
  volume: +0%
  format: mp3
```

| 字段 | 前端可写 | 说明 |
| --- | --- | --- |
| `voice` | 是 | Edge voice ID，例如 `zh-CN-XiaoxiaoNeural`。 |
| `rate` | 是 | 语速，例如 `+10%`、`-10%`。 |
| `pitch` | 否 | 音调，例如 `+10Hz`、`-10Hz`。 |
| `volume` | 否 | 合成阶段音量，例如 `+0%`。 |
| `format` | 否 | 输出格式。当前默认 `mp3`。 |

查看可用音色：

```powershell
cd D:\Coding\GitHub_Resuorse\emotion-robot\atri
uv run edge-tts --list-voices
```

前端 `Voice model` 会从 `/api/tts/voices?provider=edge_tts` 获取 Edge 音色列表。

### 4.2 `gpt_sovits_tts`

GPT-SoVITS 是本地 HTTP 服务。ATRI 不直接加载模型，只调用 GPT-SoVITS 服务端接口。

定位到 GPT-SoVITS 的目录，然后执行 `runtime\python.exe api_v2.py` 启动 gpt-sovits 服务。

```yaml
tts_model: gpt_sovits_tts
gpt_sovits_tts:
  api_url: http://127.0.0.1:9880/tts
  text_lang: zh
  ref_audio_path: D:/path/to/ref.wav
  prompt_lang: zh
  prompt_text: 参考音频对应文本
  text_split_method: cut5
  batch_size: '1'
  media_type: wav
  streaming_mode: 'false'
  timeout_seconds: 120
```

| 字段 | 前端可写 | 说明 |
| --- | --- | --- |
| `api_url` | 否 | GPT-SoVITS HTTP API 地址。 |
| `text_lang` | 否 | 待合成文本语言。 |
| `ref_audio_path` | 否 | 参考音频路径。音色主要由它决定。 |
| `prompt_lang` | 否 | 参考音频提示文本语言。 |
| `prompt_text` | 否 | 参考音频对应文本。 |
| `text_split_method` | 否 | 文本切分方式，例如 `cut5`。 |
| `batch_size` | 否 | 批处理大小。 |
| `media_type` | 否 | 返回音频格式，常用 `wav`。 |
| `streaming_mode` | 否 | GPT-SoVITS 服务端流式开关。ATRI 当前仍返回完整音频。 |
| `timeout_seconds` | 否 | HTTP 请求超时时间。 |

前端不会显示 GPT-SoVITS Provider 参数。修改这些字段时，直接编辑 `config/tts_config.yaml`。

### 4.3 `siliconflow_tts`

SiliconFlow 是云端音频合成 Provider，需要 API Key。

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

| 字段 | 前端可写 | 说明 |
| --- | --- | --- |
| `api_key` | 否 | API Key。必须使用环境变量占位符。 |
| `api_url` | 否 | SiliconFlow 语音合成 API 地址。 |
| `default_model` | 否 | 默认模型。 |
| `default_voice` | 是 | 默认音色，例如 `FunAudioLLM/CosyVoice2-0.5B:claire`。 |
| `sample_rate` | 否 | 输出采样率。 |
| `response_format` | 否 | 输出格式，常用 `mp3`、`wav`。 |
| `stream` | 是 | 请求服务端流式生成。ATRI 当前仍返回完整音频。 |
| `speed` | 否 | 语速倍率。 |
| `gain` | 否 | 增益。 |
| `timeout_seconds` | 否 | 请求超时时间。 |

环境变量示例：

```powershell
$env:SILICONFLOW_API_KEY = "YOUR_API_KEY"
```

不要把真实 API Key 写进 `tts_config.yaml`。

### 4.4 `cosyvoice3_tts`

CosyVoice3 是本地部署 Provider。ATRI 当前通过 `gradio-client` 调用 CosyVoice Gradio WebUI。

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

| 字段 | 前端可写 | 说明 |
| --- | --- | --- |
| `client_url` | 否 | CosyVoice Gradio WebUI 地址。 |
| `mode_checkbox_group` | 否 | 推理模式，例如 `预训练音色`、`3s极速复刻`、`跨语种复刻`。 |
| `sft_dropdown` | 否 | WebUI 中的预训练音色/模型下拉值。前端只读显示。 |
| `prompt_text` | 否 | 参考音频对应文本。 |
| `prompt_wav_upload_url` | 否 | 上传参考音频路径或 URL。 |
| `prompt_wav_record_url` | 否 | 录制参考音频路径或 URL。 |
| `instruct_text` | 否 | 自然语言控制指令。 |
| `stream` | 是 | 请求 CosyVoice WebUI 使用流式推理。ATRI 当前仍返回完整音频。 |
| `seed` | 否 | 随机种子。 |
| `speed` | 是 | 语速倍率。 |
| `api_name` | 否 | Gradio API 名称，默认 `/generate_audio`。 |

更详细说明见：

```text
atri/docs/CosyVoice3_TTS使用说明.md
```

---

## 5. 前端和后端回写规则

前端设置页只允许写入少数安全字段。后端也会过滤直接 API 调用中的受保护字段。

| Provider | 允许回写字段 |
| --- | --- |
| `edge_tts` | `voice`、`rate` |
| `gpt_sovits_tts` | 无 |
| `siliconflow_tts` | `default_voice`、`stream` |
| `cosyvoice3_tts` | `stream`、`speed` |

这意味着即使直接调用 `PUT /api/tts/config`，也不能通过 API 覆盖 GPT-SoVITS 的 `ref_audio_path`、`prompt_text`，也不能覆盖 CosyVoice3 的 `client_url`、`sft_dropdown`、参考音频路径等字段。

---

## 6. 敏感配置规则

TTS 配置支持 `${ENV_NAME}` 环境变量占位符。`api_key` 等敏感字段必须使用占位符。

正确：

```yaml
siliconflow_tts:
  api_key: ${SILICONFLOW_API_KEY}
```

错误：

```yaml
siliconflow_tts:
  api_key: sk-真实密钥
```

后端有两层保护：

- 运行时可以读取环境变量展开后的值。
- 保存 YAML 时会尽量保留占位符，不把运行时密钥写回配置文件。
- API 返回配置时会把 `api_key`、`token`、`secret`、`password` mask 成 `********`。

如果你发现真实 key 被写入配置文件，请立即：

1. 删除该 key，改回 `${SILICONFLOW_API_KEY}`。
2. 轮换服务商后台的 API Key。
3. 扫描仓库，确认没有残留明文密钥。

---

## 7. 前端设置页对应关系

设置页路径：

```text
/settings/modules/speech
```

页面区域和配置关系：

| 页面区域 | 对应配置 | 说明 |
| --- | --- | --- |
| TTS Module | `enabled` | 控制是否启用 TTS。 |
| Providers | `tts_model` | 切换当前 Provider。 |
| Auto-play AI replies | `auto_play` | AI 回复完成后是否自动朗读。 |
| Show playback control on home | `show_player_on_home` | 是否在 `/` 显示浮动播放控制。 |
| Playback volume | `volume` | 浏览器播放音量。 |
| Edge Voice model | `edge_tts.voice` | Edge 音色。 |
| Edge Rate | `edge_tts.rate` | Edge 语速。 |
| SiliconFlow Voice model | `siliconflow_tts.default_voice` | SiliconFlow 音色。 |
| SiliconFlow Request streaming mode | `siliconflow_tts.stream` | 请求流式生成。 |
| CosyVoice3 Model | `cosyvoice3_tts.sft_dropdown` | 只读显示当前本地模型/音色配置。 |
| CosyVoice3 Request streaming mode | `cosyvoice3_tts.stream` | 请求 CosyVoice WebUI 流式推理。 |
| CosyVoice3 Speed | `cosyvoice3_tts.speed` | 语速倍率。 |

---

## 8. 运行链路

### 自动朗读

```text
WebSocket chat:complete
  -> 前端确认 enabled && auto_play
  -> POST /api/tts/synthesize
  -> TTSService
  -> 当前 Provider 合成完整音频
  -> 前端生成 ObjectURL
  -> HTMLAudioElement 播放
```

当前 TTS 处理机制是：LLM 回复完整文本后，再喂给 TTS Provider 合成。它不是边生成边播放的实时流式链路。

### 单条消息播放

```text
用户点击 AI 消息的播放按钮
  -> POST /api/tts/synthesize
  -> 播放返回音频
```

### 播放队列

前端 `useAudioPlayer` 维护队列。上一段音频播放结束后，会自动播放下一条。当前提供暂停、继续、停止功能。

---

## 9. API 端点

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/tts/providers` | 获取 Provider 列表、可用性和当前配置。 |
| `GET` | `/api/tts/config` | 获取当前 TTS 配置。敏感值会被 mask。 |
| `PUT` | `/api/tts/config` | 合并保存 TTS 配置。受回写白名单限制。 |
| `POST` | `/api/tts/switch` | 切换当前 Provider。 |
| `GET` | `/api/tts/health` | 获取 TTS 健康状态。 |
| `GET` | `/api/tts/voices` | 获取 Provider 音色列表。 |
| `POST` | `/api/tts/synthesize` | 合成完整音频。 |

切换 Provider 示例：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8430/api/tts/switch" `
  -ContentType "application/json" `
  -Body '{"provider":"edge_tts"}'
```

合成语音示例：

```powershell
Invoke-WebRequest `
  -Method Post `
  -Uri "http://127.0.0.1:8430/api/tts/synthesize" `
  -ContentType "application/json" `
  -Body '{"text":"你好，我是 ATRI。"}' `
  -OutFile "tts-test.mp3"
```

---

## 10. 错误处理和重试

前端调用 `/api/tts/synthesize` 时会自动重试一次，重试条件是：

- 网络错误，或请求没有收到响应。
- HTTP `429`。
- HTTP `5xx`。

不会重试 HTTP `4xx` 配置错误。例如 GPT-SoVITS 参数错误导致的 `400`，应该修正配置，而不是重复请求。

后端 Provider 层不会自行重试。这样可以避免本地模型服务或云端服务在错误配置下被重复请求。

---

## 11. 流式 TTS 现状

当前 ATRI TTS 是完整音频模式：

```text
文本 -> 后端等待 Provider 合成完成 -> 返回完整 Blob -> 前端播放
```

真流式 TTS 的改造复杂度较高，需要同时改：

- 后端路由：从 `Response(bytes)` 改成 `StreamingResponse`。
- TTS 接口：实现 `synthesize_stream()`。
- Provider：逐个适配真实分块输出。
- 前端：从 Blob/ObjectURL 改成 MediaSource 或 Web Audio 分块播放。
- 队列管理：处理“还在下载但已经开始播放”的状态。
- 错误恢复：处理半段音频失败、取消、重试和资源释放。

因此当前建议后续单独作为一个小 Phase 实现，不和 Phase10 的完整文本合成混在一起。

---

## 12. 常见配置示例

### 示例 A：Edge TTS 中文音色

```yaml
tts_model: edge_tts
enabled: true
auto_play: true
edge_tts:
  voice: zh-CN-XiaoxiaoNeural
  rate: +0%
```

适合快速验证。推荐作为默认配置。

### 示例 B：GPT-SoVITS 本地音色

```yaml
tts_model: gpt_sovits_tts
gpt_sovits_tts:
  api_url: http://127.0.0.1:9880/tts
  text_lang: zh
  ref_audio_path: D:/path/to/ref.wav
  prompt_lang: zh
  prompt_text: 参考音频对应文本
  text_split_method: cut5
  media_type: wav
```

适合本地音色复刻。前端不会回写这些字段。

### 示例 C：SiliconFlow CosyVoice2

```yaml
tts_model: siliconflow_tts
siliconflow_tts:
  api_key: ${SILICONFLOW_API_KEY}
  default_model: FunAudioLLM/CosyVoice2-0.5B
  default_voice: FunAudioLLM/CosyVoice2-0.5B:claire
  stream: false
```

适合云端 TTS。前端可以切换 `default_voice` 和 `stream`。

### 示例 D：CosyVoice3 本地 WebUI

```yaml
tts_model: cosyvoice3_tts
cosyvoice3_tts:
  client_url: http://127.0.0.1:50000/
  mode_checkbox_group: 预训练音色
  sft_dropdown: 中文女
  stream: false
  speed: 1.0
```

适合本地 CosyVoice3 部署。前端只读显示 `sft_dropdown`，可以调整 `stream` 和 `speed`。

---

## 13. 自检命令

后端 TTS 测试：

```powershell
cd D:\Coding\GitHub_Resuorse\emotion-robot\atri
uv run ruff check src/tts tests/routes/test_tts.py
uv run python -m mypy src/ --ignore-missing-imports
uv run pytest tests/routes/test_tts.py -v
```

前端检查：

```powershell
cd D:\Coding\GitHub_Resuorse\emotion-robot\atri-webui
npm run type-check
npm run build
```

---

## 14. 常见问题

### Provider 显示 unavailable

原因通常是依赖未安装、本地服务未启动、模型路径错误或 API Key 未配置。

处理方式：

1. 查看 `/settings/modules/speech` 中 Provider 卡片的状态提示。
2. 确认对应 Python 包已安装。
3. 确认本地服务端口或环境变量正确。

### Edge TTS 无法合成

处理方式：

- 确认 `edge-tts` 依赖已安装。
- 确认当前网络能访问 Microsoft Edge TTS 服务。
- 换一个 `voice` 测试。

### GPT-SoVITS 返回 400 或 502

`400` 通常来自 GPT-SoVITS 服务端参数校验失败。ATRI 会把上游错误包装成 `502 Bad Gateway`。

处理方式：

- 检查 `ref_audio_path` 是否存在并能被 GPT-SoVITS 服务访问。
- 检查 `prompt_text` 是否和参考音频匹配。
- 检查 `text_lang`、`prompt_lang`、`text_split_method` 是否是服务端支持的值。
- 确认 GPT-SoVITS 服务正在监听 `api_url`。

### SiliconFlow Provider unavailable

处理方式：

- 设置 `$env:SILICONFLOW_API_KEY`。
- 确认 `api_key` 使用 `${SILICONFLOW_API_KEY}` 占位符。
- 确认 `default_voice` 属于当前 `default_model`。

### CosyVoice3 不显示完整音色列表

这是当前设计。CosyVoice3 是本地 WebUI 调用模式，不是 Edge 那种固定云端音色列表。

前端只读显示当前 `sft_dropdown`。可用值以你启动的 CosyVoice WebUI 下拉框为准。

### TTS 开启但 AI 回复没有自动朗读

处理方式：

1. 确认 `enabled: true`。
2. 确认 `auto_play: true`。
3. 确认前端已重新加载配置。
4. 查看浏览器控制台和后端日志。

---

## 15. 修改建议

优先通过 `/settings/modules/speech` 修改 TTS 配置。只有在以下场景才建议直接编辑 YAML：

- 初次配置环境变量占位符。
- 配置 GPT-SoVITS 参考音频。
- 配置 CosyVoice3 本地 WebUI。
- 批量调整本地 Provider 参数。
- 前端设置页无法启动，需要手工恢复默认 Provider。

直接编辑 YAML 后，重启后端服务让配置生效。

保存配置时不要使用 YAML 格式化工具。当前后端只 patch 指定字段，目标是保留注释、顺序和引号。

