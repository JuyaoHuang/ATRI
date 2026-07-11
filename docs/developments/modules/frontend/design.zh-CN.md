---
status: active
owner: frontend
created: 2026-07-09
updated: 2026-07-11
source:
  - ../../module-design/CN/前端设计文档.md
  - ../../features/2026-07-frontend-websocket-session-refactor/README.zh-CN.md
  - frontend/src/router/index.ts
  - frontend/src/pages/index.vue
  - frontend/src/composables/useWebSocket.ts
related_code:
  - frontend/src/router/index.ts
  - frontend/src/pages/index.vue
  - frontend/src/composables/useWebSocket.ts
  - frontend/src/stores/
  - frontend/src/components/
---

# Frontend 模块总设计

本文把 `frontend/` 的整体设计接起来。现有文档已经分别讲了状态管理、聊天语音运行时和舞台/设置，但还需要一页说明：

1. 前端在整个系统中的角色。
2. 首页、设置页、WebSocket 和本地偏好为什么这样划分。
3. WebSocket session 与屏幕视觉单例如何承担跨组件运行时。

## 模块定位

当前前端是一个建立在后端 FastAPI 之上的单页应用。它的职责不是复制一套后端业务，而是把后端协议组织成可用的浏览器体验：

- 首页聊天与舞台
- 登录与回调
- 设置页
- 音频播放器
- 本地偏好

它在系统中的位置更接近：

```text
REST + WebSocket protocol
  -> frontend stores / composables
  -> pages / components
  -> browser UX
```

## 设计目标

结合旧前端设计文档和近期 session refactor，长期目标已经收敛为 5 条：

1. 后端拥有业务真相，前端只保存浏览器偏好和运行时态。
2. 首页支持普通聊天模式和 Live2D 舞台模式，但不改变业务协议。
3. 文本聊天、屏幕视觉、实时语音和自动 TTS 共享同一套 generation 生命周期。
4. WebSocket 连接状态、发送 authority 和 UI 投影必须分层。
5. 设置页只暴露稳定 API 或明确归属的本地偏好。

## 模块组成

当前前端可以稳定拆成四层：

| 层 | 代码 | 职责 |
| --- | --- | --- |
| 路由与页面 | `router/index.ts` `pages/` | 首页、登录、回调、设置页结构 |
| 组件层 | `components/` | 侧边栏、聊天区、舞台、设置面板 |
| 状态与组合层 | `stores/` `composables/` | 聊天、角色、认证、WebSocket、音频、Live2D 等运行时逻辑 |
| 传输层 | `api/` `utils/websocket.ts` | REST 请求和 WebSocket 底层连接 |

## 首页双态设计

首页 `pages/index.vue` 当前支持两种模式：

- 普通聊天模式
- Live2D 舞台模式

两种模式共享：

- 当前角色
- 当前聊天
- WebSocket 连接
- 音频播放器
- 跨路由 `visionSessionController`

长期约束：

- 切换模式只改变页面布局；
- 不改变聊天、认证、记忆或音频协议；
- Live2D 是主视觉差异，不是第二套业务系统。

## 状态设计

前端状态已经稳定分成三类：

1. 业务投影
   - `chat` `chats` `characters` `user` `asr` `tts`
2. 浏览器偏好
   - `live2d` `settings` `user.settings`
3. 运行时临时态
   - WebSocket session controller
   - Vision session controller 与 MediaStream
   - `activeStream`
   - 音频队列

这条分层是近期前端设计最重要的收敛结果之一。

## 传输面设计

当前前端只有两条正式业务传输面：

- REST
- WebSocket `/ws`

REST 负责：

- 列表与详情
- 配置页读取/写入
- 模型/角色管理
- 数据清理

WebSocket 负责：

- 文本流式聊天
- VAD 控制事件
- ASR transcript 事件
- TTS 分段音频事件
- 屏幕共享状态、截图请求/结果和 generation failure

这两条面长期共存，前端不会试图把一切都折叠到 WebSocket，也不会为了流式聊天放弃 REST。

## WebSocket session 设计

近期 feature `2026-07-frontend-websocket-session-refactor` 已经把前端连接语义收敛为：

- `WebSocketManager`：原生传输层
- `WebSocketSessionController`：单例会话层
- `useWebSocket()`：业务 facade
- `wsStore`：UI projection

长期约束：

1. `readyState === OPEN` 是唯一发送事实来源。
2. `wsStore.connected` 不能再作为发送 authority。
3. 页面级连接入口收敛到首页。
4. 默认协议处理器只能注册一次。

这不仅是某次修 bug，而是当前前端运行时结构的一部分。

## generation 作为统一边界

当前前端里，`generation_id` 已经成为三条链路共享的边界：

- 文本流式回复
- VAD interrupt
- TTS 分段音频

这意味着：

- 旧文本 chunk 不能落到新聊天；
- 旧音频 segment 不能在上下文切换后继续播放；
- `control:interrupt` 必须同时影响流式回复和音频队列。

长期上，这组规则比“某个按钮怎么显示”更重要。

## 设置页设计

当前设置页已经收敛成“稳定能力入口”，而不是“任意草稿功能集合”。

已稳定的主要入口包括：

- 账户设置
- 角色卡管理
- TTS 配置
- ASR 配置
- 场景设置
- Live2D 模型设置
- 数据管理

仍是占位或开发中的页面，不能写成当前完整能力。

## 本地持久化边界

前端会长期持久化的内容包括：

- 背景设置
- Live2D 偏好
- 麦克风设备选择
- 本地昵称与头像文件名
- 登录完成时间和 redirect

不应持久化为业务真相的内容包括：

- 聊天消息与聊天列表
- 认证真正凭据
- Provider 密钥
- 记忆状态
- 后端模块完整配置

这条边界贯穿了当前整个前端模块设计。

## 与旧前端设计文档的取舍

旧 `前端设计文档.md` 中，已经被当前实现吸收并保留的骨架包括：

- 双态首页
- store 化管理
- WebSocket + REST 双传输面
- 设置页分区
- Live2D 前后端职责划分

不再应被当作当前事实的部分包括：

- 旧 token / LocalStorage 认证主路径
- 多个占位 Phase 规划直接等同于当前功能
- 一些尚未落地的系统页和性能/部署规划

因此当前总设计更强调“已实现且稳定的交互结构”，而不是把旧计划全文复刻一遍。

## 相关文档

- [state-management.zh-CN.md](state-management.zh-CN.md)
- [chat-voice-runtime.zh-CN.md](chat-voice-runtime.zh-CN.md)
- [stage-and-settings.zh-CN.md](stage-and-settings.zh-CN.md)
