---
status: active
owner: vad
created: 2026-07-09
updated: 2026-07-09
source:
  - docs/developments/features/2026-06-vad-realtime-interrupt/README.zh-CN.md
  - docs/developments/features/2026-06-vad-realtime-interrupt/dev-log.zh-CN.md
  - docs/developments/wiki/development-blogs/2026-07-08-vad-realtime-interrupt.zh-CN.md
related_code:
  - src/routes/chat_ws.py
  - src/vad/service.py
  - src/asr/service.py
  - src/tts/segment_manager.py
  - frontend/src/composables/useRealtimeVoiceInput.ts
  - frontend/src/composables/useWebSocket.ts
  - frontend/src/composables/useAudioPlayer.ts
---

# VAD 实时打断边界

本页沉淀 VAD 第一版已经稳定下来的“实时打断语义”。它不是 feature 流水，而是跨版本应继续保持的边界。

## 稳定协议

| 方向 | 消息 | 作用 |
| --- | --- | --- |
| 前端 -> 后端 | `input:audio:chunk` | 发送 16 kHz、mono、PCM float array 风格的音频片段。 |
| 前端 -> 后端 | `input:audio:end` | 本轮实时音频输入结束，重置 session 和缓冲。 |
| 后端 -> 前端 | `control:listen-state` | 通知 `speech_start`、`speech_chunk`、`speech_end`、`silence` 或 `error`。 |
| 后端 -> 前端 | `control:interrupt` | 告知用户已开始说话，当前播放和旧 generation 应立即失效。 |
| 后端 -> 前端 | `output:asr:transcript` | `speech_end` 后端 ASR 成功后的最终 transcript。 |
| 后端 -> 前端 | `output:chat:interrupted` | 旧 generation 被打断后，返回已经发给前端的半截回复。 |

## `speech_start` 的长期语义

`speech_start` 一旦成立，后端会在同一条控制路径中完成以下动作：

1. 从 `pre_buffer` 开始缓存本轮有效语音。
2. 发送 `control:listen-state(state=speech_start)`。
3. 如果当前 speaking burst 还没发过 interrupt，则发送一次 `control:interrupt`。
4. 使当前 `generation_id` 失效。
5. 取消当前聊天 task。
6. 打断当前 `TTSSegmentManager`，使旧 `output:audio:*` 结果可以被丢弃。

如果旧 generation 已经向前端发送过可见文本，后端还会：

7. 以“已经发送给前端的文本”为准构造 interrupted snapshot。
8. 持久化 `interrupted=true` 的审计历史。
9. 发送 `output:chat:interrupted`。

## `speech_chunk` 的长期语义

`speech_chunk` 表示当前 speaking burst 仍在继续：

- 音频继续追加到 `audio_buffer`；
- `interrupt_sent` 保持为真；
- 同一轮连续说话不会重复发送 `control:interrupt`。

这条约束保证前端不会在同一轮说话里反复清空播放队列。

## `speech_end` 的长期语义

`speech_end` 成立后：

1. 后端发送 `control:listen-state(state=speech_end)`。
2. 清理 `pre_buffer`。
3. 取出当前 `audio_buffer` 作为完整语音片段。
4. 重置 `interrupt_sent=false`，允许下一轮说话再次触发打断。
5. 若音频为空或小于 `min_speech_ms`，直接返回 listen error，不进入 ASR。
6. 否则将音频编码成 `realtime-vad.wav` 并调用 `ASRService.transcribe_audio()`。
7. ASR 成功后发送 `output:asr:transcript`。
8. 后端自动把 transcript 作为新一轮聊天输入启动新的 generation。

这意味着：

- 前端收到 `output:asr:transcript` 时只负责展示，不应再次调用 `sendMessage()`；
- VAD 的“结束”定义的是交给 ASR 的时机，而不是前端是否已经看到新的 AI 回复。

## 与聊天历史和记忆的边界

当前稳定语义是：

- `partial_reply` 只表示“后端已经发送给前端的文本”；
- interrupted AI 消息可以展示、可以审计；
- interrupted AI 消息不进入普通记忆轮次，不触发短期记忆压缩，也不写入长期记忆；
- 普通 `output:chat:complete` 仍是完整 AI 回复的权威完成信号。

因此第一版**没有**引入 `heard_response`，也不把“用户实际听到多少 TTS”回写给记忆系统。

## 与 TTS 的边界

VAD 只负责让旧 generation 失效，不负责决定 TTS 怎样合成。长期边界是：

- TTS 是 LLM 文本回复的下游消费者；
- `speech_start` 会让旧 generation 的自动音频结果可丢弃；
- 前端 `useAudioPlayer` 按 `generation_id` 丢弃旧自动音频；
- `output:audio:*` 的生命周期不反向修改 `partial_reply`、聊天历史或记忆。

这也是为什么 TTS 分段流式化被拆成独立 feature，而不是并入 VAD 模块文档。

## 错误和关闭边界

### 处理错误

Provider 不可用、配置无效或处理失败时：

- 后端发送 `control:listen-state(state=error, code=..., message=...)`；
- 清空连接上的音频缓存；
- 重置 VAD session；
- 聊天 WebSocket 保持连接。

### `input:audio:end`

前端主动停止实时语音时：

- 重置 VAD session；
- 清空 `audio_buffer` 和 `pre_buffer`；
- 发送一个 `speech_end` 风格的 listen-state 作为 UI 收口；
- 不会自动触发 ASR。

### WebSocket close

连接关闭时：

- `vad_service.reset_session(session_id)`；
- 当前 TTS generation 被中断；
- 轻量级连接态释放；
- 不保留跨连接的 VAD session。

## 当前明确不做的事

- 不提供独立的 VAD REST API。
- 不让浏览器回传 `heard_response`。
- 不把 Web Speech API 伪装成 VAD model。
- 不把 TTS provider 的原生流式能力当作 VAD 模块职责。

## 文档关系

- feature 目录解释“这次开发是怎么做成的”。
- 本页只回答“以后改代码时哪些语义不能被悄悄改掉”。
