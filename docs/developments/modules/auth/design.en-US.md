---
status: active
owner: auth
created: 2026-07-09
updated: 2026-07-09
source: docs/configs/EN/authentication-system-guide.md
related_code:
  - src/auth/
  - src/middleware/
  - src/routes/auth.py
  - frontend/src/pages/login.vue
  - frontend/src/pages/auth-callback.vue
  - frontend/src/pages/settings/account.vue
---

# Authentication Module Design

This document captures the development-side design of the authentication system. Configuration and deployment steps remain in [Authentication System Usage Guide](../../../configs/EN/authentication-system-guide.md).

## Module Role

The authentication module supports two runtime modes:

| Mode | Behavior | Use case |
| --- | --- | --- |
| Local mode | `enabled: false`; backend uses the default user `default` | Local development, single-machine use, personal intranet deployment |
| Deployment mode | `enabled: true`; GitHub OAuth + JWT + whitelist | Public deployment, multi-user access, user isolation |

The authentication module is responsible for:

- reporting whether authentication is enabled;
- starting the GitHub OAuth login flow;
- checking whether the GitHub user is allowed by `whitelist.users`;
- issuing and validating JWT tokens;
- establishing user identity for HTTP routes and WebSocket connections.

It is not responsible for:

- creating the GitHub OAuth App;
- storing GitHub passwords or long-lived GitHub tokens;
- implementing a complex RBAC permission model.

## Login Flow

Deployment mode uses this flow:

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
  -> frontend redirects back to the original target
```

JWT is still the server-side session payload, but the browser path does not expose it to frontend JavaScript. The frontend relies on the `atri_session` Cookie; the URL does not carry `token` or `access_token`.

## Frontend Behavior

When authentication is enabled:

- `/login` and `/auth/callback` are public pages.
- `/`, `/settings`, and business pages require login.
- HTTP APIs use `withCredentials` so the browser sends `atri_session`.
- When an API returns `401`, the frontend clears auth state and redirects to login.
- WebSocket connections use same-site Cookie authorization. The URL does not append a token.

When authentication is disabled:

- The frontend does not force login.
- The backend uses the `default` user.
- Local display name and avatar still affect chat presentation.

## User Identity Boundary

JWT user identity is used for:

- HTTP API authorization;
- WebSocket authorization;
- chat data isolation;
- future memory and storage isolation.

In local mode, all reads and writes use the `default` user space. In deployment mode, storage and memory code should use the authenticated GitHub user identity as the isolation key.

HTTP routes also accept `Authorization: Bearer <JWT>` for scripts, tests, or non-browser clients. If a browser request carries both Cookie and Bearer, the backend prefers the Cookie. WebSocket currently reads Cookie only.

## Security Constraints

- Production deployments must use HTTPS and WSS.
- `.env` must not be committed.
- Rotate `JWT_SECRET_KEY` if it leaks.
- The GitHub OAuth callback URL must point to backend `/api/auth/callback`.
- The frontend callback page treats only `success=1` as login success and then calls `/api/auth/me`.
- Do not place JWT values in URLs, LocalStorage, or ordinary frontend state.
- Keep the whitelist as short as practical.
- Public deployments must enable authentication.

## Related Documents

- [Authentication System Usage Guide](../../../configs/EN/authentication-system-guide.md)
- [Authentication API and Authorization Protocol](../../api/auth.en-US.md)
