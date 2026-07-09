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

This document records authentication REST APIs, HTTP authorization rules, Cookie session behavior, and WebSocket authorization boundaries. User-facing configuration lives in [Authentication System Usage Guide](../../configs/EN/authentication-system-guide.md).

Current conclusions:

- Browser clients use the `HttpOnly` session Cookie `atri_session`.
- HTTP REST routes also accept `Authorization: Bearer <JWT>` for non-browser clients.
- WebSocket `/ws` reads Cookie only. Query-string tokens are not the supported path.
- OAuth callback success is represented by `success=1`; the frontend then calls `/api/auth/me`.
- `POST /api/auth/logout` clears the Cookie and does not require a valid login first.

## REST API

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/api/auth/status` | No | Returns whether authentication is enabled. |
| `GET` | `/api/auth/login` | No | Returns the GitHub OAuth authorization URL and sets the OAuth state Cookie. |
| `GET` | `/api/auth/callback` | No | GitHub OAuth callback endpoint. On success it sets `atri_session` and redirects to the frontend callback page. |
| `GET` | `/api/auth/me` | Local mode: no; deployment mode: yes | Returns the current user. |
| `POST` | `/api/auth/logout` | No | Clears `atri_session` and returns success. |

## HTTP Authorization

When authentication is enabled, business HTTP routes resolve credentials in this order:

1. Validate the `atri_session` Cookie if present.
2. Fall back to `Authorization: Bearer <JWT>` if no Cookie is present.
3. Return `401` when neither credential is valid.

Authentication endpoints, static assets, health checks, and documentation endpoints remain public.

When authentication is disabled, the backend uses the default user `default`.

## WebSocket Authorization

The supported business WebSocket URL is:

```text
wss://YOUR_BACKEND_DOMAIN/ws
```

When authentication is enabled, the backend reads `atri_session` from the WebSocket handshake Cookie. It rejects missing, expired, invalid, or unauthorized sessions before accepting the connection.

When authentication is disabled, WebSocket connections do not require credentials and still use the `default` user.

Do not append `token` or `access_token` to the WebSocket URL. Browser WebSocket authorization is Cookie-based in the current implementation.

## OAuth Callback

The backend redirects the browser to the configured frontend callback URL with one of these results:

| Result | Meaning |
| --- | --- |
| `success=1` | Login succeeded. The session Cookie has already been set. |
| `auth=disabled` | Authentication is disabled. The frontend enters local mode. |
| `error=...` | Login failed. Optional `detail` may include more context. |

The frontend callback page does not read a JWT from the URL. It treats only `success=1` as a successful login and then calls `/api/auth/me`.

## Frontend State Handling

The frontend should:

- call `/api/auth/status` at startup to determine auth mode;
- use `withCredentials` for browser HTTP requests;
- clear auth state and redirect to login when a business API returns `401`;
- redirect to the original target after login;
- call `/api/auth/logout` on logout to clear the session Cookie.

## Error Semantics

| Scenario | Suggested response |
| --- | --- |
| Missing session Cookie on HTTP | `401 Unauthorized` |
| Expired or invalid JWT | `401 Unauthorized` |
| GitHub user not whitelisted | `401 Unauthorized` or failed OAuth redirect |
| Invalid OAuth callback parameters | Failed OAuth redirect |
| WebSocket authentication failure | close code `1008` |

## Related Documents

- [Authentication Module Design](../modules/auth/design.en-US.md)
- [Authentication System Usage Guide](../../configs/EN/authentication-system-guide.md)
