---
status: active
owner: asr
created: 2026-07-09
updated: 2026-07-09
source:
  - docs/developments/module-design/CN/ASR模块设计文档.md
related_code:
  - src/asr/interface.py
  - src/asr/factory.py
  - src/asr/service.py
  - src/routes/asr.py
  - src/routes/chat_ws.py
  - frontend/src/composables/useVoiceInput.ts
---

# ASR 模块架构

## 模块定位

ASR 模块负责把“已经采集好的音频”转成文本，并为前端设置页提供 Provider 列表、健康状态和配置读写能力。

ASR 负责：

- 维护 `src/asr/` Provider 注册表和统一接口。
- 按配置选择当前活跃 Provider。
- 接收上传音频并调用后端可转录 Provider。
- 为浏览器侧 `web_speech_api` 暴露配置和能力元数据。
- 在 VAD `speech_end` 后为聊天 WebSocket 提供一次后端转录能力。

ASR 不负责：

- 采集麦克风、录音或浏览器权限申请。
- 判断语音何时开始、何时结束，这属于 VAD。
- 决定转录文本是否自动发送到聊天，这属于前端 `InputBox` 和实时语音链路。
- 维护独立 ASR WebSocket 协议。当前没有 `/ws/asr` 或等价路由。

## 分层结构

| 层 | 代码 | 职责 |
| --- | --- | --- |
| 接口层 | `src/asr/interface.py` | 定义 `ASRInterface`、`ASRHealth` 和上传音频适配规则。 |
| 工厂层 | `src/asr/factory.py` | 通过装饰器注册 Provider，并暴露静态元数据。 |
| 配置层 | `src/asr/config.py` | 读取 `config/asr_config.yaml`，做默认值合并、磁盘回写和敏感字段保护。 |
| 服务层 | `src/asr/service.py` | 协调配置、健康检查、Provider 切换、本地模型缓存和转录入口。 |
| 路由层 | `src/routes/asr.py` | 暴露 `/api/asr/*` REST 接口。 |
| 聊天集成层 | `src/routes/chat_ws.py` | 在 VAD `speech_end` 后把缓存语音交给 `ASRService`，并发送 `output:asr:transcript`。 |

## 三条实际链路

### 1. 浏览器 Web Speech 链路

```text
frontend SpeechRecognition
  -> frontend transcript callback
  -> InputBox auto-send or manual send
```

这条链路中，后端 ASR 模块只提供：

- `web_speech_api` 的配置项；
- Provider 元数据中的 `supports_browser_streaming=true`；
- 设置页的 Provider/health/config API。

真正的识别发生在浏览器，`src/asr/providers/web_speech_api.py` 只是一个“配置型 Provider”，不会接收音频上传。

### 2. 后端上传转录链路

```text
frontend VoiceInput / settings test
  -> POST /api/asr/transcribe
  -> ASRService.transcribe_audio()
  -> selected provider
  -> ASRTranscriptionResponse { provider, text }
```

这是普通按钮式语音输入和设置页测试录音使用的链路。前端先决定使用浏览器识别还是后端上传：

- `supports_browser_streaming=true` 时，`useVoiceInput.ts` 优先走 Web Speech API。
- 其他 Provider 通过 `MediaRecorder/WAV` 路径上传到 `/api/asr/transcribe`。

### 3. VAD 自动接管链路

```text
input:audio:chunk
  -> src/routes/chat_ws.py
  -> VADService.process_audio()
  -> speech_end
  -> _float_audio_to_wav_bytes()
  -> ASRService.transcribe_audio()
  -> output:asr:transcript
  -> backend starts next chat generation
```

这条链路说明 ASR 是 VAD 实时打断后的下游模块，而不是实时控制模块本身。VAD 负责“何时交给 ASR”，ASR 只负责“如何把完整语音片段转成文本”。

## Provider 生命周期

### 注册

所有 Provider 通过 `src/asr/providers/__init__.py` 导入时完成装饰器注册，当前注册事实以 `ASRFactory.available()` 为准。

### 实例化

`ASRService` 在每次请求或切换 Provider 时通过 `ASRFactory.create(name, **provider_config)` 构造实例。

### 本地模型缓存

当同时满足以下条件时，`ASRService` 会缓存 Provider 实例并复用：

- `persistent_provider=true`；
- Provider 元数据 `provider_type == "local"`；
- `supports_backend_transcription=true`；
- Provider 不是 `web_speech_api`。

缓存后的本地 Provider 会配合 `asyncio.Lock` 串行转录，避免多个请求同时复用同一个识别器时出现线程安全问题。

### 预加载

`preload_provider=true` 时，应用启动后可以调用 `preload_active_provider()` 提前加载当前本地模型。是否真的预加载，仍受“仅本地、仅后端可转录 Provider”约束。

## 音频契约

`ASRInterface` 的核心本地契约是“16 kHz、单声道、float32 风格的数值数组”。默认上传适配器支持：

- WAV 封装；
- 8/16/32-bit PCM；
- 多声道自动降混为单声道；
- 通过 `source`、`sample_rate`、`channels`、`encoding` 做上传元数据校验。

但默认适配器不负责任意格式解码。当前代码中：

- `faster_whisper` 对非 WAV 浏览器格式做了临时文件兜底；
- `openai_whisper` 直接按文件上传给云接口；
- `sherpa_onnx_asr` 和 `whisper_cpp` 仍依赖默认 WAV 适配；
- `web_speech_api` 不接受上传。

## API 与事件边界

### REST API

`src/routes/asr.py` 当前公开：

- `GET /api/asr/providers`
- `GET /api/asr/config`
- `PUT /api/asr/config`
- `POST /api/asr/switch`
- `GET /api/asr/health`
- `POST /api/asr/transcribe`

### WebSocket 事件

ASR 模块没有独立 WebSocket 路由。当前唯一稳定的 ASR 相关聊天事件是：

- `output:asr:transcript`

它由 `src/routes/chat_ws.py` 在 VAD `speech_end` 后发送，而不是由 `src/routes/asr.py` 发送。

## 文档关系

- 旧设计文档曾把“独立 ASR WebSocket”和“统一流式转录接口”作为主线；当前代码没有落这条路径。
- 旧文档把 `web_speech_api` 视为纯前端能力；当前实现中它仍是前端能力，但后端新增了一个配置型 Provider 作为统一设置入口。
- 与一次性开发过程、测试结果和打断语义相关的事实，继续放在 VAD feature/wiki 文档，不在本页重复流水。
