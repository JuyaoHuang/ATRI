---
status: active
owner: api
created: 2026-07-09
updated: 2026-07-11
related_code:
  - src/routes/chat_ws.py
  - src/auth/dependencies.py
  - frontend/src/utils/websocket.ts
  - frontend/src/composables/useWebSocket.ts
  - frontend/src/composables/useRealtimeVoiceInput.ts
  - src/tts/segment_manager.py
  - src/vision/
  - frontend/src/composables/useVision.ts
  - frontend/src/utils/visionSessionController.ts
---

# WebSocket 协议

ATRI 的实时聊天、屏幕视觉输入、实时语音打断和分段 TTS 都走同一个 WebSocket 端点：

```text
ws://HOST:PORT/ws
```

当前协议只使用 JSON 文本帧，不使用二进制音频帧，也不使用多路子协议。

## 连接方式

浏览器侧当前等价于：

```ts
const socket = new WebSocket("ws://localhost:8430/ws")
```

连接建立后，前端会：

1. 开始监听 `output:*`、`control:*`、`error`、`pong`。
2. 每 20 秒发送一次 `{"type":"ping"}` 心跳。
3. 在断线后按前端策略自动重连。

当前服务端一条连接只维护一份实时状态：

- 一个活动中的聊天 generation
- 一个活动中的 TTS 分段 manager
- 一个活动中的 VAD 会话
- 一份当前浏览器屏幕共享状态
- 一组按 generation 管理的待处理截图 Future

如果上一轮文本聊天还没有结束，又收到新的 `input:text`，服务端会返回 `error`，消息通常是 `Chat task already running`。

## 鉴权

认证开启时，`/ws` 在 `accept()` 之前就会做鉴权：

- 只读取 Cookie `atri_session`
- 不读取查询参数 token
- 不读取 Bearer 头

因此正式连接方式应该始终是：

```text
wss://YOUR_BACKEND/ws
```

而不是：

```text
wss://YOUR_BACKEND/ws?token=YOUR_JWT
```

行为总结：

| 场景 | 结果 |
| --- | --- |
| 认证关闭 | 直接接入，后端用户为 `default` |
| 认证开启且 Cookie 有效 | 正常建立连接 |
| 认证开启但 Cookie 缺失、过期或无效 | 在握手阶段关闭，close code `1008` |

认证细节见 [auth.zh-CN.md](auth.zh-CN.md)。

## 消息封装

所有业务消息都使用统一信封：

```json
{
  "type": "event-name",
  "data": {}
}
```

例外：

- `ping` 没有业务字段。
- `pong` 是服务端对 `ping` 的直接应答。

事件字段的精确定义见 [events.zh-CN.md](events.zh-CN.md)。本页重点解释连接时序。

服务端还会按 `vision.transport.websocket_max_message_bytes` 检查每个 JSON 文本帧的 UTF-8 字节数。配置必须为最大图片 Base64 保留最少信封余量；前端仍在真正发送前检查完整 `JSON.stringify(message)` 的 UTF-8 字节数。有图 `input:text` 超限时移除图片后发送同一文本一次；降级后的纯文本帧仍超限时不写 socket，并由发送状态机回滚 pending。VAD capture result 超限时改发 `status=failed`。后端拒绝的超限帧收到顶层 `error`，连接保持打开；日志只记录整数大小，不记录消息内容。

## 文本聊天时序

客户端发起一轮文本对话时，发送：

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
    },
    "image": {
      "source": "screen",
      "media_type": "image/jpeg",
      "encoding": "base64",
      "data": "<opaque-base64>"
    }
  }
}
```

`image` 是可选字段。只有后端视觉模块开启、且当前连接已经通过 `input:vision:state` 报告活动共享时，服务端才会校验和使用它。无图片、无活动视觉流或图片校验失败时，合法文本仍按纯文本处理。

后端时序如下：

```text
input:text
  -> 校验 text / chat_id / character_id
  -> 校验 chat 属于当前用户且属于该角色
  -> 创建 generation_id
  -> 构造 InputInform(text, image?)
  -> 流式发送 output:chat:chunk
  -> 在 send lock 内认领 committing
  -> 持久化 human / ai 消息
  -> 提交本轮记忆
  -> 发送 output:chat:complete
```

对调用方最重要的语义是：

- `output:chat:chunk` 代表“这段文本已经被前端看到”。
- 正常路径在 `output:chat:complete` 前进入 durable commit 并尝试聊天历史与记忆提交；complete 表示 generation 成功结束，不是所有持久化介质的严格事务确认。
- 如果 generation 在 durable success 开始前失败，服务端发送 `output:chat:error`，而不是 `output:chat:complete`。
- `output:chat:error`、`output:chat:complete` 和 VAD interrupt 在同一 send lock 内竞争首个终态。
- 失败 generation 不写聊天归档或 Memory；顶层 `error` 则不表示 generation 已失败。

## 屏幕视觉时序

### 模块与连接状态

视觉功能需要两个状态同时为真：

1. 后端 `vision.enabled=true`；
2. 当前浏览器连接发送：

```json
{
  "type": "input:vision:state",
  "data": {
    "enabled": true,
    "source": "screen"
  }
}
```

`input:vision:state` 只投影当前连接的 MediaStream 状态，不修改后端 YAML。WebSocket 重连后，如果页面中的 stream 仍有效，客户端应重新发送 `enabled=true`。

### 键盘与普通 ASR

键盘文本和普通单次 ASR 最终都通过前端 `useChat.sendMessage()` 发送。前端在发出 `input:text` 前最多截取一帧，并把可选 `image` 放入同一个消息。

本地无帧、Canvas/JPEG 编码失败或图片超限时，客户端静默省略 `image`，用户文本只发送一次。

### VAD + ASR

后端 ASR 完成后会直接启动 generation，因此由服务端请求截图：

```text
output:asr:transcript(generation_id)
  -> 注册 generation capture Future
  -> control:vision:capture-request
  -> 浏览器截图
  -> input:vision:capture-result
  -> 解析 Future
  -> InputInform(text, image?)
  -> output:chat:chunk ...
```

capture request 示例：

```json
{
  "type": "control:vision:capture-request",
  "data": {
    "generation_id": "gen_xxx",
    "chat_id": "chat_xxx",
    "character_id": "atri",
    "source": "screen"
  }
}
```

客户端成功回传：

```json
{
  "type": "input:vision:capture-result",
  "data": {
    "generation_id": "gen_xxx",
    "status": "captured",
    "image": {
      "source": "screen",
      "media_type": "image/jpeg",
      "encoding": "base64",
      "data": "<opaque-base64>"
    }
  }
}
```

`status=unavailable|failed` 时省略 `image`，后端继续纯文本。超过 `capture.timeout_ms`、连接关闭、视觉流停止或 generation 被 VAD 打断时，pending capture 被清理；迟到结果直接丢弃。

## 实时语音与 VAD 打断

### 输入音频

实时麦克风路径使用 `input:audio:chunk`：

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

其中：

- `audio` 是 number 数组，前端当前发送归一化后的浮点采样。
- `seq` 是前端递增序号，后端会在 `control:listen-state` 和 `output:asr:transcript` 中尽量回传它，便于前端关联。

### 正常 VAD 流程

```text
input:audio:chunk ...
  -> control:listen-state(state=silence / speech_start / speech_chunk / speech_end)
speech_end
  -> 后端拼接本轮语音
  -> 调用后端 ASR
  -> output:asr:transcript
  -> 后端内部自动触发一轮新的文本聊天
  -> output:chat:chunk ...
  -> output:chat:complete
```

也就是说，后端 ASR 成功后，客户端通常不需要再补发一条 `input:text`。

### `speech_start` 打断

当 VAD 检测到用户重新开口时，服务端会在同一条控制路径中：

1. 使当前聊天 generation 失效。
2. 取消当前聊天任务。
3. 中断当前 TTS 分段 manager。
4. 发送 `control:interrupt`。

若 generation 已在 send lock 内认领 `committing`，durable success 已经获胜。此时服务端仍停止 TTS，但不使聊天 generation 失效、不取消聊天任务，也不重复写 interrupted round；`control:interrupt` 会携带 `preserve_chat_generation=true`，前端保留文本 stream 并等待正常 complete。

若新一轮语音在提交期间结束，后端最多等待旧 commit task 5 秒。上限内完成时继续发送下一轮 ASR transcript；超时时不取消旧任务、不调用 ASR、也不创建新 generation，而是发送 `control:listen-state(state=error, code=chat_commit_busy)`。该错误结束本次 speech-end 处理并把控制权归还 WebSocket receive loop，用户可在旧 generation complete 后重试。

如果旧 generation 已经发出过一部分文本，服务端还会：

1. 把“已经发送给前端的 partial reply”持久化为 interrupted 审计消息。
2. 再发送 `output:chat:interrupted`。

因此前端应把 `control:interrupt` 当成“立刻停播、立刻丢弃旧 generation 音频”的信号；而 `output:chat:interrupted` 是“这段半截文本已经被后端正式记账”的信号。

### 主动结束录音

前端在停止实时录音时会发送：

```json
{
  "type": "input:audio:end",
  "data": {
    "chat_id": "chat_xxx",
    "character_id": "atri"
  }
}
```

它的作用是重置本次连接上的 VAD 会话。当前服务端对这条消息保留了少量同连接回退逻辑，但正式调用方仍应显式带上 `chat_id` 和 `character_id`。

## TTS 分段时序

只有同时满足下面三个条件时，聊天 WebSocket 才会自动下发分段 TTS：

```text
tts.enabled == true
tts.auto_play == true
tts.streaming.enabled == true
```

时序如下：

```text
output:chat:chunk
  -> 同一 chunk 喂给 SentenceDivider
  -> TTSSegmentManager 生成文本段
  -> 调用 TTSService.synthesize()
  -> output:audio:segment(sequence=0..n)
  -> output:audio:complete
```

关键语义：

- `output:chat:complete` 和 `output:audio:complete` 不是同一个时刻。
- 文本先完成，音频可能还会继续下发一小段时间。
- `output:audio:complete` 只表示“后端不会再发新的音频段”，不表示“用户已经播放完成”。
- 某个音频段失败时，后端会发送 `output:audio:error`，连接不会因此关闭。

## 关闭与错误

### 连接关闭

无论是客户端主动关闭、网络断开，还是服务端异常退出，后端都会在 `finally` 里做清理：

- interrupt 当前 TTS manager
- 释放本连接的 VAD 状态
- reset 当前 VAD session
- 释放连接级视觉状态并取消待处理截图

这保证旧 generation 的迟到音频不会继续写向已关闭连接。

### 不关闭连接的协议错误

下面这些情况通常只会收到 `error` 事件，连接仍保持打开：

- 消息不是合法 JSON
- 文本帧超过视觉 transport 配置的应用层上限
- 消息缺少 `type`
- `type` 未知
- `input:text` / `input:audio:*` 缺少必要字段
- 聊天不属于当前用户或角色

新前端会给 `input:text` 附带 `request_id`。当服务端明确拒绝该输入时，顶层 `error` 回显 request/chat/character；前端只清理完全匹配且仍为 pending 的 submission，不让其他协议错误终止 active generation。

### 连接前就失败的情况

这类错误不会先发 `error` 事件，因为连接还没 `accept()`：

- WebSocket 认证失败

客户端通常只能观察到握手失败或 close code `1008`。

### 心跳

服务端不会主动发心跳包，但会响应：

```json
{ "type": "ping" }
```

对应应答：

```json
{ "type": "pong" }
```

## 相关文档

- [事件字典](events.zh-CN.md)
- [认证 API 与鉴权协议](auth.zh-CN.md)
- [TTS 分段流式化长期设计](../modules/tts/streaming-design.zh-CN.md)
- [VAD 实时打断 feature](../features/2026-06-vad-realtime-interrupt/README.zh-CN.md)
- [Vision 模块长期设计](../modules/vision/README.zh-CN.md)
