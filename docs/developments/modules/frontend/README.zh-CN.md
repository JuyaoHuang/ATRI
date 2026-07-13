---
status: active
owner: frontend
created: 2026-07-09
updated: 2026-07-13
related_code:
  - frontend/src/router/
  - frontend/src/pages/
  - frontend/src/components/
  - frontend/src/stores/
  - frontend/src/composables/
---

# Frontend 模块长期设计

本目录沉淀 `frontend/` Web 客户端的长期设计。这里描述前端的职责边界、运行时约束和设置面组织；一次性开发过程、阶段性验收和旧讨论记录不放在这里。

## 模块定位

ATRI 前端是后端 FastAPI 服务之上的单页应用，负责：

- 组织首页、登录页、设置页等路由与页面结构。
- 渲染聊天、角色选择、聊天历史、Live2D 舞台和设置界面。
- 通过 REST API 读取角色、聊天、模块配置和数据维护接口。
- 通过业务 WebSocket `/ws` 消费聊天文本流、视觉截图握手、ASR/VAD 控制事件和 TTS 音频事件。
- 管理当前浏览器标签页的屏幕共享运行时，并按轮次提供短生命周期截图。
- 管理浏览器本地偏好，例如背景、发送快捷键、Live2D 舞台参数和部分设备选择。

前端不负责：

- 持久化聊天历史、短期记忆或长期记忆。
- 保存认证会话凭据、Provider 密钥或后端模块敏感配置。
- 决定聊天历史、记忆压缩和 TTS Provider 的最终语义。

## 当前文档

| 文档 | 内容 |
| --- | --- |
| [design.zh-CN.md](design.zh-CN.md) | Frontend 模块总设计，串起首页双态、状态分层、传输面设计、WebSocket session 和设置页边界。 |
| [state-management.zh-CN.md](state-management.zh-CN.md) | 前端 store 拓扑、WebSocket 会话层、聊天运行时状态机和本地持久化边界。 |
| [chat-voice-runtime.zh-CN.md](chat-voice-runtime.zh-CN.md) | 文本聊天、单次/实时语音、屏幕视觉、generation failure 和自动 TTS 的运行时设计。 |
| [chat-markdown-rendering.zh-CN.md](chat-markdown-rendering.zh-CN.md) | 静态消息 Markdown/KaTeX、安全清洗、有界缓存和动态虚拟时间线。 |
| [stage-and-settings.zh-CN.md](stage-and-settings.zh-CN.md) | 首页双态布局、Live2D 舞台、设置系统、路由守卫和本地偏好持久化边界。 |

## 前后端边界

| 主题 | 前端职责 | 后端职责 |
| --- | --- | --- |
| 认证 | 登录页、回调页、路由守卫、会话状态展示 | GitHub OAuth、Cookie 会话、`/api/auth/*` 协议 |
| 聊天 | 输入框、消息列表、草稿会话、本地流式状态 | 聊天持久化、标题生成、`/api/chats`、`/ws` |
| 角色 | 角色列表、表单、导入导出 UI | Persona 文件、头像托管、`/api/characters` |
| Live2D | 舞台渲染、位置参数、OPFS 缓存、表情请求 | 模型上传、模型元数据、静态资源托管 |
| ASR/TTS | 设置页、浏览器采集、音频播放、自动发送体验 | Provider 配置、模块开关、转写/合成、VAD 与 TTS 事件 |
| Vision | 设置页投影、屏幕共享、截图与瞬态错误 UI | 模块配置、图片校验、VAD 截图协调、LLM 多模态调用 |
| 数据维护 | 删除确认、清理入口、结果提示 | 聊天文件删除、短期记忆清理、长期记忆删除提交 |

## 设计原则

1. 后端拥有业务真相：聊天、记忆、认证、模块配置都以后端接口为准。
2. 前端只持久化浏览器偏好，不复制一套业务配置镜像。
3. 文本流、音频流和 VAD 控制共用一条业务 WebSocket，但各自生命周期独立。
4. `generation_id` 是自动 TTS 与实时打断的失效边界，前端必须据此丢弃旧结果。
5. 首页布局可以切换为 Live2D 舞台模式，但不能改变聊天、记忆和认证协议。
6. MediaStream、图片 Base64 和 generation notice 都是运行时数据，不进入前端持久化。

## 阅读路径

建议按以下顺序阅读：

1. 本 README，确认前端边界和文档分工。
2. [design.zh-CN.md](design.zh-CN.md)，理解前端整体结构与传输面。
3. [state-management.zh-CN.md](state-management.zh-CN.md)，理解 store 拓扑、发送 authority 和本地持久化规则。
4. [chat-voice-runtime.zh-CN.md](chat-voice-runtime.zh-CN.md)，理解聊天、ASR、VAD 和 TTS 的运行时主链路。
5. [chat-markdown-rendering.zh-CN.md](chat-markdown-rendering.zh-CN.md)，理解静态消息的安全渲染与长历史性能边界。
6. [stage-and-settings.zh-CN.md](stage-and-settings.zh-CN.md)，理解首页双态布局、设置入口和本地偏好。
7. 交叉核对相关后端模块文档：
   - [../../modules/auth/README.zh-CN.md](../../modules/auth/README.zh-CN.md)
   - [../../modules/storage/README.zh-CN.md](../../modules/storage/README.zh-CN.md)
   - [../../modules/memory/README.zh-CN.md](../../modules/memory/README.zh-CN.md)
   - [../../modules/tts/README.zh-CN.md](../../modules/tts/README.zh-CN.md)
   - [../../modules/vision/README.zh-CN.md](../../modules/vision/README.zh-CN.md)
   - [../../features/2026-06-vad-realtime-interrupt/README.zh-CN.md](../../features/2026-06-vad-realtime-interrupt/README.zh-CN.md)

## 收录规则

本目录只收录跨版本仍应遵守的前端设计结论，例如：

- 路由与页面职责。
- WebSocket 事件消费边界。
- 首页舞台模式与默认聊天模式的关系。
- 本地偏好与后端配置的所有权。

以下内容继续留在 `features/`、`wiki/` 或 `archive/`：

- 某次开发的阶段拆分、分支名和 PR 状态。
- 已过期的旧目录结构或单独分仓假设。
- 已被后端接口替代的前端本地存储方案。
- 一次性排障过程和临时调试记录。
