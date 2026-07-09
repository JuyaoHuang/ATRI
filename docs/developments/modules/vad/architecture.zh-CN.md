---
status: active
owner: vad
created: 2026-07-09
updated: 2026-07-09
source:
  - docs/developments/module-design/CN/VAD语音唤醒模块设计.md
  - docs/developments/features/2026-06-vad-realtime-interrupt/README.zh-CN.md
related_code:
  - src/vad/interface.py
  - src/vad/session.py
  - src/vad/service.py
  - src/routes/chat_ws.py
  - frontend/src/composables/useRealtimeVoiceInput.ts
---

# VAD 模块架构

## 模块定位

VAD 在 ATRI 中是“实时音频控制模块”，不是通用音频分析 API。它的目标是把连续麦克风音频转成稳定的语义事件：

- `speech_start`
- `speech_chunk`
- `speech_end`
- `silence`
- `error`

这些事件随后驱动：

- 当前 LLM generation 的打断；
- 旧 TTS 音频的停止和丢弃；
- `speech_end -> ASR -> 新一轮聊天`。

VAD 不负责：

- 单独暴露 `/api/vad/*` REST 路由；
- 存储聊天历史；
- 执行 ASR 转录；
- 决定 TTS 如何合成。

## 分层结构

| 层 | 代码 | 职责 |
| --- | --- | --- |
| Provider 接口层 | `src/vad/interface.py` | 定义 `VADInterface`、`VADResult`、`VADEvent`。 |
| 工厂层 | `src/vad/factory.py` | 注册 VAD Provider 元数据并按名称实例化。 |
| 配置层 | `src/vad/config.py` | 读取 `config/vad_config.yaml` 并做默认值合并。 |
| Session 层 | `src/vad/session.py` | 把 Provider 的原始检测结果防抖为稳定事件。 |
| 服务层 | `src/vad/service.py` | 维护按 `session_id` 归属的 `VADSession`，协调配置和 Provider。 |
| WebSocket 集成层 | `src/routes/chat_ws.py` | 维护 pre-buffer、音频缓存、interrupt 发送状态和后续 ASR/TTS 协调。 |

## 事件流

```text
frontend RealtimeVoiceInput
  -> input:audio:chunk
  -> chat_ws._handle_audio_chunk()
  -> VADService.process_audio(session_id, audio_samples)
  -> VADSession.process_audio()
  -> provider.async_detect_speech()
  -> VADEvent
  -> control:listen-state / control:interrupt / speech buffer / ASR handoff
```

### 前端采集边界

前端 `useRealtimeVoiceInput.ts` 当前通过：

- `getUserMedia()` 获取麦克风；
- `ScriptProcessorNode` 取 PCM 数据；
- 重采样到 16 kHz；
- 发送 `input:audio:chunk` 和 `input:audio:end`。

这部分属于聊天前端能力，不属于 `src/vad/` 本体。VAD 模块从 WebSocket 收到的是已经整理好的 `number[]` 音频片段。

## Session 与防抖

### `VADSession`

`VADSession` 只关心“单条连接上的稳定语义”。它维护：

- `state`: `idle` / `active`
- `_speech_hits`
- `_silence_misses`

并把 Provider 的 `VADResult` 转成稳定 `VADEvent`。

### 防抖归属

当前两个 Provider 的防抖归属不同：

| Provider | 原始判断 | 防抖归属 |
| --- | --- | --- |
| `fake` | 单 chunk 能量阈值 | 主要由 `VADSession` 的 `required_hits` / `required_misses` 完成。 |
| `silero_vad` | 32 ms 窗口 + 概率/分贝平滑 + Provider 内部 hits/misses | `VADService` 会把 session 级 hits/misses 设为 1，避免重复防抖。 |

这也是为什么“VAD 的防抖参数”不能只从旧设计文档看一层，而要区分 Provider 内部和 session 外层。

## `chat_ws` 上的连接态

真正驱动打断链路的连接态在 `WebSocketVADState`，而不在 `src/vad/`：

- `session_id`
- `interrupt_sent`
- `current_chat_task`
- `current_generation_id`
- `current_tts_generation_id`
- `audio_buffer`
- `pre_buffer`

它负责把 VAD 事件变成聊天语义：

- `speech_start`：打断当前 generation 和 TTS；
- `speech_chunk`：继续积累音频；
- `speech_end`：取出缓存音频交给 ASR；
- `input:audio:end` / 连接关闭：重置 session 和缓存。

## Provider 生命周期

`VADService` 会按 `session_id` 缓存 `VADSession`。一个 session 一旦建立：

- 后续音频 chunk 会复用同一个 Provider 和状态机；
- Provider 切换或配置更新时，`_sessions` 全部清空；
- `input:audio:end`、错误恢复和 WebSocket close 都会调用 `reset_session()`。

与 ASR 不同，VAD 当前没有“持久 Provider 缓存”和“预加载”层，因为它主要服务于实时连接内状态。

## API 与事件边界

### 当前公开边界

VAD 当前只通过聊天 WebSocket 暴露语义事件：

- `control:listen-state`
- `control:interrupt`

### 当前不公开的边界

尽管 `VADService` 提供了 `get_config()`、`update_config()`、`switch_provider()` 等方法，但当前仓库没有对应的 `src/routes/vad.py`。这些方法是内部服务能力，不应被误写成“已有独立 VAD REST API”。

## 文档关系

- 旧设计文档强调“语音唤醒模块”概念，并提出单独 `/vad/detect`；当前实现已经收敛到聊天 WebSocket 集成。
- feature 文档记录了 M0-M6 过程和验收；本页只保留长期成立的结构边界。
