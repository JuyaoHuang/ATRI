---
status: active
owner: auth
created: 2026-07-09
updated: 2026-07-09
source: docs/configs/CN/认证系统使用指南.md
related_code:
  - src/auth/
  - src/middleware/
  - src/routes/auth.py
  - frontend/src/pages/login.vue
  - frontend/src/pages/auth-callback.vue
  - frontend/src/pages/settings/account.vue
---

# 认证模块设计

本文沉淀认证系统的开发侧设计。配置和部署步骤见 [认证系统使用指南](../../../configs/CN/认证系统使用指南.md)。

## 模块定位

认证模块提供两种运行模式：

| 模式 | 行为 | 适用场景 |
| --- | --- | --- |
| 本地模式 | `enabled: false`，后端使用默认用户 `default` | 本地开发、单机使用、内网个人部署 |
| 部署模式 | `enabled: true`，GitHub OAuth + JWT + 白名单 | 公网部署、多人访问、需要用户隔离 |

认证模块负责：

- 判断当前实例是否启用认证。
- 发起 GitHub OAuth 登录。
- 校验 GitHub 用户是否在白名单中。
- 颁发和校验 JWT。
- 为 HTTP 路由和 WebSocket 建立用户身份。

认证模块不负责：

- 管理 GitHub OAuth App 的创建。
- 存储 GitHub 密码或长期访问令牌。
- 提供复杂 RBAC 权限模型。

## 登录流程

部署模式下的完整流程：

```text
user visits /
  -> frontend route guard calls GET /api/auth/status
  -> unauthenticated user redirects to /login?redirect=/
  -> user clicks Continue with GitHub
  -> frontend calls GET /api/auth/login
  -> backend returns GitHub authorization URL
  -> GitHub redirects to backend /api/auth/callback
  -> backend fetches GitHub user profile
  -> backend checks whitelist.users
  -> backend signs JWT
  -> backend writes HttpOnly Cookie atri_session
  -> backend redirects to frontend /auth/callback?success=1
  -> frontend calls GET /api/auth/me
  -> frontend redirects back to original target
```

JWT 仍是服务端会话载体，但浏览器主路径不把 JWT 暴露给前端 JavaScript。当前浏览器端依赖 `atri_session` Cookie；URL 中不会携带 `token` 或 `access_token`。

## 前端行为

认证开启时：

- `/login` 和 `/auth/callback` 是公开页面。
- `/`、`/settings` 和业务页面需要登录。
- HTTP API 使用 `withCredentials` 自动携带 `atri_session` Cookie。
- API 返回 `401` 时，前端清理认证状态并跳转登录页。
- WebSocket 连接使用同站 Cookie 鉴权，URL 不追加 token。

认证关闭时：

- 前端不强制跳转登录页。
- 后端使用 `default` 用户。
- 本地显示名和本地头像继续用于聊天展示。

## 用户身份边界

JWT 中的用户身份用于：

- HTTP API 鉴权。
- WebSocket 连接鉴权。
- 聊天数据读写隔离。
- 后续记忆和存储空间隔离。

本地模式下，所有读写都落到 `default` 用户空间。部署模式下，应以认证后的 GitHub 用户身份作为用户隔离依据。

HTTP 路由兼容 `Authorization: Bearer <JWT>`，用于脚本、测试或非浏览器调用方。浏览器请求若同时携带 Cookie 和 Bearer，后端以 Cookie 为准。WebSocket 当前只读取 Cookie。

## 安全约束

- 生产环境必须使用 HTTPS 和 WSS。
- `.env` 不得提交到 Git。
- `JWT_SECRET_KEY` 泄露后必须轮换。
- GitHub OAuth callback URL 必须指向后端 `/api/auth/callback`。
- 前端回调页只把 `success=1` 视为登录成功，并在之后调用 `/api/auth/me`。
- 不要把 JWT 写入 URL、LocalStorage 或普通前端状态。
- 白名单应尽量短。
- 公网部署必须启用认证。

## 相关文档

- [认证系统使用指南](../../../configs/CN/认证系统使用指南.md)
- [认证 API 与鉴权协议](../../api/auth.zh-CN.md)
