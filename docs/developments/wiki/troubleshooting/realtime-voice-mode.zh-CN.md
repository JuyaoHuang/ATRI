---
status: active
owner: vad
created: 2026-07-09
updated: 2026-07-09
source: docs/configs/CN/实时语音模式使用说明.md
related_code:
  - src/routes/chat_ws.py
  - src/vad/
  - src/asr/
  - frontend/src/
---

# 实时语音模式排障

本文是准备迁移到 GitHub Wiki 的实时语音排障稿。使用入口和推荐配置见 [实时语音模式使用说明](../../../configs/CN/实时语音模式使用说明.md)。

## 判断是否连到业务 WebSocket

业务 WebSocket 是：

```text
/ws
```

如果 DevTools 中看到：

```text
ws://localhost:5200/
```

那通常是 Vite HMR 通道，不是聊天业务 WebSocket。

应在 Chrome DevTools 中进入：

```text
Network -> WS -> /ws -> Messages
```

## 正常消息顺序

打开实时语音后，说一句话，通常能看到：

```text
input:audio:chunk
control:listen-state
control:interrupt
output:asr:transcript
output:chat:chunk
```

如果在 AI 正在输出时开口，还应看到：

```text
output:chat:interrupted
```

## 没有 ASR 自动聊天

先检查 `config/asr_config.yaml`：

```yaml
asr_model: sherpa_onnx_asr
```

如果当前是：

```yaml
asr_model: web_speech_api
```

这是预期限制。`web_speech_api` 是浏览器侧识别，后端不能拿它做 VAD 后的自动 ASR。

## 没有打断当前回复

用户开口时应看到：

```text
control:interrupt
```

如果 AI 正在输出，旧 `generation_id` 不应继续产生普通完整回复。排查顺序：

1. 确认实时语音 button 已开启。
2. 确认浏览器正在发送 `input:audio:chunk`。
3. 确认后端持续返回 `control:listen-state`。
4. 调低 VAD 开口阈值，或检查麦克风权限。

## 说话结束太快

Silero 默认静默结束理论时间约为：

```text
required_misses = 24
24 * 32 ms = 768 ms
```

连续说话被切分时，可以增大：

```yaml
silero_vad:
  required_misses: 30
```

## 误触发太多

优先调高：

```yaml
silero_vad:
  prob_threshold: 0.5
  db_threshold: 65
```

也可以适当调高 `required_hits`，让开口判定更保守。

## ScriptProcessorNode 弃用警告

浏览器控制台出现 `ScriptProcessorNode` 弃用警告，不代表功能失败。

当前前端采集实现仍可能使用该 API。迁移到 `AudioWorklet` 是后续优化，不是判断实时语音是否可用的必要条件。

## 当前限制

- TTS 仍可走 REST 完整音频，除非启用分段流式链路。
- VAD 打断会停止旧 TTS 播放，并丢弃旧 generation 的后续 TTS 结果。
- 已发出的 REST TTS API 请求不做 Provider 级取消。
- `web_speech_api` 不能用于后端 VAD 自动 ASR。
- 当前实时音频 payload 是 JSON float array，后续可评估二进制帧优化。

## 相关文档

- [实时语音模式使用说明](../../../configs/CN/实时语音模式使用说明.md)
- [VAD 配置说明](../../../configs/CN/VAD配置说明.md)
- [VAD 实时打断开发日志](../../features/2026-06-vad-realtime-interrupt/dev-log.zh-CN.md)
