---
status: active
owner: asr
created: 2026-07-09
updated: 2026-07-09
source:
  - ../../module-design/CN/ASR模块设计文档.md
  - src/asr/interface.py
  - src/asr/factory.py
  - src/asr/service.py
  - src/routes/asr.py
  - src/routes/chat_ws.py
related_code:
  - src/asr/interface.py
  - src/asr/factory.py
  - src/asr/service.py
  - src/asr/config.py
  - src/routes/asr.py
  - src/routes/chat_ws.py
---

# ASR 模块总设计

本文把 `src/asr/` 的整体设计接起来。现有文档已经分别讲了架构、接口、配置和 Provider 矩阵，但还需要一页说明：

1. ASR 在整个系统中的位置。
2. 浏览器语音、上传转录、VAD 自动接管为什么共用一套模块。
3. 本地 Provider 常驻缓存和上传 WAV 契约为什么是长期设计的一部分。

## 模块定位

当前 ASR 模块不是单一的“上传文件转文字”工具，而是系统的统一语音识别入口。它同时服务三条链路：

- 浏览器原生 Web Speech 识别
- 后端上传文件转录
- VAD `speech_end` 后的自动接管转录

在系统中的位置可以概括为：

```text
audio input
  -> ASR provider selection
  -> backend transcription or browser streaming
  -> transcript
  -> chat pipeline
```

## 设计目标

结合旧设计文档、当前代码和近期 VAD 联调日志，长期目标已经收敛为 5 条：

1. 用统一抽象承接不同来源的语音输入。
2. 保持浏览器路径和后端路径的边界清晰，但共享同一 Provider 能力模型。
3. 让本地大模型 Provider 可以常驻缓存，减少重复初始化。
4. 让上传 WAV 契约严格可验证，减少联调时的“听起来像 WAV”但实际不匹配问题。
5. 让 ASR 故障不会破坏聊天主链路和 WebSocket 可用性。

## 模块组成

当前 `src/asr/` 可以稳定拆成五部分：

| 组件 | 代码 | 职责 |
| --- | --- | --- |
| 接口层 | `interface.py` | 定义 Provider 契约与默认 WAV 适配逻辑。 |
| 工厂层 | `factory.py` | 注册 Provider 和能力元数据。 |
| 配置层 | `config.py` | 读写 `config/asr_config.yaml`。 |
| 异常层 | `exceptions.py` | 统一配置错误、Provider 不可用、转录失败。 |
| 服务层 | `service.py` | 选择 Provider、复用本地实例、执行转录。 |

对外正式入口有两处：

- `src/routes/asr.py`：HTTP 配置与上传转录
- `src/routes/chat_ws.py`：VAD 自动接管后的内部使用

## 三条正式链路

### 1. 浏览器 Web Speech 链路

当前当 Provider 声明 `supports_browser_streaming=true` 时，前端优先走浏览器原生识别：

- 后端不直接接收音频内容；
- 前端本地得到 transcript；
- transcript 回填输入框或进入聊天。

这条链路说明：ASR 模块并不总是等于“后端跑模型”。

### 2. 上传转录链路

当前 `POST /api/asr/transcribe` 是正式后端上传转录入口：

- 前端上传音频文件；
- `ASRService.transcribe_audio()` 解析当前或指定 Provider；
- 默认按 16 kHz WAV 契约适配；
- 返回 `{ provider, text }`。

### 3. VAD 自动接管链路

近期演化里最重要的变化，是 VAD `speech_end` 后会自动：

- 把 `audio_buffer` 编码成 `realtime-vad.wav`
- 调 `ASRService.transcribe_audio()`
- 将 transcript 作为新一轮聊天输入

因此 ASR 模块已经不只是“设置页和手动录音”的附属模块，而是实时语音主链路的一环。

## Provider 能力模型

当前每个 Provider 至少要回答两个问题：

1. `supports_backend_transcription`
2. `supports_browser_streaming`

这两个能力位比“Provider 名称”更重要，因为它们直接决定前端和后端走哪条链路。

长期约束：

- 不是所有 Provider 都能接后端上传；
- 不是所有 Provider 都应该暴露浏览器流式识别；
- `web_speech_api` 是浏览器路径的特殊 Provider，不应被误写成后端模型。

## 上传 WAV 契约

当前默认上传适配器要求：

- PCM WAV
- 16 kHz
- 单声道
- 8/16/32 bit 支持

而且会显式校验前端声明的：

- `sample_rate`
- `channels`
- `encoding`

这条契约已经从近期联调中沉淀下来。它的意义是：

- 前后端对音频协议的理解可验证；
- 出错时能快速定位是“录音参数不匹配”而不是“模型效果不好”；
- 本地 Provider 可以复用同一适配入口。

## 本地 Provider 常驻缓存

当前 `ASRService` 的一个核心设计点，是允许本地 Provider 常驻：

- `_provider_cache`
- `_provider_locks`
- `_cache_lock`

长期意义：

- 本地模型加载成本高，不应每次请求都重新初始化；
- 同一 Provider 可能不安全并发，因此要串行转录；
- 这条行为应该由服务层统一处理，而不是每个路由或 Provider 自己重复实现。

## 配置所有权

当前 ASR 配置中，前端和后端各自拥有不同字段：

- 前端可写：
  - 活跃 Provider
  - 少量 Provider 白名单字段
  - auto_send 相关 UX 行为
- 后端专有：
  - `persistent_provider`
  - `preload_provider`
  - 敏感凭据

长期约束是：前端只能调系统允许它写的那一小部分，不应把整个 `asr_config.yaml` 镜像成前端编辑器。

## 与 VAD 的关系

VAD 负责“什么时候应该转录”，ASR 负责“如何转录”。

当前稳定边界：

- `speech_end` 之前，ASR 不工作；
- `speech_end` 之后，ASR 只接收一段完成的 speech audio；
- transcript 输出后，聊天链路重新接管。

这意味着 ASR 和 VAD 是顺序协作关系，而不是同一状态机。

## 与聊天链路的关系

ASR 输出的 transcript 当前有两种去向：

1. 单次语音输入：
   - 回填输入框
2. VAD 自动接管：
   - 直接作为聊天输入启动新 generation

因此 ASR 模块对上游来说返回的只是文本，不自己决定是否立即发送聊天。

## 与旧设计文档的取舍

旧 `ASR模块设计文档.md` 中，已经被当前实现吸收并仍然成立的包括：

- 抽象接口 + 装饰器工厂
- Provider 能力差异
- 配置驱动
- 独立异常层

不再应被当作当前事实的包括：

- 独立 ASR WebSocket
- 统一 `transcribe_stream()` 主路径
- 数据库或缓存等未落地优化成为默认行为

因此当前 ASR 总设计更强调“已实现的三条链路”和“上传契约 + 常驻缓存”这两个现实。

## 相关文档

- [architecture.zh-CN.md](architecture.zh-CN.md)
- [interface.zh-CN.md](interface.zh-CN.md)
- [config.zh-CN.md](config.zh-CN.md)
- [provider-matrix.zh-CN.md](provider-matrix.zh-CN.md)
