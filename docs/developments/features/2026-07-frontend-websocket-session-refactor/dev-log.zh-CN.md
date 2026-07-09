---
status: active
owner: frontend
created: 2026-07-09
updated: 2026-07-09
source:
  - frontend/AGENTS.md
  - docs/文档构建思路.md
related_code:
  - frontend/src/composables/useWebSocket.ts
  - frontend/src/utils/websocket.ts
  - frontend/src/utils/websocketSessionController.ts
  - frontend/src/stores/websocket.ts
  - frontend/src/composables/useChat.ts
  - frontend/src/composables/useRealtimeVoiceInput.ts
  - frontend/src/pages/index.vue
---

# Frontend WebSocket Session Refactor 开发日志

本文记录 2026-07-09 前端 WebSocket 会话重构的开发事实。重点保留问题定位、边界收敛、实现顺序、审查反馈和当前结论，不展开重复的上下文讨论。

## 2026-07-09 问题确认

### 观察到的现象

- 启动前后端后，页面可能长期显示“未连接”。
- 文本发送会因为 `WebSocket is not connected` 被前置拦截。
- 实时语音链路直接读取 `wsStore.connected` 与 `wsStore.wsManager`，前端内部存在多份连接真相。

### 根因归类

把现有判断沿着 WebSocket 数据流拆开后，可以看到四类职责被混在了一起：

1. 传输层事实：底层 `WebSocket.readyState`
2. UI 投影状态：`wsStore.connected / reconnecting`
3. 会话归属判断：当前 manager 是否仍是 active session
4. 业务发送入口：文本发送与实时音频发送能力

问题不在“判断太少”，而在“同一件事有多份真相，而且互相越权”。

## 2026-07-09 方案定稿

### 核心原则

- `readyState === OPEN` 是唯一底层发送事实来源。
- `wsStore.connected` 可以影响按钮样式和文案，但不能阻塞任何发送路径。
- 所有业务发送都必须经过 `useWebSocket().send*()`。
- `canSend()` 只做同源预检，最终是否成功只认 `send*()` 返回值。

### 结构决策

- 保留页面级连接，不升级为应用级常驻连接。
- 引入单例 `WebSocketSessionController`，集中持有当前 manager、session epoch 和事件总线。
- `WebSocketManager` 只保留传输层职责，不再负责协议消息到业务事件的映射。
- `useWebSocket()` 只做 facade，默认协议副作用只注册一次。

## 2026-07-09 Step 1 会话层重构

### 完成

- 新增 `frontend/src/types/websocket.ts`
  - 提供 `ConnectionStatus`
  - 提供聊天、音频、ASR、VAD 相关协议数据镜像类型
- 新增 `frontend/src/utils/websocketSessionController.ts`
  - 管理当前 `WebSocketManager`
  - 提供 `connect()` / `disconnect()` / `canSend()` / `send*()` / `on()` / `off()`
  - 通过 `sessionEpoch` 丢弃 stale session 事件
- 改造 `frontend/src/utils/websocket.ts`
  - `connect()` 会在重新连接前清理 pending reconnect timer
  - `send()` 统一基于 `readyState === OPEN` 判断，并捕获底层发送异常
  - 不再在 manager 内部把协议消息映射成 `chat:chunk` / `vad:interrupt`
- 改造 `frontend/src/stores/websocket.ts`
  - 删除 `wsManager`
  - 删除 `send()` / `sendIfOpen()`
  - 新增 `connectionStatus`
  - `connected / reconnecting` 变为 getter
- 改造 `frontend/src/composables/useWebSocket.ts`
  - 变成 facade
  - 统一注册默认协议处理器
  - 对外只暴露连接状态、发送能力和事件订阅
- 改造连接入口
  - `frontend/src/pages/index.vue` 负责 `connect()/disconnect()`
  - `ChatArea.vue`、`StageChatShell.vue` 删除各自的 `onMounted -> connect()`

### 对应提交

- `7c4ca34` `fix(websocket-session-refactor/step 1): centralize websocket session state`

## 2026-07-09 Step 2 发送链细化

### 背景

第一版会话层重构完成后，针对 `useChat()` 发送链又补做了两点小修：

1. `beginStreaming()` 的时机
2. 前端 deferred title 状态启动的时机

### 完成

- `beginStreaming()` 前移到 `sendText()` 之前
  - 目的不是宣称高概率竞态，而是让“本轮流式回复已开始等待”这个状态先落地，避免 `appendStreamingChunk()` 在结构上依赖隐含时序
- `markPendingDeferredTitle()` 与 `watchDeferredTitle()` 后移到 `sendText()` 成功之后
  - 这能阻止前端在发送失败时继续保留 pending title 状态并启动轮询

### 当前限制

- 后端 `createChat(..., defer_title=true)` 仍会在 REST 创建成功后立即启动 `_backfill_chat_title` 后台任务
- 因此本次修复只解决“前端标题状态与轮询提前启动”，**不解决**“远端空 chat 仍可能被后端按失败首条消息补标题”
- 对这个限制，当前 feature 只记录事实，不扩展到后端协议或产品语义修复

### 对应提交

- `f96cbec` `fix(websocket-session-refactor/step 2): delay deferred title after send`

## 2026-07-09 审查反馈收敛

### 已采纳

- `canSend()` 只是预检，不是成功保证
- `RECONNECTING` 状态下允许 connect kick，但 manager 必须先清 timer
- 默认协议处理器只注册一次
- `wsStore.connected` 不再出现在任何发送阻塞路径里

### 已确认但不继续扩展

- `audioPlayer.stopBecauseContextChanged()` 的前后顺序只会带来极小的体验差异
- 在当前实现中，它位于 `sendText()` 前；从用户体验收益看，不值得继续为这个小点扩大改动范围

## 验证

在 `frontend/` 子仓库按 AGENTS 要求执行：

```bash
npm run type-check
npm run lint
npm run build
```

### 结果

- `type-check` 通过
- `build` 通过
- `lint` 通过，保留既有 warning：
  - `src/components/airi-ui/TransitionVertical.vue`
  - 两处 `@typescript-eslint/no-explicit-any`

## 当前结论

本次 feature 的核心目标已经达成：

- 前端连接真相收敛到单例 controller
- `readyState === OPEN` 成为唯一底层发送事实来源
- `wsStore.connected` 退回为 UI projection
- 页面级连接入口收敛完成
- 文本发送与实时音频发送都改走统一 facade

仍保留的非核心边角限制：

- 远端空 chat 的后台补标题任务并未被本次前端修复阻止
- 音频停止时机的小顺序问题经评估可暂不处理
