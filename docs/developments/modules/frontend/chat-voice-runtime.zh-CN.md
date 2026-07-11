---
status: active
owner: frontend
created: 2026-07-09
updated: 2026-07-12
source_documents:
  - ../../module-design/CN/前端设计文档.md
  - ../../features/2026-06-vad-realtime-interrupt/README.zh-CN.md
  - ../../features/2026-07-tts-segment-streaming/README.zh-CN.md
related_code:
  - frontend/src/composables/useChat.ts
  - frontend/src/composables/useWebSocket.ts
  - frontend/src/utils/websocket.ts
  - frontend/src/composables/useVoiceInput.ts
  - frontend/src/composables/useRealtimeVoiceInput.ts
  - frontend/src/composables/useAudioPlayer.ts
  - frontend/src/composables/useVision.ts
  - frontend/src/utils/visionSessionController.ts
  - frontend/src/utils/screenCapture.ts
  - frontend/src/components/chat/InputBox.vue
  - frontend/src/stores/chat.ts
  - frontend/src/stores/chats.ts
  - frontend/src/stores/websocket.ts
---

# 聊天、语音与视觉运行时

本文描述前端聊天、语音输入、屏幕视觉、VAD 打断和自动 TTS 播放的长期运行时设计。它只关注浏览器侧状态编排，不替代后端聊天、记忆、Vision、VAD 或 TTS 模块文档。

## 运行时定位

当前前端有两条业务传输面：

- REST：负责角色、聊天列表、历史详情、模块配置、模型管理和数据清理。
- WebSocket `/ws`：负责聊天文本流、视觉截图握手、VAD 控制、ASR 最终转写和 TTS 分段音频事件。

前端运行时的核心任务，是把这两条传输面汇总为一个稳定的用户体验：

- 用户输入后，能够看到草稿会话、历史消息和流式回复。
- 语音输入能够以“单次转写”或“实时语音”两种方式进入同一套聊天链路。
- 自动 TTS、VAD interrupt 和上下文切换不会把旧 generation 的音频或文本泄漏到新上下文。
- 屏幕截图只属于当前发送轮次，不进入浏览器持久化状态或聊天历史。

## 核心不变量

1. 聊天显示真相来自 `chatStore.timelineItems`；`messages` getter 只过滤持久化语义的正常消息。时间线来源要么是 `useChat.loadHistory()` 的 REST 返回，要么是 WebSocket `output:chat:*` 事件。
2. 自动 TTS 只消费 AI 回复，不反向改写聊天历史或短期记忆。
3. `generation_id` 是自动 TTS、打断和迟到结果丢弃的统一边界。
4. 实时语音必须绑定“已保存的聊天标题 + 已选角色 + 已连接的业务 WebSocket”。
5. 会话切换、角色切换和 VAD interrupt 都会停止当前播放，但语义不同：前两者是前端上下文切换，后者是后端显式打断。
6. 视觉模块开关与当前标签页的 `MediaStream` 是两份不同状态，不能相互冒充。
7. generation failure 是瞬态 notice，不是 AI 消息；刷新或历史重载后必须消失。

## WebSocket 事件面

`frontend/src/utils/websocket.ts` 把后端消息映射成前端内部事件：

| 后端消息 | 前端内部事件 | 主要消费者 |
| --- | --- | --- |
| `output:chat:chunk` | `chat:chunk` | `useWebSocket` -> `chatStore.appendStreamingChunk()` |
| `output:chat:complete` | `chat:complete` | `useWebSocket` -> `chatStore.completeStreaming()` |
| `output:chat:interrupted` | `chat:interrupted` | `useWebSocket` -> `chatStore.interruptStreaming()` |
| `output:chat:error` | `chat:generation-error` | `useWebSocket` -> `chatStore.failActiveGeneration()` |
| `output:audio:segment` | `audio:segment` | `useWebSocket` -> `useAudioPlayer.enqueueAudioSegment()` |
| `output:audio:complete` | `audio:complete` | `useWebSocket` -> `useAudioPlayer.completeAudioGeneration()` |
| `output:audio:error` | `audio:error` | `useWebSocket` -> `useAudioPlayer.skipAudioSegment()` |
| `output:asr:transcript` | `asr:transcript` | `useWebSocket` -> `chatStore.addAsrTranscriptMessage()` |
| `control:listen-state` | `vad:listen-state` | `useRealtimeVoiceInput` |
| `control:interrupt` | `vad:interrupt` | `useWebSocket` + `useAudioPlayer` |
| `control:vision:capture-request` | `vision:capture-request` | `useVision` -> 截图并回传结果 |
| `error` | `chat:error` | `useWebSocket` |
| `pong` | 无额外分发 | `WebSocketManager` 心跳 |

客户端主动发送的消息类型目前是：

- `input:text`
- `input:vision:state`
- `input:vision:capture-result`
- `input:audio:chunk`
- `input:audio:end`
- `ping`

## WebSocket 会话控制层

近期前端会话重构后，聊天运行时不再把“连接中”“UI 已连接”“允许发送”混为一谈。当前稳定结构是：

| 层 | 代码 | 职责 |
| --- | --- | --- |
| 传输层 | `frontend/src/utils/websocket.ts` | 原生 socket、heartbeat、重连 timer、原始 `send()` |
| 会话层 | `frontend/src/utils/websocketSessionController.ts` | 当前 active manager、session epoch、协议事件分发、统一发送入口 |
| facade 层 | `frontend/src/composables/useWebSocket.ts` | 对业务暴露 `connect()`、`disconnect()`、`canSend()`、`send*()` 和统一默认 handler |
| UI 投影层 | `frontend/src/stores/websocket.ts` | 只保留 `connectionStatus` 与 `error` |

长期约束：

1. `readyState === OPEN` 是唯一底层发送事实来源。
2. `wsStore.connected` 只用于 UI，不再阻塞文本或音频发送。
3. 页面内所有文本和实时音频发送都必须经过 `useWebSocket()` facade。
4. 默认协议 handler 只注册一次，避免多处调用 `useWebSocket()` 造成重复副作用。

## 连接生命周期

`useWebSocket()` 是聊天页级别的连接入口，内部使用 `WebSocketManager` 维护单连接实例。

连接规则：

1. 入口 URL 来自 `VITE_WS_URL`，并在前端统一规范为 `ws:` 或 `wss:`。
2. 已有同 URL 且仍然连接中或允许重连的 manager，不重复创建。
3. 连接成功后开始 20 秒心跳；关闭后 3 秒重连。
4. 断线时清空 `chatStore.activeStream`，并把 `wsStore.reconnecting` 置为可观测状态。
5. `disconnect()` 与 `destroy()` 都会停止心跳、关闭 socket，并移除监听器。

前端不维护多路聊天 WebSocket，也不按聊天标题创建独立连接。

页面级连接入口目前固定在 `frontend/src/pages/index.vue`：

- 首页 `onMounted()` 建立连接；
- 首页 `onUnmounted()` 断开连接；
- `ChatArea` 与 `StageChatShell` 不再各自 `connect()`。

这是近期 git log 和 feature 文档已经确认下来的稳定结论。

## 文本聊天链路

### 发送链路

`InputBox.vue` 负责输入体验，`useChat.sendMessage()` 负责真正发消息。

发送过程如下：

1. 输入框先校验文本非空；`chatStore.reserveSubmission()` 同时阻止 active generation 和截图等待期间的重复发送。
2. `useChat()` 为每条消息附带 `client_context.datetime`，包含：
   - `iso`
   - `local`
   - `time_zone`
   - `utc_offset`
3. 若当前还没有已保存聊天，前端先在 `chatsStore` 中插入一个 `draft_*` 草稿会话，并立即把用户消息加入本地消息列表。
4. 随后调用 `POST /api/chats` 创建真实聊天标题；成功后用真实 `chat_id` 替换草稿，并启动延迟标题轮询。
5. 如果视觉模块已启用且当前标签页存在活动屏幕共享，`captureForSubmission()` 尝试截取一张 JPEG。无活动流时立即返回，不等待视觉配置 REST；失败时返回 `undefined`，不显示 toast。
6. 最终通过 WebSocket 发送：

```json
{
  "type": "input:text",
  "data": {
    "text": "...",
    "chat_id": "...",
    "character_id": "...",
    "request_id": "request_xxx",
    "client_context": {
      "datetime": {
        "iso": "...",
        "local": "...",
        "time_zone": "...",
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

`image` 是可选字段。前端不在聊天框显示截图预览、附件徽标或元数据。会话发送层在 `JSON.stringify()` 后按 UTF-8 字节数检查完整信封；有图帧超限时省略图片并只发送一次文本。

7. `chatStore.beginStreaming()` 在真正调用 `sendText()` 前创建流式状态；发送失败时立即清理。

需要补充一个近期稳定约束：

- `beginStreaming()` 在发送前建立本地等待态；
- deferred title 的 pending 标记与轮询只在 `sendText()` 成功后启动。
- submission gate 在截图与发送完成后才释放，确保用户文本最多发送一次。

这样可以避免：

- chunk 到达时前端还没进入 streaming 结构；
- 发送失败时前端自己保留一份假的 pending title 状态。

### 接收链路

`useWebSocket()` 在 `chat:chunk`、`chat:complete`、`chat:interrupted` 上更新 `chatStore`：

- `chat:chunk`：增量拼接 `streamingText`。
- `chat:complete`：结束流式状态，落入一条最终 AI 消息。
- `chat:interrupted`：把半截回复以 `interrupted=true` 的消息形态落到前端消息列表。
- `chat:generation-error`：严格匹配 `chat_id + character_id + generation_id` 后，终止当前流式状态并追加瞬态错误 notice。
- `chat:error`：投影到 `wsStore.error`；若 `chat_id + request_id` 匹配 pending submission，则清理该 pending。事件若携带 `character_id`，还必须与本地角色一致；其他错误不终止 active generation。

AI 文本在进入消息列表前，会先经过 `extractLive2dExpression()`：

- 展示内容只保留可读文本。
- 若文本中携带合法表情标记，则把表情请求发给 `live2dStore`。

### 历史加载

`useChat.loadHistory()` 通过 `/api/chats/{id}` 读取完整消息列表，并在前端做两件事：

1. 还原消息显示字段，例如角色名、头像、`generation_id`、`interrupted`。
2. 从最后一条 AI 消息里提取 Live2D 表情，恢复舞台状态。

历史响应只包含持久化消息。加载时 `replaceTimelineItems()` 会整体替换当前运行时时间线，因此 generation failure 对应的本地用户文本与错误 notice 都会消失。

## 单次语音输入

`VoiceInput.vue` 对应“点一下开始、再点一下结束”的语音输入入口，底层是 `useVoiceInput()`。

它有两种路径：

1. 浏览器原生识别：
   - 当 ASR provider 标记 `supports_browser_streaming=true` 时，优先使用 `SpeechRecognition` / `webkitSpeechRecognition`。
   - 中间结果显示在按钮浮层。
   - 最终结果通过 `onTranscript` 回填到 `InputBox`。
2. 后端文件转写：
   - 当 provider 不支持浏览器流式识别时，浏览器先录制 WAV，再调用 `POST /api/asr/transcribe`。
   - 转写完成后把文本回填到 `InputBox`。

`InputBox` 会把收到的 transcript 追加到文本框，并按 `asrStore.auto_send` 决定是否延迟自动发送。

## 实时语音输入

`RealtimeVoiceInput.vue` 与 `useRealtimeVoiceInput()` 是另一条链路，目标是“边听边让后端跑 VAD/ASR/interrupt”。

### 前置条件

只有同时满足以下条件时，实时语音按钮才可用：

- ASR 模块已开启。
- 已选择角色。
- 当前聊天不是 `draft_*`，而是已保存聊天。
- WebSocket 已连接。

这意味着实时语音不会自动替用户创建聊天标题。

### 浏览器采集

前端采集规则：

1. `getUserMedia()` 按 `settings/hearing/audio-input` 选择麦克风。
2. 用 `AudioContext + ScriptProcessorNode + GainNode` 建立静音采集链路。
3. 采样被重采样到 16 kHz 单声道。
4. 每个 chunk 通过 JSON float array 发送为 `input:audio:chunk`，并携带递增 `seq`。
5. 停止时发送 `input:audio:end`，除非是 WebSocket 已断开的被动停止。

`ScriptProcessorNode` 当前仍是兼容实现的一部分；迁移到 `AudioWorklet` 属于后续优化，不改变协议。

### 状态反馈

后端 `control:listen-state` 会驱动以下前端状态：

- `listenState`
- `isSpeech`
- `probability`
- `energy`
- 临时错误提示

这些状态既用于实时语音按钮的视觉反馈，也服务于设置页的监控与排障。

### 自动转入聊天

当后端在一次语音结束后返回 `output:asr:transcript` 且 `is_final=true` 时：

1. `chatStore.addAsrTranscriptMessage()` 先把用户语音结果作为一条 `human` 消息加入当前聊天。
2. 同时创建新的 `activeStream`，等待后续 AI 回复。
3. 后续 `output:chat:*` 与手打文本走同一套接收链路。

## 屏幕视觉输入

### 双层控制

设置页 `/settings/modules/vision` 只有一个持久化开关。它通过 REST 修改后端 `vision.enabled`，但不会调用浏览器屏幕共享 API。

默认聊天和 Live2D Stage 都复用 `InputBox.vue`，工具栏顺序是：

```text
VoiceInput -> RealtimeVoiceInput -> VisionInput
```

`VisionInput` 控制当前标签页的 `MediaStream`：

- 模块关闭：按钮不可用；
- 模块开启、无流：按钮可用但不自动请求权限；
- 用户点击：调用 `getDisplayMedia({video:true,audio:false})`；
- 活动共享：按钮显示 pressed 状态；
- 再次点击：停止全部 tracks；
- 权限拒绝或不支持：按钮显示安全错误状态。

按钮不依赖 WebSocket connected 才允许共享。若连接断开但 MediaStream 仍有效，重连后会重新发送活动状态。

### MediaStream 所有权

`visionSessionController` 是跨路由单例，持有 stream、video track 和隐藏 video。Pinia 只保存安全配置投影与轻量状态。

组件卸载和设置页/主页切换不会停止 stream。controller 在以下时机清理：

- 用户显式停止；
- 设置页禁用模块成功；
- 浏览器原生“停止共享”触发 track `ended`；
- 页面卸载；
- 授权返回时发现启动 epoch 已被取消。

页面刷新后不尝试恢复共享，也不保存“已授权”状态。

### VAD 截图握手

键盘和普通 ASR 在前端发送前直接截图。VAD + 后端 ASR 则由后端在生成开始前发送 `control:vision:capture-request`。

`useVision` 收到请求后：

1. 检查 `generation_id` 和 `source=screen`；
2. 从 controller 的活动视频截取当前一帧；
3. 发送 `input:vision:capture-result`，状态为 `captured`、`unavailable` 或 `failed`；
4. WebSocket 重连、路由切换或组件卸载都不改变图片的 generation 关联。

截图失败不会显示 toast 或 `ChatErrorBubble`。图片是局部返回值，发送后不进入 Pinia、localStorage、IndexedDB 或聊天时间线。

### Generation failure

`output:chat:error` 的 message 以普通消息气泡尺寸显示，但时间线 item 是 `kind=notice`：

- 不使用 AI role 或角色头像；
- 不显示 TTS 按钮；
- 不触发 Live2D 表情；
- 只在当前匹配聊天可见；
- VAD interrupt 或新 generation 已先获胜时直接丢弃；
- 失败 generation 的待播音频一并丢弃；
- 刷新或历史重载后消失。

## 自动 TTS 与播放器

`useAudioPlayer()` 是全局播放器运行时，`App.vue` 中的 `AudioPlayer.vue` 负责渲染悬浮播放器。

播放器有两条输入路径：

1. 手动或测试播放：
   - 直接调用 `ttsStore.synthesize()`，拿到完整音频后排队播放。
   - 来源可以是历史消息手动播放、设置页语音测试或普通自动朗读 fallback。
2. WebSocket 分段音频：
   - `useWebSocket()` 把 `output:audio:segment` 的 base64 音频解码为 `Blob`。
   - `useAudioPlayer.enqueueAudioSegment()` 按 `generation_id + sequence` 去重并排队。

`enqueueAutoSpeech()` 只有在以下条件同时满足时才会走“完整回复后自动朗读”：

- TTS 模块开启。
- 自动播放开启。
- 当前不是 TTS 分段流式自动播放模式。

也就是说，当后端已启用分段流式 TTS 时，前端不会再对同一条完整回复额外触发一次 REST 合成。

## 丢弃与中断规则

前端必须主动治理旧 generation 的迟到结果：

- `control:interrupt`：停止当前播放；默认把对应 generation 标记为 discarded。若携带 `preserve_chat_generation=true`，只丢弃音频并保留聊天 stream，等待 durable commit 的 complete。
- `output:chat:error`：清理匹配 generation 的 partial text，并丢弃同 generation 音频。
- `output:chat:interrupted`：以半截回复形式结束本轮展示，不让旧流继续占用 `activeStream`。
- 切换聊天或角色：`audioPlayer.stopBecauseContextChanged()` 立即清空当前与排队音频。
- 手动 `stop()`：增加 `discardEpoch`，防止进行中的 REST 合成在稍后重新插入队列。
- `audio:error`：按 sequence 跳过失败片段，避免播放队列永久卡住。

这里的原则是“宁可丢弃旧结果，也不跨上下文串音或串文”。

## 扩展约束

后续扩展应保持以下边界不变：

1. 不让播放器进度、已听到文本或手动跳播去回写聊天历史与短期记忆。
2. 不让实时语音直接复用草稿聊天；若要支持，必须先补全后端对 draft chat 的协议定义。
3. 如果升级为二进制音频帧或 `AudioWorklet`，要保持 `generation_id`、`sequence` 和 interrupt 语义稳定。
4. 新增音频消费能力时，优先复用 `useAudioPlayer()` 的 discard 规则，不单独发明第二套 generation 生命周期。
5. 新增视觉来源时，先扩展 `InputInform` 与 controller 所有权，不把 stream 或附件塞进聊天 store。
6. 大型二进制或 Base64 字段只能作为局部发送参数，不能进入 console、Pinia 或持久化层。

## 相关文档

- [README.zh-CN.md](README.zh-CN.md)
- [stage-and-settings.zh-CN.md](stage-and-settings.zh-CN.md)
- [../../features/2026-06-vad-realtime-interrupt/README.zh-CN.md](../../features/2026-06-vad-realtime-interrupt/README.zh-CN.md)
- [../../modules/tts/streaming-design.zh-CN.md](../../modules/tts/streaming-design.zh-CN.md)
- [Vision 模块长期设计](../vision/README.zh-CN.md)
