# Authentication System Usage Guide

This document describes the usage of the Phase 11 authentication system. The current system supports two modes:

- **Local Mode**: Authentication disabled, continues to use the default user `default`.
- **Deployment Mode**: GitHub OAuth enabled, only whitelisted GitHub users can access the application.

The authentication toggle is controlled in the backend configuration. The frontend automatically reads the backend authentication status and decides whether to require login.

## Quick Conclusion

Keep the default configuration for local development:

```yaml
# atri/config/auth.yaml
enabled: false
```

Enable authentication before public deployment:

```yaml
# atri/config/auth.yaml
enabled: true
```

After enabling authentication, accessing the frontend `/` will automatically redirect to `/login`. Users must complete GitHub login before using the home page, settings page, chat, WebSocket, and other features.

## Cloud Deployment

### 1. Backend atri

#### 1.1. atri/.env

```env
JWT_SECRET_KEY=Randomly generated secret key
GITHUB_CLIENT_ID=GitHub OAuth App Client ID
GITHUB_CLIENT_SECRET=GitHub OAuth App Client Secret
```

#### 1.2. atri/config/auth.yaml

```yaml
enabled: true

github:
  callback_url: https://your-backend-domain/api/auth/callback

frontend:
  callback_url: https://your-frontend-domain/auth/callback
  login_url: https://your-frontend-domain/login

whitelist:
  users:
    - your-github-username
```

If frontend and backend share the same domain, e.g., https://robot.example.com, it can be:

```yaml
github:
  callback_url: https://robot.example.com/api/auth/callback

frontend:
  callback_url: https://robot.example.com/auth/callback
  login_url: https://robot.example.com/login
```

#### 1.3. GitHub OAuth App Configuration

The Authorization callback URL in GitHub backend must exactly match the backend configuration:

`https://your-backend-domain/api/auth/callback`, not the frontend `/auth/callback`.

#### 1.4. Backend CORS

If frontend and backend are on different domains, you need to allow the frontend domain in the backend CORS configuration, e.g.:

```yaml
allow_origins:
  - https://your-frontend-domain
```

### 2. Frontend atrio-webui

Set frontend environment variables before building:

```env
VITE_API_BASE_URL=https://your-backend-domain
VITE_WS_URL=wss://your-backend-domain/ws
```

Notes:

- VITE_API_BASE_URL uses https://
- VITE_WS_URL uses wss://
- Vite environment variables are written at build time; you need to re-run `npm run build` after changes

### 3. Server/Reverse Proxy

You need to ensure:

```text
/api  -> Backend FastAPI
/ws   -> Backend WebSocket
/     -> Frontend static files
```

And `/ws` must support WebSocket upgrade.

### 4. Minimal Deployment Checklist

1. auth.yaml enabled: true
2. JWT_SECRET_KEY generated and written to atri/.env
3. GitHub Client ID / Secret written to atri/.env
4. GitHub OAuth callback URL = backend /api/auth/callback
5. whitelist.users contains your GitHub username
6. Frontend VITE_API_BASE_URL / VITE_WS_URL changed to server address
7. Using HTTPS / WSS
8. Re-run npm run build after changing frontend env

If only for local/intranet personal use, you can keep:

```yaml
enabled: false
```

This way, GitHub OAuth is not needed.

## Related Files

| Repository | File | Purpose |
| --- | --- | --- |
| `atri` | `config/auth.yaml` | Authentication master configuration |
| `atri` | `.env` | Stores JWT and GitHub OAuth secrets |
| `atri` | `.env.example` | Environment variable example, no real secrets |
| `atri-webui` | `.env.development` | Frontend API and WebSocket addresses |
| `atri-webui` | `src/pages/login.vue` | Login page |
| `atri-webui` | `src/pages/auth-callback.vue` | OAuth callback page |
| `atri-webui` | `src/pages/settings/account.vue` | Account settings page |

## Local Mode

Local mode is suitable for personal development and standalone deployment.

1. Confirm backend authentication is disabled:

```yaml
# atri/config/auth.yaml
enabled: false
```

2. Start the backend and frontend.

3. Open the frontend page.

At this point, there will be no redirect to the login page. The backend will use `default` as the user ID and maintain the original single-user chat data path.

## Deployment Mode

Deployment mode is suitable for public servers or multi-user accessible environments.

### 1. Create GitHub OAuth App

Create an OAuth App on GitHub:

1. Open GitHub **Settings**.
2. Go to **Developer settings**.
3. Go to **OAuth Apps**.
4. Create a new OAuth App.

Local development example:

| Field | Value |
| --- | --- |
| Homepage URL | `http://localhost:5173` |
| Authorization callback URL | `http://localhost:8430/api/auth/callback` |

Production environment example:

| Field | Value |
| --- | --- |
| Homepage URL | `https://YOUR_FRONTEND_DOMAIN` |
| Authorization callback URL | `https://YOUR_BACKEND_DOMAIN/api/auth/callback` |

Note: The GitHub OAuth App callback URL is the **backend** address. After the backend receives the GitHub authorization result, it redirects to the frontend `/auth/callback`.

### 2. Configure Backend Environment Variables

Configure in `atri/.env`:

```env
JWT_SECRET_KEY=REPLACE_WITH_A_LONG_RANDOM_SECRET
GITHUB_CLIENT_ID=YOUR_GITHUB_CLIENT_ID
GITHUB_CLIENT_SECRET=YOUR_GITHUB_CLIENT_SECRET
```

Requirements:

- `JWT_SECRET_KEY` must be a long random string.
> You can use Python to generate it: scripts\generate_jwt_secret.py
- Do not commit the real `.env` to Git.
- `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` come from the GitHub OAuth App.

### 3. Configure Backend Authentication Toggle

Edit `atri/config/auth.yaml`:

```yaml
enabled: true

jwt:
  secret_key: ${JWT_SECRET_KEY}
  algorithm: HS256
  expire_days: 7

github:
  client_id: ${GITHUB_CLIENT_ID}
  client_secret: ${GITHUB_CLIENT_SECRET}
  callback_url: http://localhost:8430/api/auth/callback
  scope: read:user

frontend:
  callback_url: http://localhost:5173/auth/callback
  login_url: http://localhost:5173/login

whitelist:
  users:
    - YOUR_GITHUB_USERNAME
```

For production, change the URLs to actual domains:

```yaml
github:
  callback_url: https://YOUR_BACKEND_DOMAIN/api/auth/callback

frontend:
  callback_url: https://YOUR_FRONTEND_DOMAIN/auth/callback
  login_url: https://YOUR_FRONTEND_DOMAIN/login
```

JWT lifecycle is fixed at `expire_days: 7`, i.e., 7 days.

### 4. Configure Whitelist

Only GitHub usernames in `whitelist.users` can log in.

```yaml
whitelist:
  users:
    - JuyaoHuang
    - another-user
```

Whitelist matching is case-insensitive. It is recommended to use the `login` username displayed on the GitHub profile.

### 5. Configure Frontend Address

For local development, use `atri-webui/.env.development`:

```env
VITE_API_BASE_URL=http://localhost:8430
VITE_WS_URL=ws://localhost:8430/ws
```

For production, configure according to the deployment domain:

```env
VITE_API_BASE_URL=https://YOUR_BACKEND_DOMAIN
VITE_WS_URL=wss://YOUR_BACKEND_DOMAIN/ws
```

If the frontend and backend use same-domain reverse proxy, you can also use a relative API proxy approach, but ensure `/api` and `/ws` are both forwarded to the backend.

## Login Flow

After enabling authentication, the flow is as follows:

1. User visits `/`.
2. Frontend route guard calls `/api/auth/status`.
3. If authentication is enabled and there is no valid token, frontend redirects to `/login?redirect=/`.
4. User clicks **Continue with GitHub**.
5. Frontend calls `/api/auth/login` to get the GitHub authorization URL.
6. User authorizes on GitHub.
7. GitHub calls back to backend `/api/auth/callback`.
8. Backend reads GitHub user info and checks the whitelist.
9. After whitelist passes, backend generates JWT.
10. Backend redirects to frontend `/auth/callback?token=...`.
11. Frontend saves token to LocalStorage and returns to the original target page.

## Frontend Behavior

After enabling authentication:

- `/login` and `/auth/callback` are public pages.
- `/`, `/settings`, and other business pages require login.
- Logged-in users visiting `/login` will return to the target page.
- When API returns `401`, frontend clears token and redirects to login page.
- Login page will display "Login has expired. Please sign in again."
- WebSocket connection will automatically append `?token=JWT_TOKEN`.

When authentication is disabled:

- No forced redirect to login page.
- Frontend continues to use local user profile.
- Backend uses `default` user.

## Account Settings Page

Account settings page path:

```text
/settings/account
```

This page displays:

- Current authentication mode.
- GitHub username and avatar.
- Login time.
- Logout button.
- Local display name and local avatar filename.

Local display name and avatar are still used for local mode and user display in chat messages.

## Backend Authentication Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/auth/status` | Returns whether authentication is enabled |
| `GET` | `/api/auth/login` | Returns GitHub OAuth authorization URL |
| `GET` | `/api/auth/callback` | GitHub OAuth callback |
| `GET` | `/api/auth/me` | Returns current user |
| `POST` | `/api/auth/logout` | Used for frontend logout, server returns success |

After enabling authentication, all backend HTTP routes except authentication endpoints, static resources, health checks, and documentation endpoints require the `Authorization` header:

```http
Authorization: Bearer YOUR_JWT_TOKEN
```

WebSocket uses query parameter:

```text
wss://YOUR_BACKEND_DOMAIN/ws?token=YOUR_JWT_TOKEN
```

## Verification Methods

Backend verification:

```bash
cd atri
uv run pytest tests/auth tests/routes/test_auth.py tests/routes/test_chats.py tests/routes/test_chat_ws.py tests/storage/test_json_storage.py -q
uv run ruff check src tests/auth tests/routes/test_auth.py tests/routes/test_chat_ws.py tests/storage/test_json_storage.py
```

Frontend verification:

```bash
cd atrio-webui
npm run type-check
npm run build
npm run lint
```

Manual acceptance:

1. Set `enabled: true`.
2. Fill in OAuth and JWT configuration in `.env`.
3. Add your GitHub username to the whitelist.
4. Start the backend and frontend.
5. Open frontend `/`.
6. Confirm automatic redirect to `/login`.
7. Click GitHub login.
8. After successful login, confirm return to `/`.
9. Open `/settings/account`, confirm GitHub user info is displayed.
10. Click logout, confirm return to login page.

## Common Issues

### Backend fails to start after enabling authentication

Possible causes:

- `JWT_SECRET_KEY` not set.
- `GITHUB_CLIENT_ID` not set.
- `GITHUB_CLIENT_SECRET` not set.
- `auth.yaml` still has `${...}` placeholders.

Resolution:

1. Check `atri/.env`.
2. Confirm the backend loaded `.env` when starting.
3. Confirm `config/auth.yaml` references the correct variables.

### Login fails after GitHub callback

Possible causes:

- GitHub OAuth App callback URL configured incorrectly.
- `github.callback_url` does not match the GitHub OAuth App.
- `frontend.callback_url` is not the actual frontend domain.
- GitHub username not in the whitelist.

Resolution:

1. GitHub OAuth App callback uses backend `/api/auth/callback`.
2. `frontend.callback_url` uses frontend `/auth/callback`.
3. Check `whitelist.users`.

### Accessing home page keeps redirecting to login page

Possible causes:

- Token does not exist.
- Token has expired.
- Token's corresponding user is not in the whitelist.
- Old token saved in browser LocalStorage.

Resolution:

1. Log in again.
2. Clear `atri_auth_token` in browser LocalStorage.
3. Confirm whitelist configuration.

### WebSocket connection is closed

After enabling authentication, if WebSocket is missing a token or the token is invalid, the backend will reject the connection.

Check:

- Whether the frontend is logged in.
- Whether `VITE_WS_URL` points to backend `/ws`.
- Whether the WebSocket URL in browser developer tools has the `token` query parameter.

### Don't want to log in locally

Change the backend configuration back to:

```yaml
enabled: false
```

After restarting the backend, the frontend will restore local login-free behavior.

## Security Notes

- Production must use HTTPS and WSS.
- Do not commit the real `.env`.
- If `JWT_SECRET_KEY` is leaked, you need to replace the key and have all users log in again.
- The shorter the whitelist, the more secure.
- Authentication must be enabled for public deployment.
