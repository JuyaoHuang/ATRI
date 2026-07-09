---
status: active
owner: frontend
created: 2026-07-09
updated: 2026-07-09
related_code:
  - frontend/src/composables/useWebSocket.ts
  - frontend/src/utils/websocket.ts
  - frontend/src/utils/websocketSessionController.ts
  - frontend/src/stores/websocket.ts
  - frontend/src/composables/useChat.ts
  - frontend/src/composables/useRealtimeVoiceInput.ts
  - frontend/src/pages/index.vue
---

# Frontend WebSocket Session Refactor

本目录记录 2026-07 前端 WebSocket 会话重构的开发过程。它属于 feature 过程文档，用于追踪本次重构的目标、边界、实现顺序、验收结果和已确认的限制，不替代长期模块设计文档。

## 当前状态

- 状态：`active`
- 开发分支：`frontend/feat/websocket-session-refactor`
- 当前实现：已完成两次提交并通过前端基础检查
- 长期模块文档入口：`../../modules/frontend/chat-voice-runtime.zh-CN.md`

## 本次目标

1. 把 WebSocket 可发送性的唯一事实来源收敛到底层 `readyState === OPEN`。
2. 让 `wsStore.connected` 只承担 UI 展示职责，不再阻塞任何文本或实时音频发送。
3. 收敛连接入口，避免页面内多个组件分别 `connect()` 导致的重复连接与状态分裂。
4. 把协议分发和会话归属判断集中到单例 controller，减少散落在 composable/组件里的边界判断。

## 不在本次范围

- 不修改后端 WebSocket 协议字段、事件名、路由和鉴权方式。
- 不把连接策略升级为应用级常驻连接，仍按页面级生命周期管理。
- 不顺带重做 draft chat / create chat 的整体产品语义。
- 不解决后端 `createChat(..., defer_title=true)` 已经启动的后台补标题任务。

## 已完成实现摘要

- 新增单例 `WebSocketSessionController`，统一持有当前 manager、session epoch、连接状态和事件总线。
- `WebSocketManager` 收敛为传输层，只负责原生 socket、heartbeat、reconnect timer、原始消息解析和 `send()`。
- `wsStore` 降级为 UI projection，只保留 `connectionStatus` 与 `error`。
- `useWebSocket()` 变为 facade，对业务暴露 `canSend()`、`sendText()`、`sendAudioChunk()`、`sendAudioEnd()` 与事件订阅接口。
- 首页根层负责 `connect()/disconnect()`，`ChatArea` 与 `StageChatShell` 不再各自建立连接。
- `useChat()` 与 `useRealtimeVoiceInput()` 改为只信统一发送出口，不再通过 `wsStore.connected` 阻塞发送。

## 本次确认的边界

- `canSend()` 只是同源预检，不是发送成功保证；最终结果只认 `send*()` 返回值。
- `connectionStatus` 只是 UI 生命周期投影，不是发送 authority。
- 默认协议处理器只允许注册一次；`useWebSocket()` 多处调用不能重复注册副作用。
- 新建会话发送失败时，当前修复只收敛前端本地标题状态，不宣称阻止后端空 chat 被补标题。

## 子文档

| 文档 | 职责 |
|---|---|
| `dev-log.zh-CN.md` | 按阶段记录本次前端会话重构的动机、实现顺序、审查反馈和验收结果 |

## 阅读顺序

1. 先读本 README，了解本次 feature 的目标与边界。
2. 再读 `dev-log.zh-CN.md`，追踪从问题定位到实现落地的过程。
3. 最后回到长期模块文档和代码，理解这次 feature 产出的稳定结论。
