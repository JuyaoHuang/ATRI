---
status: active
owner: auth
created: 2026-07-09
updated: 2026-07-09
source: docs/configs/CN/认证系统使用指南.md
related_code:
  - src/routes/auth.py
  - src/middleware/
  - frontend/src/pages/login.vue
  - frontend/src/pages/auth-callback.vue
---

# 认证 API 与鉴权协议

本文记录认证相关 REST API、HTTP 鉴权规则和 WebSocket token 约定。用户侧配置见 [认证系统使用指南](../../configs/CN/认证系统使用指南.md)。

## REST API

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/auth/status` | 否 | 返回认证是否启用。 |
| `GET` | `/api/auth/login` | 否 | 返回 GitHub OAuth 授权地址。 |
| `GET` | `/api/auth/callback` | 否 | GitHub OAuth 回调入口。 |
| `GET` | `/api/auth/me` | 是 | 返回当前用户。 |
| `POST` | `/api/auth/logout` | 是 | 前端登出用，服务端返回成功。 |

## HTTP 鉴权

认证开启后，除认证接口、静态资源、健康检查和文档接口外，业务 HTTP 路由都需要：

```http
Authorization: Bearer YOUR_JWT_TOKEN
```

认证关闭时，后端使用默认用户 `default`。

## WebSocket 鉴权

认证开启后，业务 WebSocket 使用查询参数传 token：

```text
wss://YOUR_BACKEND_DOMAIN/ws?token=YOUR_JWT_TOKEN
```

缺少 token、token 无效或用户不在白名单时，后端应拒绝连接。

认证关闭时，WebSocket 不要求 token，后端仍使用 `default` 用户。

## 前端状态处理

前端应遵守：

- 启动时调用 `/api/auth/status` 判断认证模式。
- 业务 API 返回 `401` 后清除本地 token。
- 登录成功后进入原始目标页面。
- 登出后清除 token，并回到登录页或本地模式页面。

## 错误语义

| 场景 | 建议响应 |
| --- | --- |
| 未提供 token | `401 Unauthorized` |
| token 过期或签名无效 | `401 Unauthorized` |
| GitHub 用户不在白名单 | `403 Forbidden` |
| OAuth callback 参数无效 | `400 Bad Request` |

## 相关文档

- [认证模块设计](../modules/auth/design.zh-CN.md)
- [认证系统使用指南](../../configs/CN/认证系统使用指南.md)
