# Backend API Documentation

> Project: emotion-robot / atri
> Backend address: `http://localhost:8430`
> Document status: Updated per Phase 11 authentication system and current backend routes
> Last updated: 2026-04-26

## API Overview

| Category | Method | Path | Description | Auth |
|---|---:|---|---|---|
| Health Check | GET | `/health` | Service health status | No |
| Auth | GET | `/api/auth/status` | Query auth toggle | No |
| Auth | GET | `/api/auth/login` | Get GitHub OAuth login URL | No |
| Auth | GET | `/api/auth/callback` | GitHub OAuth callback | No |
| Auth | GET | `/api/auth/me` | Get current user | Required when auth is enabled |
| Auth | POST | `/api/auth/logout` | Logout placeholder endpoint | No |
| Characters | GET | `/api/characters` | Character list | Yes |
| Characters | POST | `/api/characters` | Create character | Yes |
| Characters | GET | `/api/characters/{character_id}` | Character details | Yes |
| Characters | PUT | `/api/characters/{character_id}` | Update character | Yes |
| Characters | DELETE | `/api/characters/{character_id}` | Delete character | Yes |
| Characters | POST | `/api/characters/{character_id}/avatar` | Upload character avatar | Yes |
| Chats | GET | `/api/chats` | Chat list | Yes |
| Chats | POST | `/api/chats` | Create chat | Yes |
| Chats | GET | `/api/chats/{chat_id}` | Chat details and messages | Yes |
| Chats | POST | `/api/chats/{chat_id}/update` | Update chat title | Yes |
| Chats | POST | `/api/chats/{chat_id}/delete` | Delete chat | Yes |
| WebSocket | WS | `/ws` | Real-time streaming conversation | Yes |
| ASR | GET | `/api/asr/providers` | ASR provider list | Yes |
| ASR | GET | `/api/asr/config` | ASR configuration | Yes |
| ASR | PUT | `/api/asr/config` | Update ASR configuration | Yes |
| ASR | POST | `/api/asr/switch` | Switch ASR provider | Yes |
| ASR | GET | `/api/asr/health` | ASR health status | Yes |
| ASR | POST | `/api/asr/transcribe` | Audio to text | Yes |
| TTS | GET | `/api/tts/providers` | TTS provider list | Yes |
| TTS | GET | `/api/tts/config` | TTS configuration | Yes |
| TTS | PUT | `/api/tts/config` | Update TTS configuration | Yes |
| TTS | POST | `/api/tts/switch` | Switch TTS provider | Yes |
| TTS | GET | `/api/tts/health` | TTS health status | Yes |
| TTS | GET | `/api/tts/voices` | Get voice list | Yes |
| TTS | POST | `/api/tts/synthesize` | Text to speech | Yes |
| Live2D | GET | `/api/live2d/models` | Live2D model list | Yes |
| Live2D | POST | `/api/live2d/models` | Upload Live2D ZIP model | Yes |
| Live2D | GET | `/api/live2d/models/{model_id}/expressions` | Expression list | Yes |
| Live2D | PUT | `/api/live2d/models/{model_id}` | Update model metadata | Yes |
| Live2D | DELETE | `/api/live2d/models/{model_id}` | Delete model | Yes |
| Static Assets | GET | `/api/assets/avatars/{filename}` | Character avatar file | No |
| Static Assets | GET | `/api/assets/live2d/{model_id}/{path}` | Live2D model assets | No |
| Static Assets | GET | `/static/avatars/{filename}` | Legacy avatar path | No |

## Authentication Rules

Authentication is controlled by the backend `atri/config/auth.yaml`.

```yaml
enabled: true
jwt:
  secret_key: ${JWT_SECRET_KEY}
  algorithm: HS256
  expire_days: 7
```

When `enabled: false`, the backend runs in local single-user mode. All business data belongs to the `default` user, and clients do not need to pass a token.

When `enabled: true`, except for public paths, all HTTP business endpoints must carry a JWT:

```http
Authorization: Bearer <JWT_TOKEN>
```

WebSocket cannot use HTTP headers to pass a token. Use a query parameter when connecting:

```text
ws://localhost:8430/ws?token=<JWT_TOKEN>
```

Public paths include:

| Path | Description |
|---|---|
| `/health` | Health check |
| `/openapi.json` | OpenAPI JSON |
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/api/auth/*` | Authentication flow |
| `/api/assets/*` | Backend static assets |
| `/static/avatars/*` | Legacy avatar static assets |

### Error Responses

Authentication failure returns `401 Unauthorized`:

```json
{
  "detail": "Missing bearer token"
}
```

Common causes:

| Scenario | Handling |
|---|---|
| Missing `Authorization` | Save the token after login and include it in request headers |
| Token expired | Re-login |
| `JWT_SECRET_KEY` changed | All old tokens are invalidated; re-login required |
| User not in whitelist | Add the GitHub username to `whitelist.users` in `auth.yaml` |

## Health Check

### `GET /health`

Check whether the backend service is running.

```bash
curl http://localhost:8430/health
```

Response:

```json
{
  "status": "ok"
}
```

## Auth Endpoints

### `GET /api/auth/status`

Query whether authentication is enabled on the backend.

Response:

```json
{
  "enabled": true
}
```

### `GET /api/auth/login`

Get the GitHub OAuth authorization URL. When authentication is disabled, `authorization_url` is `null`.

Query Parameters:

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `state` | string | No | OAuth state; the frontend can use it for CSRF protection or redirect state |

Response:

```json
{
  "enabled": true,
  "authorization_url": "https://github.com/login/oauth/authorize?client_id=..."
}
```

### `GET /api/auth/callback`

GitHub OAuth callback URL. This endpoint is called by GitHub via redirect and should not be called directly by the frontend.

Query Parameters:

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `code` | string | On success | GitHub OAuth authorization code |
| `error` | string | On failure | Error returned by GitHub |

On success, the backend redirects to `frontend.callback_url` from `auth.yaml` with:

```text
?token=<JWT_TOKEN>&username=<GITHUB_USERNAME>&avatar_url=<URL>
```

On failure, it redirects to the same frontend callback page with:

```text
?error=unauthorized&detail=<reason>
```

### `GET /api/auth/me`

Get the currently logged-in user. `Authorization` header is required when authentication is enabled.

Response:

```json
{
  "username": "JuyaoHuang",
  "avatar_url": "https://avatars.githubusercontent.com/u/...",
  "name": "User Name",
  "auth_enabled": true
}
```

Response when authentication is disabled:

```json
{
  "username": "default",
  "avatar_url": null,
  "name": null,
  "auth_enabled": false
}
```

### `POST /api/auth/logout`

Logout placeholder endpoint. JWT is a stateless token; the backend does not currently maintain server-side sessions. The frontend needs to delete the local token.

Response:

```json
{
  "success": true
}
```

## Character Endpoints

### `GET /api/characters`

Get the character list without the full `system_prompt`.

Response:

```json
[
  {
    "character_id": "atri",
    "name": "Atri",
    "avatar": "atri.png",
    "avatar_url": "http://localhost:8430/api/assets/avatars/atri.png",
    "greeting": "Hello",
    "description": "Default character",
    "created_at": null,
    "updated_at": null,
    "is_system": true
  }
]
```

### `POST /api/characters`

Create a custom character.

Request:

```json
{
  "character_id": "rainy-atri",
  "name": "Rainy Atri",
  "greeting": "Want to chat today too?",
  "description": "A quieter version of the character",
  "system_prompt": "You are a..."
}
```

Field constraints:

| Field | Type | Required | Constraints |
|---|---|---:|---|
| `character_id` | string | No | Max 64 characters; auto-generated by backend if omitted |
| `name` | string | Yes | 1-50 characters |
| `greeting` | string | No | Max 500 characters |
| `description` | string | No | Max 200 characters |
| `system_prompt` | string | Yes | 1-4000 characters |

Returns `201 Created` and the complete character object on success.

### `GET /api/characters/{character_id}`

Get character details, including the full `system_prompt`.

Response:

```json
{
  "character_id": "atri",
  "name": "Atri",
  "avatar": "atri.png",
  "avatar_url": "http://localhost:8430/api/assets/avatars/atri.png",
  "greeting": "Hello",
  "description": "Default character",
  "created_at": null,
  "updated_at": null,
  "is_system": true,
  "system_prompt": "You are..."
}
```

### `PUT /api/characters/{character_id}`

Update a character. All fields are optional.

Request:

```json
{
  "name": "New Name",
  "greeting": "New greeting",
  "description": "New description",
  "system_prompt": "New character settings"
}
```

### `DELETE /api/characters/{character_id}`

Delete a custom character. System characters cannot be deleted.

Returns `204 No Content` on success.

### `POST /api/characters/{character_id}/avatar`

Upload or replace a character avatar.

Request format: `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---:|---|
| `avatar` | file | Yes | PNG / JPG / WEBP; size limit enforced by the backend storage layer |

Response:

```json
{
  "character_id": "rainy-atri",
  "avatar": "rainy-atri-a1b2c3d4.png",
  "avatar_url": "http://localhost:8430/api/assets/avatars/rainy-atri-a1b2c3d4.png"
}
```

## Chat Endpoints

Chat data is isolated per current user. When authentication is disabled, all chats belong to `default`.

### `GET /api/chats`

Get the current user's chat list, sorted by update time in descending order.

Query Parameters:

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `character_id` | string | No | Filter by character |

Response:

```json
[
  {
    "id": "20260421_a3f8b2c1",
    "title": "Weather chat",
    "character_id": "atri",
    "created_at": "2026-04-21T10:30:00Z",
    "updated_at": "2026-04-21T11:45:00Z",
    "message_count": 12
  }
]
```

### `POST /api/chats`

Create a new chat.

Request:

```json
{
  "character_id": "atri",
  "first_message": "Let's chat about deploying the auth system today",
  "defer_title": false
}
```

Fields:

| Field | Type | Required | Description |
|---|---|---:|---|
| `character_id` | string | Yes | Character ID |
| `first_message` | string | Yes | First user message, used to generate the title |
| `defer_title` | boolean | No | Default `false`; when `true`, returns a temporary title first and backfills asynchronously in the background |

Response:

```json
{
  "id": "20260421_b4c9d3e2",
  "title": "Deploying the auth system",
  "character_id": "atri",
  "created_at": "2026-04-21T12:00:00Z",
  "updated_at": "2026-04-21T12:00:00Z"
}
```

### `GET /api/chats/{chat_id}`

Get chat details and message history.

Query Parameters:

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `limit` | int | No | Load all | Number of messages to return; range `1-5000` |
| `offset` | int | No | `0` | Message offset |

Response:

```json
{
  "metadata": {
    "id": "20260421_a3f8b2c1",
    "title": "Weather chat",
    "character_id": "atri",
    "created_at": "2026-04-21T10:30:00Z",
    "updated_at": "2026-04-21T11:45:00Z",
    "message_count": 2
  },
  "messages": [
    {
      "role": "human",
      "content": "Hello",
      "timestamp": "2026-04-21T10:30:05Z",
      "name": "JuyaoHuang"
    },
    {
      "role": "ai",
      "content": "Hello, what would you like to chat about?",
      "timestamp": "2026-04-21T10:30:08Z",
      "name": "atri"
    }
  ]
}
```

### `POST /api/chats/{chat_id}/update`

Update chat title.

Request:

```json
{
  "title": "New chat title"
}
```

Returns the updated chat metadata on success.

### `POST /api/chats/{chat_id}/delete`

Delete a chat and its messages.

Returns `204 No Content` on success.

## WebSocket Real-time Conversation

### Connection URL

Authentication disabled:

```text
ws://localhost:8430/ws
```

Authentication enabled:

```text
ws://localhost:8430/ws?token=<JWT_TOKEN>
```

When authentication is enabled but the token is missing or invalid, the connection will be closed with close code `1008`. Server logs may show `403 Forbidden` or `WebSocket authentication failed`.

### Client Sends

Send a text message:

```json
{
  "type": "input:text",
  "data": {
    "text": "Hello",
    "chat_id": "20260421_a3f8b2c1",
    "character_id": "atri",
    "client_context": {
      "live2d_expression": "smile"
    }
  }
}
```

Fields:

| Field | Type | Required | Description |
|---|---|---:|---|
| `type` | string | Yes | Fixed to `input:text` |
| `data.text` | string | Yes | User input |
| `data.chat_id` | string | Yes | Chat ID |
| `data.character_id` | string | Yes | Character ID |
| `data.client_context` | object | No | Frontend runtime context; passed to the Agent |

Heartbeat:

```json
{
  "type": "ping"
}
```

### Server Returns

Streaming chunk:

```json
{
  "type": "output:chat:chunk",
  "data": {
    "chunk": "Hello",
    "chat_id": "20260421_a3f8b2c1",
    "character_id": "atri"
  }
}
```

Completion event:

```json
{
  "type": "output:chat:complete",
  "data": {
    "full_reply": "Hello, what would you like to chat about?",
    "chat_id": "20260421_a3f8b2c1",
    "character_id": "atri"
  }
}
```

Error event:

```json
{
  "type": "error",
  "data": {
    "message": "Missing 'chat_id' field",
    "chat_id": "20260421_a3f8b2c1"
  }
}
```

Heartbeat response:

```json
{
  "type": "pong"
}
```

## ASR Endpoints

### `GET /api/asr/providers`

Get ASR provider status list.

Response item:

```json
{
  "name": "browser",
  "display_name": "Browser Speech Recognition",
  "provider_type": "browser",
  "description": "Browser speech recognition",
  "active": true,
  "available": true,
  "reason": null,
  "supports_backend_transcription": false,
  "supports_browser_streaming": true,
  "config": {}
}
```

### `GET /api/asr/config`

Return the current ASR configuration and provider status.

```json
{
  "config": {},
  "providers": []
}
```

### `PUT /api/asr/config`

Incrementally update ASR configuration. Request body is an OLV-compatible configuration fragment.

```json
{
  "active_provider": "browser"
}
```

Returns the updated `config` and `providers` on success.

### `POST /api/asr/switch`

Switch the current ASR provider.

```json
{
  "provider": "browser"
}
```

### `GET /api/asr/health`

Get ASR health status.

```json
{
  "active_provider": "browser",
  "active_available": true,
  "providers": []
}
```

### `POST /api/asr/transcribe`

Upload audio and transcribe to text.

Request format: `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---:|---|
| `audio` | file | Yes | Audio file |
| `provider` | string | No | Specify ASR provider |

Response:

```json
{
  "provider": "faster-whisper",
  "text": "Hello"
}
```

## TTS Endpoints

### `GET /api/tts/providers`

Get TTS provider status list.

Response item:

```json
{
  "name": "edge_tts",
  "display_name": "Edge TTS",
  "provider_type": "edge",
  "description": "Microsoft Edge TTS",
  "active": true,
  "available": true,
  "reason": null,
  "supports_streaming": false,
  "media_type": "audio/mpeg",
  "config": {}
}
```

### `GET /api/tts/config`

Return the current TTS configuration and provider status.

```json
{
  "config": {},
  "providers": []
}
```

### `PUT /api/tts/config`

Incrementally update TTS configuration. Request body is an OLV-compatible configuration fragment.

```json
{
  "active_provider": "edge_tts"
}
```

### `POST /api/tts/switch`

Switch the current TTS provider.

```json
{
  "provider": "edge_tts"
}
```

### `GET /api/tts/health`

Get TTS health status.

```json
{
  "active_provider": "edge_tts",
  "active_available": true,
  "providers": []
}
```

### `GET /api/tts/voices`

Get voice list.

Query Parameters:

| Parameter | Type | Required | Description |
|---|---|---:|---|
| `provider` | string | No | Specify TTS provider |

Response:

```json
{
  "provider": "edge_tts",
  "voices": [
    {
      "id": "zh-CN-XiaoxiaoNeural",
      "name": "Xiaoxiao",
      "language": "zh-CN",
      "gender": "Female",
      "description": null,
      "preview_url": null
    }
  ]
}
```

### `POST /api/tts/synthesize`

Text to speech. The response body is audio binary, not JSON.

Request:

```json
{
  "text": "Hello",
  "provider": "edge_tts",
  "voice_id": "zh-CN-XiaoxiaoNeural",
  "options": {}
}
```

Response Headers:

| Header | Description |
|---|---|
| `Content-Type` | Audio MIME type, e.g. `audio/mpeg` |
| `X-TTS-Provider` | The TTS provider actually used |

## Live2D Endpoints

### `GET /api/live2d/models`

Get Live2D model list.

Response item:

```json
{
  "id": "hiyori",
  "name": "Hiyori",
  "model_path": "runtime/hiyori.model3.json",
  "model_url": "http://localhost:8430/api/assets/live2d/hiyori/runtime/hiyori.model3.json",
  "thumbnail_url": null,
  "expressions": ["smile", "angry"],
  "created_at": "2026-04-21T10:30:00Z",
  "is_default": false
}
```

### `POST /api/live2d/models`

Upload and extract a Live2D ZIP model.

Request format: `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---:|---|
| `model` | file | Yes | Live2D ZIP package |
| `name` | string | No | Display name |

Returns `201 Created` and a model summary on success.

### `GET /api/live2d/models/{model_id}/expressions`

Get the expression list for a specific model.

Response:

```json
{
  "model_id": "hiyori",
  "expressions": ["smile", "angry"]
}
```

### `PUT /api/live2d/models/{model_id}`

Update Live2D model metadata.

Request:

```json
{
  "name": "New model name"
}
```

`name` length is limited to `1-120` characters.

### `DELETE /api/live2d/models/{model_id}`

Delete a Live2D model directory.

Returns `204 No Content` on success.

## Static Assets

### `GET /api/assets/avatars/{filename}`

Access backend-hosted character avatar files.

### `GET /static/avatars/{filename}`

Legacy avatar path for older frontends or data.

### `GET /api/assets/live2d/{model_id}/{path}`

Access Live2D model assets. `model_url` and `thumbnail_url` return directly accessible URLs.

## Common Error Codes

| Status Code | Meaning | Common Scenarios |
|---:|---|---|
| `200 OK` | Request succeeded | Successful queries and updates |
| `201 Created` | Creation succeeded | Creating chats, characters, Live2D models |
| `204 No Content` | Succeeded with no response body | Successful deletion |
| `400 Bad Request` | Invalid request parameters | Malformed fields, invalid uploaded files |
| `401 Unauthorized` | Unauthenticated or invalid token | Auth enabled but JWT missing |
| `404 Not Found` | Resource not found | Character, chat, or Live2D model does not exist |
| `429 Too Many Requests` | Rate limit exceeded | TTS provider rate limiting |
| `502 Bad Gateway` | Upstream service error | TTS upstream API call failed |
| `503 Service Unavailable` | Provider unavailable | Current ASR/TTS provider is unavailable |
| `500 Internal Server Error` | Internal backend error | Unexpected exception |

Error responses are typically:

```json
{
  "detail": "Chat '20260421_invalid' not found"
}
```

## Frontend Integration Notes

1. On startup, call `GET /api/auth/status` to determine whether authentication is enabled.
2. When authentication is enabled, unauthenticated users should be redirected to a login page and obtain the GitHub OAuth URL via `GET /api/auth/login`.
3. After successful login, the frontend callback page reads `token` from the URL, saves it locally, and includes `Authorization: Bearer <token>` in HTTP requests.
4. When establishing a WebSocket connection, append `?token=<token>`; otherwise the connection will be rejected when authentication is enabled.
5. Chat endpoints like `GET /api/chats` and `GET /api/chats/{chat_id}` only return data for the current user.
6. `POST /api/auth/logout` only returns a success response; the actual logout action is the frontend deleting the local token.

## Related Source Code Locations

| Content | Path |
|---|---|
| FastAPI application factory | `atri/src/app.py` |
| HTTP auth middleware | `atri/src/middleware/auth.py` |
| Auth endpoints | `atri/src/routes/auth.py` |
| WebSocket endpoint | `atri/src/routes/chat_ws.py` |
| Chat endpoints | `atri/src/routes/chats.py` |
| Character endpoints | `atri/src/routes/characters.py` |
| ASR endpoints | `atri/src/routes/asr.py` |
| TTS endpoints | `atri/src/routes/tts.py` |
| Live2D endpoints | `atri/src/routes/live2d.py` |
| Auth configuration | `atri/config/auth.yaml` |
