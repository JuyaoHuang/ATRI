---
status: active
owner: routes
created: 2026-07-09
updated: 2026-07-09
related_code:
  - src/app.py
  - src/main.py
  - src/routes/
---

# Routes 模块长期设计

本目录沉淀 `src/routes/` 的长期设计。这里描述的是“路由层如何消费 app state 和后端服务模块”，而不是重复列出完整 API 字段表。具体接口协议仍以 `docs/developments/api/` 为准。

## 当前文档

| 文档 | 内容 |
| --- | --- |
| [design.zh-CN.md](design.zh-CN.md) | 路由层总设计，覆盖 app state 注入、HTTP 与 WebSocket 分工、各路由模块职责和错误/依赖边界。 |

## 模块边界

Routes 模块负责：

- 把后端能力暴露为 HTTP 路由或 WebSocket 端点。
- 从 `app.state` 取出共享服务对象，并做请求级依赖注入。
- 把领域异常映射成 HTTP 状态码或 WebSocket 错误事件。

它不负责：

- 持久化业务数据。
- 构造 LLM 上下文。
- 直接管理角色、记忆、ASR、TTS、VAD 的内部状态机。

## 阅读路径

建议按下面顺序阅读：

1. [design.zh-CN.md](design.zh-CN.md)
2. `src/app.py`
3. `src/routes/chats.py`
4. `src/routes/chat_ws.py`
5. 交叉核对 `docs/developments/api/`
