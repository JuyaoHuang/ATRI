---
status: accepted
owner: frontend
created: 2026-07-09
updated: 2026-07-09
source:
  - docs/developments/features/2026-07-frontend-websocket-session-refactor/README.zh-CN.md
  - docs/developments/features/2026-07-frontend-websocket-session-refactor/dev-log.zh-CN.md
  - docs/developments/modules/frontend/README.zh-CN.md
  - docs/developments/modules/frontend/design.zh-CN.md
  - docs/developments/modules/frontend/state-management.zh-CN.md
  - docs/developments/modules/frontend/chat-voice-runtime.zh-CN.md
related_code:
  - frontend/src/utils/websocket.ts
  - frontend/src/utils/websocketSessionController.ts
  - frontend/src/composables/useWebSocket.ts
  - frontend/src/stores/websocket.ts
  - frontend/src/composables/useChat.ts
  - frontend/src/composables/useRealtimeVoiceInput.ts
  - frontend/src/pages/index.vue
---

# ATRI 前端 WebSocket Session 重构复盘

这次 frontend websocket session refactor 不是一次普通的“把 WebSocket 再封装一层”。它真正处理的问题，是前端运行时里最容易悄悄失控的一类问题：同一条连接同时服务文本聊天、实时语音、VAD 控制和 TTS 音频之后，系统里开始出现多份看起来都合理的“连接真相”。

一份真相来自原生 socket：`readyState === OPEN`。一份真相来自 UI store：`wsStore.connected`。一份真相来自组件生命周期：谁调用了 `connect()`，谁又在卸载时 `disconnect()`。还有一份真相来自业务链路：文本发送和实时音频发送各自判断“现在能不能发”。这些判断单独看都不离谱，但一旦互相越权，前端就会进入一种很难排查的状态：页面显示未连接，底层连接可能已经打开；UI 状态说不能发，原生 socket 也许已经能发；旧 manager 的事件晚到，又可能写回新页面。

本次重构的核心结论可以概括为一句话：**发送 authority 收敛到底层 `readyState === OPEN`，session authority 收敛到单例 `WebSocketSessionController`，UI store 退回展示投影。**

## 背景

ATRI 前端现在不再只有“输入文本，等待 AI 回复”这一条链路。首页的业务 WebSocket `/ws` 同时承接了多种运行时事件：

- 文本聊天：`input:text` 上行，`output:chat:*` 下行。
- 实时语音：`input:audio:chunk` 和 `input:audio:end` 上行。
- ASR/VAD：`output:asr:transcript`、`control:listen-state`、`control:interrupt` 下行。
- TTS 分段播放：`output:audio:segment`、`output:audio:complete`、`output:audio:error` 下行。

这些链路共享同一条连接，但它们的业务生命周期并不相同。文本流式回复关心当前聊天与当前 `generation_id`；实时语音关心采集中的 `chat_id`、`character_id` 和音频序号；TTS 播放关心 `generation_id + sequence`；VAD interrupt 又要同时影响文本流与音频队列。

因此，前端长期设计里已经有几个重要约束：

- REST 和 WebSocket 是两条正式传输面，不能互相替代。
- 文本流、实时语音、VAD 和 TTS 共用业务 WebSocket，但各自状态边界独立。
- `generation_id` 是文本、打断和音频丢弃的统一业务边界。
- 首页可以在普通聊天模式和 Live2D 舞台模式之间切换，但不应该产生第二套连接生命周期。

这次重构发生的原因，是旧实现没有把“连接是否可发送”“连接状态怎么展示”“事件属于哪次会话”分清楚。随着语音链路接入，这种不清楚开始从偶发体验问题变成结构性风险。

## 问题拆解：多份连接真相

问题的表面现象很直观：

- 页面可能长时间显示“未连接”。
- 文本发送可能被 `WebSocket is not connected` 提前拦截。
- 实时语音链路直接读取 `wsStore.connected` 和旧的 `wsManager`，和文本发送不在同一套出口上。
- 页面内多个组件各自调用 `connect()`，让连接生命周期看起来属于组件，而不是属于页面。

更深一层看，前端当时把四种不同职责揉在了一起：

| 职责 | 应该回答的问题 | 混在一起后的风险 |
| --- | --- | --- |
| 传输层事实 | 原生 socket 此刻能不能 `send()` | UI 状态替代底层判断，导致误拦截或误发送 |
| UI projection | 页面应该显示连接、重连还是错误 | 展示状态被当成发送 authority |
| session 归属 | 事件是否来自当前 active manager | 旧连接晚到事件写回新状态 |
| 业务发送入口 | 文本、音频应该从哪里出站 | 不同链路绕过统一边界，各自判断可发送性 |

这里的关键不是“状态太多”，而是“状态没有分层”。`wsStore.connected` 很适合告诉按钮怎么亮、文案怎么显示、实时语音按钮是否应该呈现为可用；但它不适合决定一帧音频能不能被写入 socket。原因很简单：UI projection 是从事件推导出来的状态，它天然可能滞后于底层 socket 的瞬时状态。

同理，`canSend()` 也不能被理解成成功保证。它只是在同一个 authority 来源上做一次预检。预检之后、真正 `send()` 之前，连接仍然可能关闭。最终是否发送成功，只能看 `sendText()`、`sendAudioChunk()`、`sendAudioEnd()` 这些出口的返回值。

## Authority 收敛方案

本次重构后，WebSocket 相关职责被拆成五层：

| 层 | 代码 | 职责边界 |
| --- | --- | --- |
| 传输层 | `WebSocketManager` | 原生 `WebSocket`、heartbeat、reconnect timer、原始消息解析、原始 `send()` |
| 会话层 | `WebSocketSessionController` | 当前 active manager、`sessionEpoch`、连接状态、协议分发、统一发送出口 |
| facade 层 | `useWebSocket()` | 暴露业务可用 API，注册默认协议 handler，隐藏 controller 细节 |
| UI 投影层 | `wsStore` | `connectionStatus`、`error`、`connected/reconnecting` getter |
| 业务运行时 | `chatStore`、`useRealtimeVoiceInput()`、`useAudioPlayer()` | 聊天流、实时语音采集、TTS 队列和 `generation_id` 丢弃规则 |

这套拆分的目的，是让每一层只回答自己能回答的问题。

### `readyState === OPEN`

`readyState === OPEN` 是唯一底层发送事实来源。它只存在于传输层，由 `WebSocketManager.canSend()` 读取。

这条规则刻意很低层。因为只有原生 socket 知道自己此刻是否能写入。UI store、组件 mounted 状态、业务上是否有聊天，都不能替代它。

### `canSend()`

`canSend()` 是同源预检。它从 `useWebSocket()` 进入，最终落到 `WebSocketSessionController.canSend()`，再落到当前 manager 的 `readyState === OPEN`。

它的职责是降低无意义工作，例如：

- 文本发送前先快速提示“WebSocket is not connected”。
- 实时语音启动前避免打开麦克风后才发现不能发。
- 音频处理回调里发现断线后立即停止采集。

但它不是成功保证。成功与否仍然由实际发送函数返回。

### `sendText()`、`sendAudioChunk()`、`sendAudioEnd()`

`sendText()`、`sendAudioChunk()`、`sendAudioEnd()` 是业务发送的统一出口。它们负责把前端 payload 收敛成后端协议消息：

```text
sendText()
  -> type: input:text

sendAudioChunk()
  -> type: input:audio:chunk

sendAudioEnd()
  -> type: input:audio:end
```

这些函数返回 `boolean`。调用方必须根据返回值处理失败，而不是假设 `canSend()` 之后一定成功。

这也是文本链和实时语音链统一后的关键变化：业务代码不再直接碰底层 manager，也不再通过 `wsStore.connected` 阻塞发送。

### `wsStore.connected`

`wsStore.connected` 现在只是 UI projection。它来自 `connectionStatus === connected`，可以用于：

- 显示连接状态。
- 控制按钮视觉状态。
- 让实时语音按钮在 UI 上呈现可用或不可用。
- 在连接转入关闭或重连时触发本地清理。

它不再用于：

- 判断文本消息是否真的可以写入 socket。
- 判断音频 chunk 是否真的可以上行。
- 持有或暴露底层 `WebSocketManager`。
- 提供 `send()` 或 `sendIfOpen()`。

这条边界非常重要。`wsStore.connected` 不是“连接真相”，而是“给 UI 看的连接投影”。

## `WebSocketSessionController` 的职责

`WebSocketSessionController` 是这次重构的中心，但它不是一个“包办所有状态”的大仓库。它只负责 WebSocket session 本身：

- 当前 URL。
- 当前 active `WebSocketManager`。
- 当前 `ConnectionStatus`。
- 当前连接错误。
- `sessionEpoch`。
- session 级事件总线。
- 协议消息到前端内部事件的分发。
- `sendText()`、`sendAudioChunk()`、`sendAudioEnd()` 三个统一发送出口。

它把连接生命周期收敛成下面这条路径：

```text
index.vue onMounted
  -> useWebSocket().connect()
  -> WebSocketSessionController.connect(url)
  -> WebSocketManager.connect()
  -> connection:status
  -> wsStore projection

index.vue onUnmounted
  -> useWebSocket().disconnect()
  -> WebSocketSessionController.disconnect()
  -> teardown current manager
  -> connectionStatus = closed
```

当同一个 URL 已经处于 `CONNECTED` 或 `CONNECTING`，controller 不重复创建 manager。当状态是 `RECONNECTING` 且 manager 仍存在时，controller 允许一次 connect kick，由 manager 先清理 pending reconnect timer，再尝试连接。这样既避免重复 socket，也避免“正在重连时手动 connect 反而被卡住”。

协议分发也被收敛到 controller。底层 manager 只发出原始 `message`，controller 再把后端消息映射成前端内部事件：

| 后端消息 | 前端内部事件 |
| --- | --- |
| `output:chat:chunk` | `chat:chunk` |
| `output:chat:complete` | `chat:complete` |
| `output:chat:interrupted` | `chat:interrupted` |
| `output:audio:segment` | `audio:segment` |
| `output:audio:complete` | `audio:complete` |
| `output:audio:error` | `audio:error` |
| `output:asr:transcript` | `asr:transcript` |
| `control:listen-state` | `vad:listen-state` |
| `control:interrupt` | `vad:interrupt` |
| `error` | `chat:error` |
| `pong` | 心跳响应，不额外分发 |

这样做之后，`useWebSocket()` 的默认 handler 只需要订阅 controller 事件，不需要理解原生 socket，也不需要重复解析后端协议。

## `sessionEpoch`：防止旧会话写回新状态

`sessionEpoch` 是这次设计里最容易被低估的保护。它解决的是一个很具体的问题：旧 manager 的异步事件可能晚到。

浏览器 WebSocket 的事件不是同步、可完全线性控制的。页面卸载、重连、切换 URL、销毁 manager 之后，旧 socket 的 `onclose`、`onerror` 或 `onmessage` 仍可能在稍后触发。如果这些事件没有归属检查，就可能出现：

- 旧连接的 close 把新连接状态改成 closed。
- 旧连接的 message 被当成当前会话消息继续分发。
- 旧连接的 error 覆盖当前 session 的错误状态。

controller 在绑定 manager 事件时，会把当前 `epoch` 捕获进闭包。每个事件进来后先检查：

```text
this.manager === manager && this.sessionEpoch === epoch
```

只有 manager identity 和 epoch 同时匹配，事件才允许继续分发。否则直接丢弃。

需要强调的是，`sessionEpoch` 不是 `generation_id` 的替代品。它只回答“这是不是当前 WebSocket session 的事件”。它不回答“这个 chunk 属不属于当前聊天”，也不回答“这段音频还能不能播放”。

当前前端有三层丢弃边界：

| 边界 | 解决的问题 |
| --- | --- |
| `sessionEpoch` | 旧 WebSocket manager 的事件不能写回新 session |
| `chatId + characterId + generationId` | 旧文本 chunk 不能落进新聊天或新角色 |
| `generation_id + sequence` | 旧 TTS 音频段不能在上下文切换后继续入队 |

这三层边界不能互相替代。把所有东西都塞进 controller，会让连接层重新变成业务大杂烩；只保留业务层检查，又挡不住旧 manager 的连接事件写回 UI。

## UI Projection：让 store 回到展示层

重构后的 `frontend/src/stores/websocket.ts` 很薄，只保留：

- `connectionStatus`
- `error`
- `connected` getter
- `reconnecting` getter

`ConnectionStatus` 的当前取值包括：

```text
idle
connecting
connected
reconnecting
closed
```

这些状态由 controller 的 `connection:status` 事件驱动，再被 `useWebSocket()` 的默认 handler 写入 store。业务组件可以消费这些状态来渲染 UI，但不能把它们当作发送判断。

这次降级的价值有两点。

第一，它移除了 store 对底层 manager 的所有权。`wsStore` 不再有 `wsManager`，自然也不再允许组件从 store 里拿 manager 直接发送。

第二，它让连接展示和发送事实解耦。比如实时语音可以用 `connected` 决定按钮是否看起来可启动，也可以在 `connected` 变成 false 时停止本地采集；但真正开始前和每个音频 chunk 发送前，仍然要走 `canSend()` 和 `sendAudioChunk()`。

换句话说，UI projection 可以影响体验路径，但不能越权决定底层 I/O。

## 页面级连接入口

这次重构明确保留“页面级连接”，没有升级为应用级常驻连接。

当前连接入口在 `frontend/src/pages/index.vue`：

```text
onMounted()
  -> connect()
  -> fetch characters
  -> fetch Live2D models

onUnmounted()
  -> disconnect()
```

`ChatArea` 和 `StageChatShell` 不再各自建立连接。这样首页的普通聊天模式和 Live2D 舞台模式共享同一条页面连接，切换布局不会创建第二条业务 WebSocket。

这个决策背后有两个取舍。

第一，业务 WebSocket 主要服务首页聊天、实时语音和音频流。设置页、登录页、角色管理等场景主要使用 REST，不需要应用启动后一直维持 `/ws`。

第二，连接生命周期应该属于页面，而不是属于局部组件。否则任意一个组件的 mounted/unmounted 都可能影响整页发送能力，排查时很难判断到底是谁创建了当前连接。

因此，当前稳定结论是：**首页拥有连接生命周期，组件只消费 facade。**

## 文本链与实时语音链的统一出口

这次重构的另一个重点，是让文本发送和实时语音发送都走同一套 WebSocket facade。

### 文本发送链

`useChat()` 现在通过 `useWebSocket()` 获取：

- `canSend`
- `sendText`

发送流程可以概括为：

```text
校验文本和当前发送状态
  -> canSend() 预检
  -> 准备 character/chat
  -> 如无当前 chat，则创建 draft 并请求后端创建真实 chat
  -> stopBecauseContextChanged()
  -> beginStreaming()
  -> sendText()
  -> 如果 sendText() 失败，清理 activeStream
  -> 如果 sendText() 成功，再启动 deferred title 前端 pending 和轮询
  -> 添加本地 human 消息
```

这里有两个细节值得写清楚。

第一，`beginStreaming()` 被放在 `sendText()` 之前，是为了先建立本轮回复的本地等待态。这样后续 `chat:chunk` 到达时，不依赖隐含的异步时序。

第二，deferred title 的前端 pending 标记和轮询被放在 `sendText()` 成功之后。这样发送失败时，前端不会自己制造一个“等待标题补全”的假状态。

这只收敛了前端本地状态，不改变后端 `createChat(..., defer_title=true)` 的语义。后端在 REST 创建成功后可能已经启动补标题后台任务，这不是本次前端重构解决的问题。

### 实时语音链

`useRealtimeVoiceInput()` 现在也通过同一个 facade 获取：

- `canSend`
- `connected`
- `sendAudioChunk`
- `sendAudioEnd`
- `on/off`

这里看起来还在使用 `connected`，但它的用途已经被限制在 UI 和生命周期投影：

- `canStart = asrStore.moduleEnabled && connected.value` 用于按钮可用性。
- `watch(connected)` 用于连接断开后停止本地实时语音会话。
- 真正开始前，仍然检查 `canSend()`。
- `getUserMedia()` 和 `AudioContext` 建立后，还会再次检查 `canSend()`。
- 每个 `onaudioprocess` 回调发送前，还会检查 `canSend()`。
- 每个音频 chunk 实际出站时，仍然以 `sendAudioChunk()` 返回值为准。

实时语音停止时，如果需要通知后端，统一走 `sendAudioEnd()`。如果是断线导致的被动停止，则不再强行通知后端，避免在不可发送状态下继续制造无意义发送。

同时，`vad:listen-state` 也不再从散落的 manager listener 进入，而是通过 `useWebSocket().on()` 订阅 controller 分发后的事件。这样实时语音链路和文本链路共享同一套 session authority。

## 协议分发与业务状态仍然分层

连接 authority 收敛之后，并不意味着 controller 要接管聊天和音频的所有业务状态。相反，这次设计更强调“连接归连接，业务归业务”。

`useWebSocket()` 的默认 handler 负责把 session 事件交给业务运行时：

- `chat:chunk` -> `chatStore.appendStreamingChunk()`
- `chat:complete` -> `chatStore.completeStreaming()`
- `chat:interrupted` -> `chatStore.interruptStreaming()`
- `chat:error` -> `chatStore.failActiveStream()`
- `audio:segment` -> `audioPlayer.enqueueAudioSegment()`
- `audio:error` -> `audioPlayer.skipAudioSegment()`
- `audio:complete` -> `audioPlayer.completeAudioGeneration()`
- `asr:transcript` -> `chatStore.addAsrTranscriptMessage()`
- `vad:interrupt` -> `audioPlayer.vadInterruptPlayback()` 与 `chatStore.markActiveStreamInterrupted()`

但这些业务函数仍然要自己判断上下文归属。例如：

- 当前聊天是否仍是事件里的 `chat_id`。
- 当前角色是否仍是事件里的 `character_id`。
- 当前 `generation_id` 是否仍然可见。
- 音频段的 `sequence` 是否有效、是否已经被丢弃。

这也是长期模块文档里的核心不变量：前端宁可丢弃旧结果，也不能把旧文本或旧音频串到新上下文里。

## 验收

这次验收不只看“能不能发一条消息”，而是看 authority 是否真的收敛。

结构性验收点包括：

- `WebSocketManager.send()` 统一基于 `readyState === OPEN` 判断，并捕获底层 `socket.send()` 异常。
- `WebSocketSessionController` 成为唯一 active manager 持有者。
- `sessionEpoch` 能拦截 stale manager 事件。
- `wsStore` 不再持有 `wsManager`，不再提供 `send()` 或 `sendIfOpen()`。
- `useWebSocket()` 成为业务 facade，默认协议 handler 只注册一次。
- `index.vue` 是页面级 `connect()/disconnect()` 入口。
- `useChat()` 和 `useRealtimeVoiceInput()` 都通过 `sendText/sendAudioChunk/sendAudioEnd` 出站。
- `wsStore.connected` 不再出现在发送阻塞路径里。
- deferred title 的前端 pending 和轮询只在 `sendText()` 成功后启动。

按前端基础检查执行：

```bash
npm run type-check
npm run lint
npm run build
```

结果为：

- `type-check` 通过。
- `build` 通过。
- `lint` 通过，保留仓库既有 warning：
  - `src/components/airi-ui/TransitionVertical.vue`
  - 两处 `@typescript-eslint/no-explicit-any`

这些检查说明本次重构没有引入新的类型、构建或 lint 阻塞项。

## 剩余边界

这次重构已经收敛了前端本地连接语义，但它没有把所有相关问题都顺手改掉。当前需要明确保留这些边界：

1. 连接仍是页面级生命周期，不是应用级常驻连接。
2. `canSend()` 只是预检，不是发送成功保证。
3. `wsStore.connected` 仍可用于 UI 展示和本地生命周期响应，但不能作为发送 authority。
4. 默认协议 handler 只能注册一次；后续不能在多个 composable 里重复制造副作用。
5. 实时语音仍要求明确的聊天和角色上下文，不把草稿聊天自动升级成实时语音会话。
6. `sessionEpoch` 只解决 WebSocket session 归属，不替代 `generation_id`、`chat_id`、`character_id` 的业务归属判断。
7. 当前仍使用 JSON float array 上行音频；切换到二进制帧或 `AudioWorklet` 属于后续优化，不改变本次 authority 边界。

尤其要强调 deferred title：本次只修正了前端本地状态。发送失败后，前端不再错误保留 pending title，也不再提前启动轮询。但后端 `createChat(..., defer_title=true)` 在 REST 创建成功后可能启动的后台补标题任务，并没有被这次前端重构解决。这里不能写成“deferred title 语义已修复”，只能写成“前端本地状态已收敛”。

## 小结

这次 frontend websocket session refactor 的价值，不在于多了一层封装，而在于把几类容易混淆的 authority 放回了各自的位置：

- `WebSocketManager` 负责传输事实。
- `WebSocketSessionController` 负责 session authority。
- `useWebSocket()` 负责业务 facade。
- `wsStore` 负责 UI projection。
- `chat/audio/realtime voice` 运行时负责业务状态归属。

当“多份连接真相”被收敛后，前端的数据流就重新变得可推理：页面拥有连接生命周期，controller 判断当前 session，manager 判断底层可发送性，业务发送统一走 facade，而聊天、语音和音频各自保留自己的 generation 边界。对一个同时承载文本、语音、打断和分段播放的前端来说，这种边界清楚，比再多几个状态字段更重要。
