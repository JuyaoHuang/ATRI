---
status: active
owner: auth
created: 2026-07-09
updated: 2026-07-09
source: docs/configs/EN/authentication-system-guide.md
related_code:
  - src/routes/auth.py
  - src/middleware/
  - frontend/src/pages/login.vue
  - frontend/src/pages/auth-callback.vue
---

# Authentication API and Authorization Protocol

This document records authentication REST APIs, HTTP authorization rules, and WebSocket token conventions. User-facing configuration lives in [Authentication System Usage Guide](../../configs/EN/authentication-system-guide.md).

## REST API

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/api/auth/status` | No | Returns whether authentication is enabled. |
| `GET` | `/api/auth/login` | No | Returns the GitHub OAuth authorization URL. |
| `GET` | `/api/auth/callback` | No | GitHub OAuth callback endpoint. |
| `GET` | `/api/auth/me` | Yes | Returns the current user. |
| `POST` | `/api/auth/logout` | Yes | Frontend logout endpoint; server returns success. |

## HTTP Authorization

When authentication is enabled, business HTTP routes require:

```http
Authorization: Bearer YOUR_JWT_TOKEN
```

Authentication endpoints, static assets, health checks, and documentation endpoints remain public.

When authentication is disabled, the backend uses the default user `default`.

## WebSocket Authorization

When authentication is enabled, the business WebSocket passes the token as a query parameter:

```text
wss://YOUR_BACKEND_DOMAIN/ws?token=YOUR_JWT_TOKEN
```

The backend should reject connections with missing tokens, invalid tokens, or users outside the whitelist.

When authentication is disabled, WebSocket connections do not require a token and still use the `default` user.

## Frontend State Handling

The frontend should:

- call `/api/auth/status` at startup to determine auth mode;
- clear the local token when a business API returns `401`;
- redirect to the original target after login;
- clear the token on logout.

## Error Semantics

| Scenario | Suggested response |
| --- | --- |
| Missing token | `401 Unauthorized` |
| Expired or invalid token | `401 Unauthorized` |
| GitHub user not whitelisted | `403 Forbidden` |
| Invalid OAuth callback parameters | `400 Bad Request` |

## Related Documents

- [Authentication Module Design](../modules/auth/design.en-US.md)
- [Authentication System Usage Guide](../../configs/EN/authentication-system-guide.md)
