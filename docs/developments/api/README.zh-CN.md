# API 与协议文档

本目录收录 ATRI 当前对外稳定的接口说明。这里的“稳定”指前后端已经依赖、改动后需要同步通知调用方的行为，包括认证、REST 路由、WebSocket 消息和事件字典。

写接口代码、改协议、排查前后端联调问题时，建议按下面顺序阅读：

1. [auth.zh-CN.md](auth.zh-CN.md)：先确认认证模式、Cookie/Bearer 边界和 OAuth 回调语义。
2. [rest.zh-CN.md](rest.zh-CN.md)：查 HTTP 路由、请求体、响应体和通用错误。
3. [websocket.zh-CN.md](websocket.zh-CN.md)：查连接方式、实时聊天时序、VAD 打断和 TTS 分段行为。
4. [events.zh-CN.md](events.zh-CN.md)：按事件名查字段字典和消息示例。

## 文档索引

| 文档 | 说明 | 适合什么时候看 |
| --- | --- | --- |
| [auth.zh-CN.md](auth.zh-CN.md) | 认证 REST API、会话 Cookie、HTTP Bearer 兼容规则、WebSocket Cookie 鉴权、OAuth 回调结果约定。 | 登录失败、401、跨端调用、Cookie/会话问题。 |
| [rest.zh-CN.md](rest.zh-CN.md) | 健康检查、角色、聊天、数据维护、ASR、TTS、Live2D、静态资源和通用错误。 | 查业务 REST 路由或准备写调用代码。 |
| [websocket.zh-CN.md](websocket.zh-CN.md) | `/ws` 连接、鉴权、文本聊天流、实时语音/VAD 中断、TTS 分段流和关闭语义。 | 查实时协议、心跳、流式回复和语音链路。 |
| [events.zh-CN.md](events.zh-CN.md) | `input:*`、`output:*`、`control:*`、`error`、`pong` 的字段字典。 | 已经知道事件名，需要精确字段说明。 |

## 维护约定

- 本目录以当前源码为准，主要来源是 `src/routes/*.py`、`src/middleware/auth.py`、`src/auth/*`、`frontend/src/utils/websocket.ts` 和 `frontend/src/composables/useWebSocket.ts`。
- 旧 `docs/developments/module-design/CN/后端API接口文档.md` 只作为迁移素材，不再作为事实来源。
- 业务语义改变时，除了更新本目录，还应同步更新引用它的模块设计或 feature 文档。
- 临时调试记录、一次性验收 payload 和开发流水不要直接写进这里，应放回 `docs/developments/features/` 或 `docs/developments/wiki/`。
