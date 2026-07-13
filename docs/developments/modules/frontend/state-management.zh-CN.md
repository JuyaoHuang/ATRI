---
status: active
owner: frontend
created: 2026-07-09
updated: 2026-07-13
source:
  - ../../module-design/CN/前端设计文档.md
  - ../../features/2026-07-frontend-websocket-session-refactor/README.zh-CN.md
  - ../../features/2026-07-frontend-websocket-session-refactor/dev-log.zh-CN.md
related_code:
  - frontend/src/stores/chat.ts
  - frontend/src/stores/chats.ts
  - frontend/src/stores/characters.ts
  - frontend/src/stores/user.ts
  - frontend/src/stores/websocket.ts
  - frontend/src/stores/live2d.ts
  - frontend/src/stores/settings.ts
  - frontend/src/stores/asr.ts
  - frontend/src/stores/tts.ts
  - frontend/src/stores/vision.ts
  - frontend/src/utils/websocketSessionController.ts
  - frontend/src/utils/visionSessionController.ts
  - frontend/src/composables/useWebSocket.ts
  - frontend/src/composables/useChat.ts
---

# Frontend 状态管理设计

本文沉淀 `frontend/src/stores/` 和 WebSocket 会话层的长期状态设计。目标不是罗列所有字段，而是说明：

1. 哪些状态属于后端真相的前端投影。
2. 哪些状态属于浏览器本地偏好。
3. 哪些状态是页面级运行时临时态，不能持久化成业务真相。

## 状态分层

当前前端状态可以稳定分成三类：

| 类别 | 典型 store / 对象 | 真相来源 |
| --- | --- | --- |
| 业务投影 | `chat` `chats` `characters` `user` `asr` `tts` `vision.config` | 后端 REST / WebSocket |
| 浏览器偏好 | `live2d` `settings` `user.settings` 局部字段 | `localStorage` |
| 运行时会话 | `websocketSessionController`、`visionSessionController`、`chat.activeStream` | 页面生命周期内的内存状态 |

长期原则：

- 后端拥有的业务状态，不在前端做第二份长期缓存。
- 浏览器偏好只保存展示和设备选择，不保存业务数据。
- 会话临时态一旦刷新页面即可丢失，不应被当作持久事实。

## Store 拓扑

### `chat` store

`chat` store 是当前聊天页的运行时真相，负责：

- `currentChatId`
- `currentCharacterId`
- `timelineItems`
- `streamingText`
- `activeStream`
- `pendingInterruptedStream`
- `draftChatId`
- deferred title 相关标记

它有两个关键特点：

1. `timelineItems` 只表示当前打开聊天的运行时时间线，不是聊天列表总仓库。
2. `messages` getter 只过滤 `kind=message`，供只接受正常消息的消费者使用。
3. `kind=notice` 表示当前页面瞬态提示，不是 ChatStorage 消息。
4. `activeStream` 是“当前等待或正在接收的 AI generation”，不是网络连接状态；pending 阶段还保存短生命周期 `requestId`，用于精确恢复被后端拒绝的输入。

### `chats` store

`chats` store 管理聊天标题列表和草稿聊天生命周期，负责：

- 拉取某角色下聊天列表；
- 创建真实聊天；
- 插入 `draft_*` 草稿；
- 替换草稿为真实 `chat_id`；
- 轮询 deferred title；
- 删除与改名。

它不负责：

- 当前聊天消息正文；
- WebSocket 流式文本；
- TTS/VAD 事件。

### `characters` store

`characters` store 负责角色列表、详情缓存和当前选中角色 ID。

它的职责边界是：

- 对角色卡 CRUD 做前端投影；
- 为聊天消息补角色名和头像；
- 为首页和设置页提供角色选择状态。

### `user` store

`user` store 分成两块状态：

1. `auth`
   - 是否启用认证
   - 当前用户资料
   - 登录态初始化状态
   - 登录时间戳
2. `settings`
   - 本地昵称
   - 本地头像文件名

长期边界：

- 认证会话凭据不存这里。
- `signedInAt` 只是 UX 辅助字段，不是权限判断依据。
- 真正的鉴权仍以后端 Cookie 会话和 `/api/auth/me` 为准。

### `websocket` store

`websocket` store 现在故意做得很薄，只保留：

- `connectionStatus`
- `error`

这是近期 WebSocket session refactor 的稳定结论：`wsStore` 只承担 UI projection，不再承担发送 authority。

### `live2d` store

`live2d` store 是最重的本地偏好 store，负责：

- 是否启用舞台；
- 当前模型 ID；
- 位置、缩放、FPS、render scale；
- 表情开关、默认表情和 LLM 暴露模式。

这里保存的是“如何展示模型”，不是“模型资源真相”。模型列表和表情列表仍来自后端 API。动作定义、当前动作和第三方运行时实例不进入 store；模型原生 Idle 与点击动作由画布运行时内部处理。模型文件直接使用后端 URL，并复用浏览器标准 HTTP 缓存。

### `settings` store

`settings` store 当前只管理背景设置：

- `imageUrl`
- `opacity`
- `blur`

它不承担通用全局设置仓库的职责。其他模块偏好各自保存在对应 store。

### `asr` / `tts` store

这两个 store 都属于“后端模块配置的前端投影”：

- 通过 REST 加载当前配置和 Provider 列表；
- 维护少量前端专属开关或设备选择；
- 对配置写入做白名单过滤。

它们不自己定义后端模块真相。

### `vision` store 与 controller

视觉状态刻意拆成两层：

| 层 | 保存内容 | 禁止保存 |
| --- | --- | --- |
| `vision` Pinia store | 后端安全配置投影、`loaded/loading/saving/error`、轻量运行时状态 | `MediaStream`、video、Canvas、Blob、图片字节、Base64、data URL |
| `visionSessionController` | 当前标签页的 `MediaStream`、video track、隐藏 video、启动 Future | 后端持久化配置 |

`vision.config.enabled` 来自后端 `GET /api/vision/config`，设置页通过 PUT 更新。`runtimeStatus` 只是 controller 的 UI 投影，不能写回 YAML，也不会跨刷新恢复。

controller 是跨路由单例。设置页、`VisionInput` 或 `InputBox` 卸载不得停止有效 tracks；只有显式停止、模块禁用、track `ended` 或页面销毁才释放资源。

## WebSocket 会话层

近期前端重构后，WebSocket 有一个清晰的三层结构：

| 层 | 代码 | 职责 |
| --- | --- | --- |
| 传输层 | `WebSocketManager` | 原生 socket、heartbeat、reconnect timer、原始 `send()` |
| 会话层 | `WebSocketSessionController` | 当前 active manager、session epoch、事件总线、发送入口 |
| facade 层 | `useWebSocket()` | 暴露业务事件、统一默认 handler、副作用汇总 |

长期约束：

1. `readyState === OPEN` 是唯一底层发送事实来源。
2. `wsStore.connected` 不能再作为发送阻塞条件。
3. 文本和实时音频发送都必须走 `useWebSocket().send*()`。
4. 事件协议分发只保留一处默认处理器。
5. 图片 payload 只作为 `sendText()` 或 `sendVisionCaptureResult()` 的局部参数存在，不进入事件总线的长期状态。

## 聊天发送状态机

`useChat.sendMessage()` 和 `chat/chats` 两个 store 共同维护当前聊天发送状态机：

```text
reserveSubmission()
  -> no current chat
  -> insertDraftChat()
  -> createChat(defer_title=true)
  -> replaceDraftChat()
  -> captureForSubmission()
  -> beginStreaming()
  -> sendText()
  -> pending deferred title poll
```

这里有五个长期边界：

1. 草稿聊天是前端 UI 过渡态，不是后端资源。
2. `beginStreaming()` 发生在 `sendText()` 前，用来先建立本地等待态。
3. deferred title 轮询只在 `sendText()` 成功后启动，避免前端自造假 pending 状态。
4. `submissionPending` 从截图开始前持续到发送完成，防止同一段文本在截图等待期间重复提交。
5. 截图 unavailable、编码失败或完整图片 JSON 帧超限时，只把同一段文本发送一次，不显示本地错误气泡。

## 流式回复状态机

`chat` store 里最核心的两个运行时对象是：

- `activeStream`
- `pendingInterruptedStream`

它们负责表达：

- 当前 generation 是否等待中、流式中、已被 interrupt；
- 中断消息回来前，前端是否需要暂存一次“应该被 interrupt 收口”的流。

这套状态机的意义在于：

- `chat:chunk` 只能追加到当前 active stream；
- `chat:complete` 只能收口匹配中的 stream；
- `chat:interrupted` 可以把半截消息落地，但不能错绑到新聊天或新角色。

`output:chat:error` 使用同一 generation 关联规则进入 `failActiveGeneration()`：

- 必须匹配 `chatId + characterId + generationId`；
- 第一条完整关联事件可以给尚未绑定 ID 的 active stream 绑定 generation；
- stale failure 返回 `ignored`，不得终止更新的 generation；
- 当前聊天可见时追加 `kind=notice` 的错误气泡；
- 当前聊天不可见时只结束匹配的运行时，不插入 notice；
- failure 会清空 partial streaming text，并要求音频层丢弃同 generation 音频。

顶层协议 `error` 不会调用 `failActiveGeneration()`。它始终更新 `websocket.error`；只有 `chat_id + request_id` 匹配本地 pending stream 时，才调用 `rejectPendingSubmission()` 清理这一次被明确拒绝的输入。事件若携带 `character_id`，还必须与本地角色一致。stale request、无 request 的通用协议错误和已经 streaming 的 generation 都保持不变。

当 `control:interrupt.preserve_chat_generation=true` 时，音频层仍执行 VAD 停播，但 `markActiveStreamInterrupted()` 返回 `ignored`。这表示后端已经认领 durable commit，前端必须保留文本 stream 等待 complete。

## 运行时丢弃规则

当前前端有四类“宁可丢弃也不串上下文”的保护：

1. WebSocket 会话层：
   - `sessionEpoch` 用来丢弃 stale manager 事件。
2. 聊天层：
   - `chatId + characterId + generationId` 共同决定消息是否还能落地。
3. 音频层：
   - `generation_id + sequence` 决定音频段是否还能入队。
4. 视觉层：
   - `generation_id` 决定 VAD 截图结果是否还能解析；未知或迟到结果直接丢弃。

这四层缺一不可。只保留其中一层，会出现：

- 旧连接事件写回新页面；
- 旧聊天 chunk 混入新聊天；
- 旧 generation 的 TTS 在切换聊天后继续播放。

## 本地持久化规则

当前前端本地持久化的边界如下：

| 键 | 语义 |
| --- | --- |
| `atri-background-settings` | 背景偏好 |
| `atri-live2d-settings` | 舞台偏好 |
| `settings/hearing/enabled` | 前端 ASR 总开关 |
| `settings/hearing/audio-input` | 当前麦克风设备 |
| `atri_user_settings` | 本地昵称和头像文件名 |
| `atri_auth_signed_in_at` | 登录完成时间 |
| `atri_auth_redirect` | 登录成功后的目标路由 |

这些键只服务于浏览器 UX，不服务于业务真相。

不应在本地存的内容：

- bearer token
- 聊天列表与消息历史
- 短期记忆或长期记忆
- Provider 密钥
- 后端模块完整配置镜像
- 视觉截图、Base64、data URL、MediaStream 或“已授权”状态
- generation failure notice

## 初始化顺序

当前前端启动和进入聊天页时，稳定顺序是：

1. `router.beforeEach()` 执行 `userStore.initializeAuth()`。
2. `/` 页面 `onMounted()` 调 `connect()`。
3. 首页同时拉角色列表和 Live2D 模型列表。
4. `useWebSocket()` 默认 handler 在首次使用时注册一次。
5. 各组件只消费 facade，不重复创建连接。
6. `VisionInput` 首次挂载时确保视觉配置已加载，但不会自动调用 `getDisplayMedia()`。

这条顺序的意义是：

- 路由守卫先确认认证模式；
- 页面进入后只建立一条业务 WebSocket；
- 组件层不再偷偷创建第二条连接。

## 扩展约束

后续扩展前端状态时，应保持以下规则：

1. 新 store 先判断它属于业务投影、浏览器偏好，还是运行时临时态。
2. 需要跨刷新持久化时，必须先说明为什么后端不拥有这份真相。
3. 任何发送逻辑都不能再读 `wsStore.connected` 做 authority 判断。
4. 若新增 WebSocket 业务事件，先补 `types/websocket.ts`，再经 controller 分发。
5. 若新增聊天运行时状态，优先落到 `chat` store，而不是散在多个 composable 的局部 ref。
6. 浏览器原生对象若需要跨路由存活，应由单例 controller 持有，不得塞入 Pinia。
7. 图片等大字段只能短生命周期传递，不得为了调试进入 store、console 或持久化插件。

## 相关文档

- [README.zh-CN.md](README.zh-CN.md)
- [chat-voice-runtime.zh-CN.md](chat-voice-runtime.zh-CN.md)
- [stage-and-settings.zh-CN.md](stage-and-settings.zh-CN.md)
- [../../features/2026-07-frontend-websocket-session-refactor/README.zh-CN.md](../../features/2026-07-frontend-websocket-session-refactor/README.zh-CN.md)
- [Vision 模块长期设计](../vision/README.zh-CN.md)
