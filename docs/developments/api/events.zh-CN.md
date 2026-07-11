---
status: active
owner: api
created: 2026-07-09
updated: 2026-07-12
related_code:
  - src/routes/chat_ws.py
  - frontend/src/utils/websocket.ts
  - frontend/src/composables/useWebSocket.ts
  - frontend/src/composables/useRealtimeVoiceInput.ts
  - frontend/src/composables/useVision.ts
  - frontend/src/types/vision.ts
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
| `request_id` | string | 否 | 新前端生成的短生命周期请求关联 ID；用于精确恢复被顶层 `error` 拒绝的 pending submission。 |
| `client_context` | object | 否 | 前端上下文。当前前端会发送本地时间信息。 |
| `image` | object | 否 | 当前轮单张屏幕 JPEG。只在视觉模块与连接状态都开启时使用。 |

`image` 字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `source` | string | 是 | 首版固定为 `screen`。 |
| `media_type` | string | 是 | 首版固定为 `image/jpeg`。 |
| `encoding` | string | 是 | 首版固定为 `base64`。 |
| `data` | string | 是 | 不带 data URL 前缀的 Base64。不得写入日志或状态持久化。 |

示例：

```json
{
  "type": "input:text",
  "data": {
    "text": "今天有点累",
    "chat_id": "chat_xxx",
    "character_id": "atri",
    "request_id": "request_xxx",
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

省略 `image` 时保持原有纯文本行为。图片无效或视觉流未激活时，服务端丢弃图片并继续处理合法文本。

### `input:vision:state`

方向：客户端 -> 服务端

用途：把当前浏览器连接是否持有活动屏幕共享投影给服务端。它不修改 `vision_config.yaml`。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `enabled` | boolean | 是 | 当前连接是否有活动共享流。 |
| `source` | string | 是 | 首版固定为 `screen`。 |

示例：

```json
{
  "type": "input:vision:state",
  "data": {
    "enabled": true,
    "source": "screen"
  }
}
```

### `input:vision:capture-result`

方向：客户端 -> 服务端

用途：响应一次 generation-keyed 的 VAD 截图请求。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `generation_id` | string | 是 | 对应 capture request 的 generation。 |
| `status` | string | 是 | `captured`、`unavailable` 或 `failed`。 |
| `image` | object | 条件必填 | `status=captured` 时提供，结构与 `input:text.image` 相同。 |

说明：

- `unavailable` 表示当前没有可用视觉流；
- `failed` 表示本地截图或编码未成功；
- 这两种状态都会静默降级为纯文本；
- 未知、已中断或迟到的 generation 结果会被丢弃。

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

说明：正常路径会在 durable commit 认领后尝试消息持久化和记忆提交，再发送本事件。Storage/Memory 的辅助失败会被安全记录，但不会把已经成功生成的回复改写为 `output:chat:error`；因此本事件表示 generation 成功结束，不是对所有后端持久化介质的严格事务确认。

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

### `output:chat:error`

方向：服务端 -> 客户端

用途：把 pre-success generation failure 作为一个安全终态交给当前页面。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `message` | string | 是 | 固定安全文案，不包含 Provider 原始错误。 |
| `chat_id` | string | 是 | 所属聊天。 |
| `character_id` | string | 是 | 所属角色。 |
| `generation_id` | string | 是 | 失败的 generation。 |

当前 message：

```text
本轮回复生成失败，请稍后重试。
```

语义：

- 与 `output:chat:complete` 和 VAD interrupt 竞争首个终态；
- 只有仍 active 的完全匹配 generation 才能应用；
- 本轮不进入 ChatStorage、Memory、recent 或压缩；
- 前端只显示瞬态错误气泡，并丢弃同 generation 音频；
- 刷新或重新加载聊天后，该提示消失。

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
- `chat_commit_busy`：上一 generation 的 durable commit 在 5 秒上限内尚未结束；旧任务继续执行，本次语音不进入 ASR。
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
| `preserve_chat_generation` | boolean | 否 | `true` 表示 generation 已进入 durable commit；前端只停止音频，不清理聊天 stream。 |

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

通常该事件会使 active generation 失效。若 `preserve_chat_generation=true`，服务端已经在 send lock 内认领 durable success，不再取消聊天任务或重复写 interrupted round；前端保留文本 generation，等待后续 `output:chat:complete`。

### `control:vision:capture-request`

方向：服务端 -> 客户端

用途：后端 ASR 完成后，为即将开始的 VAD generation 请求当前屏幕一帧。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `generation_id` | string | 是 | 本轮 generation，也是回传关联键。 |
| `chat_id` | string | 是 | 所属聊天。 |
| `character_id` | string | 是 | 所属角色。 |
| `source` | string | 是 | 首版固定为 `screen`。 |

服务端在发送该事件前已注册 pending Future，因此客户端可以立即回传 `input:vision:capture-result`。截图等待不会阻塞同一连接的 receive loop。

## `error`

方向：服务端 -> 客户端

用途：报告协议校验或非 generation 终态的业务错误，但通常不立即关闭连接。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `message` | string | 是 | 错误消息。 |
| `chat_id` | string | 否 | 相关聊天 ID。 |
| `character_id` | string | 否 | 相关角色 ID。 |
| `generation_id` | string | 否 | 相关生成 ID。 |
| `request_id` | string | 否 | 被明确拒绝的 `input:text` 请求关联 ID。 |

示例：

```json
{
  "type": "error",
  "data": {
    "message": "Missing 'text' field",
    "chat_id": "chat_xxx",
    "character_id": "atri",
    "request_id": "request_xxx"
  }
}
```

顶层 `error` 不等价于 `output:chat:error`。前端可以展示连接/协议错误，但不能据此终止当前 streaming generation。只有当 `chat_id + request_id` 匹配且本地 stream 仍为 pending 时，前端才清理这次被明确拒绝的 submission；事件若携带 `character_id`，还必须与本地角色一致。generation 终态仍由完整关联的 `output:chat:error` 管理。

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
- [Vision 模块长期设计](../modules/vision/README.zh-CN.md)
