---
status: active
owner: auth
created: 2026-07-09
updated: 2026-07-09
related_code:
  - src/routes/auth.py
  - src/middleware/auth.py
  - src/auth/dependencies.py
  - src/auth/service.py
  - src/auth/session.py
  - frontend/src/api/auth.ts
  - frontend/src/pages/auth-callback.vue
  - frontend/src/utils/websocket.ts
---

# 认证 API 与鉴权协议

这份文档只回答一件事：客户端应该怎样和当前认证实现正确对接。

先看结论：

- 浏览器主路径使用 `HttpOnly` 会话 Cookie `atri_session`。
- HTTP REST 路由兼容 `Authorization: Bearer <JWT>`，但浏览器默认走 Cookie。
- WebSocket 只读取 Cookie，不支持 `?token=` 主路径，也不读取 Bearer 头。
- OAuth 回调成功标志只有 `success=1`；前端随后再调用 `/api/auth/me` 拉取当前用户。
- `POST /api/auth/logout` 只负责清理会话 Cookie，不要求先认证成功。

## 运行模式

| 模式 | 条件 | 用户身份 | 典型场景 |
| --- | --- | --- | --- |
| 本地模式 | `auth.enabled = false` | 固定用户 `default` | 本地开发、单机使用 |
| 部署模式 | `auth.enabled = true` | GitHub OAuth + JWT + 白名单用户 | 公网部署、多人访问 |

本地模式下：

- `/api/auth/status` 返回 `{"enabled": false}`。
- `/api/auth/login` 返回 `{"enabled": false, "authorization_url": null}`。
- `/api/auth/me` 返回 `username=default` 且 `auth_enabled=false`。
- WebSocket 不要求 Cookie，后端仍把连接归到 `default` 用户。

## Cookie 与凭证规则

### 会话 Cookie

| 名称 | 用途 | Path | 属性 | 说明 |
| --- | --- | --- | --- | --- |
| `atri_session` | 登录后的会话 JWT | `/` | `HttpOnly`, `SameSite=Lax` | `Secure` 由 `auth.frontend.callback_url` 是否为 `https://` 决定。`Max-Age` 取自 `auth.jwt.expire_days`。 |
| `atri_oauth_state` | OAuth state 防重放校验 | `/api/auth` | `HttpOnly`, `SameSite=Lax` | `Secure` 由 GitHub OAuth callback URL 是否为 `https://` 决定。有效期 10 分钟。 |

### 凭证优先级

| 通道 | 支持的凭证 | 规则 |
| --- | --- | --- |
| 浏览器 HTTP | `atri_session` Cookie | 默认主路径。前端 `axios` 已启用 `withCredentials: true`。 |
| 非浏览器 HTTP | `Authorization: Bearer <JWT>` | 适合脚本、测试或不能共享浏览器 Cookie 的调用方。 |
| HTTP 同时带 Cookie 和 Bearer | Cookie 优先 | 后端先验证 `atri_session`，再回退到 Bearer。 |
| WebSocket `/ws` | `atri_session` Cookie | 只读 Cookie。缺失或无效时直接拒绝连接。 |

如果认证开启，除了 `/api/auth`、公开静态资源、`/health`、`/docs`、`/redoc` 和 `/openapi.json`，其余 HTTP 路由都会先经过认证中间件。

## 认证接口

| 方法 | 路径 | 认证要求 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/auth/status` | 否 | 返回当前实例是否启用认证。 |
| `GET` | `/api/auth/login` | 否 | 生成 GitHub 授权地址，并在响应中设置 `atri_oauth_state` Cookie。 |
| `GET` | `/api/auth/callback` | 否 | GitHub OAuth 回调入口。成功时设置 `atri_session` Cookie 并重定向到前端回调页。 |
| `GET` | `/api/auth/me` | 本地模式否；部署模式是 | 返回当前用户资料。本地模式固定返回 `default`。 |
| `POST` | `/api/auth/logout` | 否 | 清除 `atri_session` Cookie，并返回 `{"success": true}`。 |

### `GET /api/auth/status`

响应体很小，只用于前端先判定当前部署是“登录模式”还是“本地模式”。

```json
{
  "enabled": true
}
```

### `GET /api/auth/login`

返回值示例：

```json
{
  "enabled": true,
  "authorization_url": "https://github.com/login/oauth/authorize?client_id=..."
}
```

对接要点：

- 旧客户端仍可传 `state` 查询参数，但当前后端会忽略它，统一生成新的 server-side state。
- 真正用于防重放校验的是后端写入的 `atri_oauth_state` Cookie。
- 当前前端拿到 `authorization_url` 后会直接 `window.location.assign(...)` 跳转到 GitHub。

### `GET /api/auth/callback`

这是 GitHub OAuth App 的回调地址，面向 GitHub，不面向业务前端直接调用。后端完成授权码交换后，会重定向到配置中的前端回调地址。

当前前端只认下面三类结果：

| 回调结果 | 前端应该看什么 | 说明 |
| --- | --- | --- |
| 成功 | `success=1` | 后端已设置 `atri_session` Cookie。前端下一步调用 `/api/auth/me`。 |
| 认证关闭 | `auth=disabled` | 认证未启用，前端进入本地模式。 |
| 失败 | `error=...`，可选 `detail=...` | 例如 `missing_code`、`invalid_state`、`unauthorized`、`github_oauth_failed`。 |

重要限制：

- 成功回调不会把 JWT 放进 URL。
- 不要依赖 `token`、`access_token` 或其他 URL 参数。
- 如果 `state` 校验失败，但浏览器已经持有一个有效的 `atri_session`，后端仍会把这次回调视为成功并重定向到 `?success=1`。这让用户重复打开回调页时更稳定。

### `GET /api/auth/me`

部署模式下，后端按“Cookie 优先、Bearer 回退”的顺序解析用户：

```http
GET /api/auth/me
Authorization: Bearer YOUR_JWT
```

成功响应示例：

```json
{
  "username": "octocat",
  "avatar_url": "https://avatars.githubusercontent.com/u/583231?v=4",
  "name": "The Octocat",
  "auth_enabled": true
}
```

本地模式响应示例：

```json
{
  "username": "default",
  "avatar_url": null,
  "name": null,
  "auth_enabled": false
}
```

### `POST /api/auth/logout`

这是一个“幂等清 Cookie”接口。当前实现不会先检查你是否已登录，也不会要求 Bearer 或 Cookie 先通过认证。

```json
{
  "success": true
}
```

这意味着下面两种情况都会得到成功响应：

- 当前浏览器持有有效会话，需要主动登出。
- 当前浏览器本来就没有会话，只是想做一次清理。

## HTTP 鉴权规则

部署模式下，业务 REST 路由的认证行为如下：

1. 如果请求带有 `atri_session` Cookie，后端优先验证 Cookie。
2. 如果没有 Cookie，再尝试 `Authorization: Bearer <JWT>`。
3. 两者都没有时，返回 `401`，错误详情通常是 `Missing session cookie`。

这条规则适合两类调用方：

- 浏览器前端：依赖 Cookie 即可，不需要自行管理 JWT。
- 脚本或测试工具：如果没有浏览器 Cookie 上下文，可以显式带 Bearer。

## WebSocket 鉴权规则

WebSocket 主路径只有一个：

```text
wss://YOUR_BACKEND/ws
```

不要这样接：

```text
wss://YOUR_BACKEND/ws?token=...
```

当前后端在握手前只做一件事：从 Cookie 中读取 `atri_session`。因此：

- 认证开启时，缺少 Cookie、Cookie 过期、JWT 无效或用户不在白名单，连接会在 `accept()` 之前以 close code `1008` 结束。
- 认证关闭时，`/ws` 直接进入本地模式，不要求任何凭证。
- 由于浏览器原生 `WebSocket` 不能像 `fetch` 一样随意设置认证头，当前前端也没有附加 Bearer 的实现；协议文档因此把“Cookie 会话”视为唯一正式的 WebSocket 鉴权方式。

## OAuth 回调页约定

当前前端回调页 `frontend/src/pages/auth-callback.vue` 的判断顺序是：

1. `auth=disabled`
2. `error=...`
3. `success=1`

只有第 3 种会被视为真正登录成功。成功后前端会调用 `/api/auth/me`，而不是从 URL 中提取令牌。

## 常见错误

| 场景 | HTTP/连接结果 | 常见 detail 或参数 |
| --- | --- | --- |
| 未带会话 Cookie | `401` | `Missing session cookie` |
| 只传了错误格式 Bearer | `401` | `Missing bearer token` 或 token 校验错误 |
| JWT 过期 | `401` | `Token has expired` |
| JWT 签名错误 | `401` | `Invalid token signature` |
| 用户不在白名单 | `401`（HTTP）或回调失败重定向 | `GitHub user '<name>' is not whitelisted` |
| OAuth 缺少 `code` | 回调失败重定向 | `error=missing_code` |
| OAuth state 无效 | 回调失败重定向 | `error=invalid_state` |
| WebSocket 认证失败 | 握手关闭 | close code `1008` |

## 相关文档

- [REST API 总览](rest.zh-CN.md)
- [WebSocket 协议](websocket.zh-CN.md)
- [事件字典](events.zh-CN.md)
- [认证模块长期设计](../modules/auth/design.zh-CN.md)
