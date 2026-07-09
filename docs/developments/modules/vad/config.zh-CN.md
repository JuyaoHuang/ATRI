---
status: active
owner: vad
created: 2026-07-09
updated: 2026-07-09
source:
  - docs/developments/module-design/CN/VAD语音唤醒模块设计.md
  - docs/developments/features/2026-06-vad-realtime-interrupt/dev-log.zh-CN.md
related_code:
  - config.yaml
  - config/vad_config.yaml
  - src/vad/config.py
  - src/vad/service.py
  - src/routes/chat_ws.py
---

# VAD 配置与运行边界

用户侧说明见 [VAD配置说明](../../../configs/CN/VAD配置说明.md)。本文只记录开发侧配置语义。

## 配置入口

根配置通过 `config.yaml` 引用：

```yaml
vad_config: config/vad_config.yaml
```

运行时加载路径：

```text
config.yaml
  -> config/vad_config.yaml
  -> load_config()
  -> config["vad"]
  -> VADConfigStore / VADService
```

当前没有 VAD 配置 REST 路由，因此 `config/vad_config.yaml` 是外部可维护的主入口。

## 根字段

| 字段 | 作用 | 当前行为 |
| --- | --- | --- |
| `enabled` | 是否启用后端 VAD | `false` 时 `VADService.process_audio()` 直接返回带 `disabled=true` 的 `silence` 事件。 |
| `vad_model` | 当前 Provider 名称 | 必须是 `VADFactory.available()` 中的值。 |
| `sample_rate` | WebSocket 音频链路的目标采样率 | 当前聊天链路默认按 16 kHz 发送和处理。 |
| `pre_buffer_ms` | `speech_start` 前保留的滚动音频窗口 | 由 `chat_ws` 在真正开始缓冲本轮语音前补回句首。 |
| `min_speech_ms` | 可选的最短有效语音长度 | 不是 `DEFAULT_VAD_CONFIG` 的默认字段，但 `chat_ws` 会读取；过短片段会在 ASR 前被判定为 `speech_too_short`。 |

## Provider 块

### `fake`

| 字段 | 作用 |
| --- | --- |
| `speech_threshold` | 以 chunk 最大绝对振幅做阈值判断。 |
| `required_hits` | session 层需要连续多少次命中才产生 `speech_start`。 |
| `required_misses` | session 层需要连续多少次未命中才产生 `speech_end`。 |

`fake` 适合测试和开发联调，不依赖模型。

### `silero_vad`

| 字段 | 作用 |
| --- | --- |
| `sample_rate` | Provider 期望的采样率。当前实现只支持 `8000` 或 `16000`。 |
| `prob_threshold` | Silero 输出概率阈值。 |
| `db_threshold` | 基于 int16 RMS 估算的音量门槛。 |
| `required_hits` | Provider 内部从 idle 进入 active 的连续命中次数。 |
| `required_misses` | Provider 内部从 active 回到 idle 的连续未命中次数。 |
| `smoothing_window` | 概率和分贝的滑动平均窗口。 |

`silero_vad` 的 `required_hits` / `required_misses` 发生在 Provider 内部，`VADService` 识别到该 Provider 声明 `uses_internal_debounce=True` 后，会把 session 级防抖降到 1/1。

## 防抖归属

这是 VAD 配置里最容易被旧文档误导的地方：

```text
fake
  -> provider 只做单 chunk 阈值判断
  -> session 完成 hits/misses 防抖

silero_vad
  -> provider 自带窗口平滑和 hits/misses
  -> session 不再叠加一层同义防抖
```

因此不能简单把 `required_hits`、`required_misses` 视为统一的根级配置语义。

## 与聊天链路的关系

`chat_ws.py` 当前会读取 VAD 根配置中的三个值：

- `sample_rate`
- `pre_buffer_ms`
- `min_speech_ms`

并据此决定：

- pre-buffer 多长；
- 何时把缓存音频转成 WAV；
- 是否因为片段太短而直接拒绝 ASR。

`src/vad/` 本身不做 WAV 编码，也不做 ASR 调用。

## 错误与恢复

VAD Provider 或配置错误发生时：

- `chat_ws` 会发送 `control:listen-state` 的 `state=error`；
- 清空当前连接的 `audio_buffer` 和 `pre_buffer`；
- 调用 `vad_service.reset_session(session_id)`；
- 不会因此关闭整个聊天 WebSocket。

因此“配置错了导致整个聊天通道断开”不是当前设计。

## 文档关系

- 旧文档中的 `orig_sr`、`target_sr` 讨论主要来自 OLV；当前 ATRI 暴露给用户的主字段是根级 `sample_rate` 和 `silero_vad.sample_rate`。
- 配置说明面向用户介绍如何调参数；本页强调的是这些参数到底由哪一层消费。
