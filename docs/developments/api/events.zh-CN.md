---
status: active
owner: api
created: 2026-07-09
updated: 2026-07-09
related_code:
  - src/routes/chat_ws.py
  - frontend/src/utils/websocket.ts
  - frontend/src/composables/useWebSocket.ts
  - frontend/src/composables/useRealtimeVoiceInput.ts
---

# WebSocket 事件字典

这份字典按事件名说明当前 `/ws` 协议。字段定义以源码为准，示例只展示稳定字段；未列出的字段不应假设存在。

统一消息信封：

```json
{
  "type": "event-name",
  "data": {}
}
```

## `input:*`

### `input:text`

方向：客户端 -> 服务端

用途：提交一轮文本聊天输入。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `text` | string | 是 | 用户文本。空字符串会被拒绝。 |
| `chat_id` | string | 是 | 目标聊天 ID。 |
| `character_id` | string | 是 | 目标角色 ID。 |
| `client_context` | object | 否 | 前端上下文。当前前端会发送本地时间信息。 |

示例：

```json
{
  "type": "input:text",
  "data": {
    "text": "今天有点累",
    "chat_id": "chat_xxx",
    "character_id": "atri",
    "client_context": {
      "datetime": {
        "iso": "2026-07-09T08:00:00.000Z",
        "local": "2026/7/9 16:00:00",
        "time_zone": "Asia/Shanghai",
        "utc_offset": "UTC+08:00"
      }
    }
  }
}
```

### `input:audio:chunk`

方向：客户端 -> 服务端

用途：持续上传实时语音片段，驱动 VAD 和后端 ASR。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | string | 是 | 当前聊天 ID。 |
| `character_id` | string | 是 | 当前角色 ID。 |
| `audio` | number[] | 是 | 非空音频采样数组。 |
| `seq` | integer | 否 | 前端音频分片序号。 |

示例：

```json
{
  "type": "input:audio:chunk",
  "data": {
    "chat_id": "chat_xxx",
    "character_id": "atri",
    "audio": [0.01, -0.02, 0.03],
    "seq": 12
  }
}
```

### `input:audio:end`

方向：客户端 -> 服务端

用途：通知本轮实时录音结束，重置当前连接上的 VAD 会话。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | string | 建议是 | 当前聊天 ID。 |
| `character_id` | string | 建议是 | 当前角色 ID。 |

说明：

- 当前前端始终发送这两个字段。
- 服务端保留了同连接上下文回退，但新客户端不应依赖这种兼容行为。

示例：

```json
{
  "type": "input:audio:end",
  "data": {
    "chat_id": "chat_xxx",
    "character_id": "atri"
  }
}
```

## `output:*`

### `output:chat:chunk`

方向：服务端 -> 客户端

用途：流式输出一段新的 LLM 文本。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `chunk` | string | 是 | 本次新增文本片段。 |
| `chat_id` | string | 是 | 所属聊天。 |
| `character_id` | string | 是 | 所属角色。 |
| `generation_id` | string | 是 | 本轮生成 ID。 |

示例：

```json
{
  "type": "output:chat:chunk",
  "data": {
    "chunk": "那我们先慢一点说。",
    "chat_id": "chat_xxx",
    "character_id": "atri",
    "generation_id": "gen_xxx"
  }
}
```

### `output:chat:complete`

方向：服务端 -> 客户端

用途：声明本轮文本回复已经完整结束。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `full_reply` | string | 是 | 完整 AI 回复。 |
| `chat_id` | string | 是 | 所属聊天。 |
| `character_id` | string | 是 | 所属角色。 |
| `generation_id` | string | 是 | 本轮生成 ID。 |

说明：发送这一事件前，后端已经完成本轮消息持久化和记忆提交。

### `output:chat:interrupted`

方向：服务端 -> 客户端

用途：声明上一轮回复被 VAD 打断，且 partial reply 已被后端记账。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | string | 是 | 所属聊天。 |
| `character_id` | string | 是 | 所属角色。 |
| `generation_id` | string | 是 | 被打断的生成 ID。 |
| `partial_reply` | string | 是 | 已经发给前端的半截回复。 |
| `interrupted` | boolean | 是 | 当前固定为 `true`。 |
| `reason` | string | 是 | 当前稳定值为 `vad_speech_start`。 |

### `output:asr:transcript`

方向：服务端 -> 客户端

用途：通知后端 ASR 的转写结果。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | string | 是 | 所属聊天。 |
| `character_id` | string | 是 | 所属角色。 |
| `text` | string | 是 | 转写文本。 |
| `is_final` | boolean | 是 | 当前后端自动提交路径固定为 `true`。 |
| `generation_id` | string | 否 | 预分配给这轮 ASR 结果的生成 ID。 |
| `seq` | integer | 否 | 来自最近音频片段的序号。 |

说明：后端在发出这条事件后，通常会立刻内部启动对应的一轮聊天生成。

### `output:audio:segment`

方向：服务端 -> 客户端

用途：下发一个完整的自动 TTS 音频段。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | string | 是 | 所属聊天。 |
| `character_id` | string | 是 | 所属角色。 |
| `generation_id` | string | 是 | 绑定的聊天生成 ID。 |
| `segment_id` | string | 是 | 该音频段唯一 ID。 |
| `sequence` | integer | 是 | 同一 generation 内的顺序号。 |
| `audio` | string | 是 | base64 编码音频字节。 |
| `media_type` | string | 是 | 音频 MIME 类型。 |
| `display_text` | string | 是 | 前端已显示的原始文本段。 |
| `tts_text` | string | 是 | 实际送入 TTS 的清洗后文本。 |

### `output:audio:complete`

方向：服务端 -> 客户端

用途：声明某个 generation 不会再收到新的音频段。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | string | 是 | 所属聊天。 |
| `character_id` | string | 是 | 所属角色。 |
| `generation_id` | string | 是 | 绑定的聊天生成 ID。 |
| `last_sequence` | integer 或 `null` | 是 | 最后一个 sequence。若本轮没有可朗读音频段，则为 `null`。 |

注意：这不是“播放结束”，只是“后端发送结束”。

### `output:audio:error`

方向：服务端 -> 客户端

用途：声明某个音频段失败或被跳过。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | string | 是 | 所属聊天。 |
| `character_id` | string | 是 | 所属角色。 |
| `generation_id` | string | 是 | 绑定的聊天生成 ID。 |
| `segment_id` | string | 是 | 失败的音频段 ID。 |
| `sequence` | integer | 是 | 被跳过的顺序号。 |
| `code` | string | 是 | 错误码。 |
| `message` | string | 是 | 人类可读错误描述。 |

当前常见 `code`：

- `tts_synthesis_failed`
- `tts_invalid_audio`
- `tts_segment_queue_full`

## `control:*`

### `control:listen-state`

方向：服务端 -> 客户端

用途：报告 VAD 监听状态、概率和错误。

基础字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | string | 是 | 所属聊天。 |
| `character_id` | string | 是 | 所属角色。 |
| `state` | string | 是 | `speech_start`、`speech_chunk`、`speech_end`、`silence`、`error`。 |

可选字段：

| 字段 | 类型 | 出现场景 | 说明 |
| --- | --- | --- | --- |
| `is_speech` | boolean | 正常 VAD 事件 | 当前分片是否判定为语音。 |
| `seq` | integer | 前端发送了 `seq` 时 | 回传关联序号。 |
| `probability` | number | provider 提供概率时 | 语音概率。 |
| `energy` | number | provider 提供能量时 | 音频能量。 |
| `disabled` | boolean | VAD 被标记为禁用时 | 当前事件来自禁用路径。 |
| `reason` | string | `state=error` 且 provider 提供时 | 额外错误原因。 |
| `code` | string | `state=error` | 稳定错误码。 |
| `message` | string | `state=error` | 人类可读错误信息。 |

常见 `code`：

- `vad_provider_unavailable`
- `vad_config_error`
- `vad_processing_failed`
- `backend_asr_unavailable`
- `asr_transcription_failed`
- `empty_speech_audio`
- `speech_too_short`
- `empty_asr_transcript`

错误示例：

```json
{
  "type": "control:listen-state",
  "data": {
    "chat_id": "chat_xxx",
    "character_id": "atri",
    "state": "error",
    "code": "speech_too_short",
    "message": "VAD speech segment is too short for ASR auto-submit.",
    "seq": 12
  }
}
```

### `control:interrupt`

方向：服务端 -> 客户端

用途：在用户重新开口时，要求前端立刻中断当前文本/TTS 播放上下文。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | string | 是 | 当前聊天。 |
| `character_id` | string | 是 | 当前角色。 |
| `reason` | string | 是 | 当前稳定值为 `speech_start`。 |
| `generation_id` | string | 否 | 被中断的聊天或 TTS generation。 |

示例：

```json
{
  "type": "control:interrupt",
  "data": {
    "chat_id": "chat_xxx",
    "character_id": "atri",
    "generation_id": "gen_old",
    "reason": "speech_start"
  }
}
```

## `error`

方向：服务端 -> 客户端

用途：报告协议级或业务级错误，但通常不立即关闭连接。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `message` | string | 是 | 错误消息。 |
| `chat_id` | string | 否 | 相关聊天 ID。 |
| `generation_id` | string | 否 | 相关生成 ID。 |

示例：

```json
{
  "type": "error",
  "data": {
    "message": "Missing 'text' field",
    "chat_id": "chat_xxx"
  }
}
```

## `pong`

方向：服务端 -> 客户端

用途：响应客户端心跳 `{"type":"ping"}`。

示例：

```json
{
  "type": "pong"
}
```

## 相关文档

- [WebSocket 协议](websocket.zh-CN.md)
- [认证 API 与鉴权协议](auth.zh-CN.md)
