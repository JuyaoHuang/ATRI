# 后端 API 接口文档

> 项目: emotion-robot / atri
> 后端地址: `http://localhost:8430`
> 文档状态: 已按 Phase 11 认证系统与当前后端路由更新
> 最后更新: 2026-04-26

## 接口总览

| 分类 | 方法 | 路径 | 说明 | 认证 |
|---|---:|---|---|---|
| 健康检查 | GET | `/health` | 服务健康状态 | 否 |
| 认证 | GET | `/api/auth/status` | 查询认证开关 | 否 |
| 认证 | GET | `/api/auth/login` | 获取 GitHub OAuth 登录地址 | 否 |
| 认证 | GET | `/api/auth/callback` | GitHub OAuth 回调 | 否 |
| 认证 | GET | `/api/auth/me` | 获取当前用户 | 开启认证时需要 |
| 认证 | POST | `/api/auth/logout` | 登出占位接口 | 否 |
| 角色 | GET | `/api/characters` | 角色列表 | 是 |
| 角色 | POST | `/api/characters` | 创建角色 | 是 |
| 角色 | GET | `/api/characters/{character_id}` | 角色详情 | 是 |
| 角色 | PUT | `/api/characters/{character_id}` | 更新角色 | 是 |
| 角色 | DELETE | `/api/characters/{character_id}` | 删除角色 | 是 |
| 角色 | POST | `/api/characters/{character_id}/avatar` | 上传角色头像 | 是 |
| 聊天 | GET | `/api/chats` | 聊天列表 | 是 |
| 聊天 | POST | `/api/chats` | 创建聊天 | 是 |
| 聊天 | GET | `/api/chats/{chat_id}` | 聊天详情和消息 | 是 |
| 聊天 | POST | `/api/chats/{chat_id}/update` | 更新聊天标题 | 是 |
| 聊天 | POST | `/api/chats/{chat_id}/delete` | 删除聊天 | 是 |
| WebSocket | WS | `/ws` | 实时流式对话 | 是 |
| ASR | GET | `/api/asr/providers` | ASR 提供商列表 | 是 |
| ASR | GET | `/api/asr/config` | ASR 配置 | 是 |
| ASR | PUT | `/api/asr/config` | 更新 ASR 配置 | 是 |
| ASR | POST | `/api/asr/switch` | 切换 ASR 提供商 | 是 |
| ASR | GET | `/api/asr/health` | ASR 健康状态 | 是 |
| ASR | POST | `/api/asr/transcribe` | 音频转文字 | 是 |
| TTS | GET | `/api/tts/providers` | TTS 提供商列表 | 是 |
| TTS | GET | `/api/tts/config` | TTS 配置 | 是 |
| TTS | PUT | `/api/tts/config` | 更新 TTS 配置 | 是 |
| TTS | POST | `/api/tts/switch` | 切换 TTS 提供商 | 是 |
| TTS | GET | `/api/tts/health` | TTS 健康状态 | 是 |
| TTS | GET | `/api/tts/voices` | 获取语音列表 | 是 |
| TTS | POST | `/api/tts/synthesize` | 文本转语音 | 是 |
| Live2D | GET | `/api/live2d/models` | Live2D 模型列表 | 是 |
| Live2D | POST | `/api/live2d/models` | 上传 Live2D ZIP 模型 | 是 |
| Live2D | GET | `/api/live2d/models/{model_id}/expressions` | 表情列表 | 是 |
| Live2D | PUT | `/api/live2d/models/{model_id}` | 更新模型元数据 | 是 |
| Live2D | DELETE | `/api/live2d/models/{model_id}` | 删除模型 | 是 |
| 静态资源 | GET | `/api/assets/avatars/{filename}` | 角色头像文件 | 否 |
| 静态资源 | GET | `/api/assets/live2d/{model_id}/{path}` | Live2D 模型资源 | 否 |
| 静态资源 | GET | `/static/avatars/{filename}` | 兼容头像路径 | 否 |

## 认证规则

认证由后端 `atri/config/auth.yaml` 控制。

```yaml
enabled: true
jwt:
  secret_key: ${JWT_SECRET_KEY}
  algorithm: HS256
  expire_days: 7
```

`enabled: false` 时，后端保持本地单用户模式，所有业务数据归属 `default` 用户，客户端不需要传 token。

`enabled: true` 时，除公共路径外，HTTP 业务接口必须携带 JWT：

```http
Authorization: Bearer <JWT_TOKEN>
```

WebSocket 不能使用 HTTP Header 传 token，连接时使用查询参数：

```text
ws://localhost:8430/ws?token=<JWT_TOKEN>
```

公共路径包括：

| 路径 | 说明 |
|---|---|
| `/health` | 健康检查 |
| `/openapi.json` | OpenAPI JSON |
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/api/auth/*` | 认证流程 |
| `/api/assets/*` | 后端静态资源 |
| `/static/avatars/*` | 兼容头像静态资源 |

### 错误响应

认证失败返回 `401 Unauthorized`：

```json
{
  "detail": "Missing bearer token"
}
```

常见原因：

| 场景 | 处理 |
|---|---|
| 缺少 `Authorization` | 登录后保存 token，并在请求头传入 |
| token 过期 | 重新登录 |
| `JWT_SECRET_KEY` 变更 | 旧 token 全部失效，需要重新登录 |
| 用户不在白名单 | 在 `auth.yaml` 的 `whitelist.users` 添加 GitHub 用户名 |

## 健康检查

### `GET /health`

检查后端服务是否运行。

```bash
curl http://localhost:8430/health
```

响应：

```json
{
  "status": "ok"
}
```

## 认证接口

### `GET /api/auth/status`

查询后端是否启用认证。

响应：

```json
{
  "enabled": true
}
```

### `GET /api/auth/login`

获取 GitHub OAuth 授权地址。认证关闭时，`authorization_url` 为 `null`。

查询参数：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `state` | string | 否 | OAuth state，前端可用于防 CSRF 或回跳状态 |

响应：

```json
{
  "enabled": true,
  "authorization_url": "https://github.com/login/oauth/authorize?client_id=..."
}
```

### `GET /api/auth/callback`

GitHub OAuth 回调地址。该接口由 GitHub 重定向调用，不建议前端直接调用。

查询参数：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `code` | string | 成功时是 | GitHub OAuth 授权码 |
| `error` | string | 失败时是 | GitHub 返回的错误 |

成功后，后端会重定向到 `auth.yaml` 的 `frontend.callback_url`，并附带：

```text
?token=<JWT_TOKEN>&username=<GITHUB_USERNAME>&avatar_url=<URL>
```

失败时会重定向到同一前端回调页，并附带：

```text
?error=unauthorized&detail=<原因>
```

### `GET /api/auth/me`

获取当前登录用户。认证开启时必须带 `Authorization`。

响应：

```json
{
  "username": "JuyaoHuang",
  "avatar_url": "https://avatars.githubusercontent.com/u/...",
  "name": "User Name",
  "auth_enabled": true
}
```

认证关闭时响应：

```json
{
  "username": "default",
  "avatar_url": null,
  "name": null,
  "auth_enabled": false
}
```

### `POST /api/auth/logout`

登出占位接口。JWT 本身是无状态 token，后端当前不维护服务端会话，前端需要删除本地 token。

响应：

```json
{
  "success": true
}
```

## 角色接口

### `GET /api/characters`

获取角色列表，不包含完整 `system_prompt`。

响应：

```json
[
  {
    "character_id": "atri",
    "name": "亚托莉",
    "avatar": "atri.png",
    "avatar_url": "http://localhost:8430/api/assets/avatars/atri.png",
    "greeting": "你好",
    "description": "默认角色",
    "created_at": null,
    "updated_at": null,
    "is_system": true
  }
]
```

### `POST /api/characters`

创建自定义角色。

请求：

```json
{
  "character_id": "rainy-atri",
  "name": "雨天亚托莉",
  "greeting": "今天也要聊天吗？",
  "description": "更安静的角色版本",
  "system_prompt": "你是一个..."
}
```

字段限制：

| 字段 | 类型 | 必填 | 限制 |
|---|---|---:|---|
| `character_id` | string | 否 | 最多 64 字符；不填时后端生成 |
| `name` | string | 是 | 1-50 字符 |
| `greeting` | string | 否 | 最多 500 字符 |
| `description` | string | 否 | 最多 200 字符 |
| `system_prompt` | string | 是 | 1-4000 字符 |

成功返回 `201 Created` 和完整角色对象。

### `GET /api/characters/{character_id}`

获取角色详情，包含完整 `system_prompt`。

响应：

```json
{
  "character_id": "atri",
  "name": "亚托莉",
  "avatar": "atri.png",
  "avatar_url": "http://localhost:8430/api/assets/avatars/atri.png",
  "greeting": "你好",
  "description": "默认角色",
  "created_at": null,
  "updated_at": null,
  "is_system": true,
  "system_prompt": "你是..."
}
```

### `PUT /api/characters/{character_id}`

更新角色。所有字段都是可选字段。

请求：

```json
{
  "name": "新名称",
  "greeting": "新的问候语",
  "description": "新的简介",
  "system_prompt": "新的角色设定"
}
```

### `DELETE /api/characters/{character_id}`

删除自定义角色。系统角色不允许删除。

成功返回 `204 No Content`。

### `POST /api/characters/{character_id}/avatar`

上传或替换角色头像。

请求格式：`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `avatar` | file | 是 | PNG / JPG / WEBP，大小限制由后端存储层校验 |

响应：

```json
{
  "character_id": "rainy-atri",
  "avatar": "rainy-atri-a1b2c3d4.png",
  "avatar_url": "http://localhost:8430/api/assets/avatars/rainy-atri-a1b2c3d4.png"
}
```

## 聊天接口

聊天数据按当前用户隔离。认证关闭时，所有聊天归属 `default`。

### `GET /api/chats`

获取当前用户的聊天列表，按更新时间倒序。

查询参数：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `character_id` | string | 否 | 按角色过滤 |

响应：

```json
[
  {
    "id": "20260421_a3f8b2c1",
    "title": "天气闲聊",
    "character_id": "atri",
    "created_at": "2026-04-21T10:30:00Z",
    "updated_at": "2026-04-21T11:45:00Z",
    "message_count": 12
  }
]
```

### `POST /api/chats`

创建新聊天。

请求：

```json
{
  "character_id": "atri",
  "first_message": "今天聊聊部署认证系统",
  "defer_title": false
}
```

字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `character_id` | string | 是 | 角色 ID |
| `first_message` | string | 是 | 第一条用户消息，用于生成标题 |
| `defer_title` | boolean | 否 | 默认 `false`；为 `true` 时先返回临时标题，后台异步回填标题 |

响应：

```json
{
  "id": "20260421_b4c9d3e2",
  "title": "部署认证系统",
  "character_id": "atri",
  "created_at": "2026-04-21T12:00:00Z",
  "updated_at": "2026-04-21T12:00:00Z"
}
```

### `GET /api/chats/{chat_id}`

获取聊天详情和消息历史。

查询参数：

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---:|---|---|
| `limit` | int | 否 | 全量加载 | 返回消息数，范围 `1-5000` |
| `offset` | int | 否 | `0` | 消息偏移量 |

响应：

```json
{
  "metadata": {
    "id": "20260421_a3f8b2c1",
    "title": "天气闲聊",
    "character_id": "atri",
    "created_at": "2026-04-21T10:30:00Z",
    "updated_at": "2026-04-21T11:45:00Z",
    "message_count": 2
  },
  "messages": [
    {
      "role": "human",
      "content": "你好",
      "timestamp": "2026-04-21T10:30:05Z",
      "name": "JuyaoHuang"
    },
    {
      "role": "ai",
      "content": "你好，有什么想聊的？",
      "timestamp": "2026-04-21T10:30:08Z",
      "name": "atri"
    }
  ]
}
```

### `POST /api/chats/{chat_id}/update`

更新聊天标题。

请求：

```json
{
  "title": "新的聊天标题"
}
```

成功返回更新后的聊天元数据。

### `POST /api/chats/{chat_id}/delete`

删除聊天及其消息。

成功返回 `204 No Content`。

## WebSocket 实时对话

### 连接地址

认证关闭：

```text
ws://localhost:8430/ws
```

认证开启：

```text
ws://localhost:8430/ws?token=<JWT_TOKEN>
```

认证开启但缺少或传入无效 token 时，连接会被关闭，关闭码为 `1008`。服务日志中可能看到 `403 Forbidden` 或 `WebSocket authentication failed`。

### 客户端发送

发送文本消息：

```json
{
  "type": "input:text",
  "data": {
    "text": "你好",
    "chat_id": "20260421_a3f8b2c1",
    "character_id": "atri",
    "client_context": {
      "live2d_expression": "smile"
    }
  }
}
```

字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `type` | string | 是 | 固定为 `input:text` |
| `data.text` | string | 是 | 用户输入 |
| `data.chat_id` | string | 是 | 聊天 ID |
| `data.character_id` | string | 是 | 角色 ID |
| `data.client_context` | object | 否 | 前端运行时上下文，会传给 Agent |

心跳：

```json
{
  "type": "ping"
}
```

### 服务端返回

流式片段：

```json
{
  "type": "output:chat:chunk",
  "data": {
    "chunk": "你好",
    "chat_id": "20260421_a3f8b2c1",
    "character_id": "atri"
  }
}
```

完成事件：

```json
{
  "type": "output:chat:complete",
  "data": {
    "full_reply": "你好，有什么想聊的？",
    "chat_id": "20260421_a3f8b2c1",
    "character_id": "atri"
  }
}
```

错误事件：

```json
{
  "type": "error",
  "data": {
    "message": "Missing 'chat_id' field",
    "chat_id": "20260421_a3f8b2c1"
  }
}
```

心跳响应：

```json
{
  "type": "pong"
}
```

## ASR 接口

### `GET /api/asr/providers`

获取 ASR 提供商状态列表。

响应项：

```json
{
  "name": "browser",
  "display_name": "Browser Speech Recognition",
  "provider_type": "browser",
  "description": "浏览器语音识别",
  "active": true,
  "available": true,
  "reason": null,
  "supports_backend_transcription": false,
  "supports_browser_streaming": true,
  "config": {}
}
```

### `GET /api/asr/config`

返回当前 ASR 配置和提供商状态。

```json
{
  "config": {},
  "providers": []
}
```

### `PUT /api/asr/config`

增量更新 ASR 配置。请求体为 OLV 兼容配置片段。

```json
{
  "active_provider": "browser"
}
```

成功返回更新后的 `config` 和 `providers`。

### `POST /api/asr/switch`

切换当前 ASR 提供商。

```json
{
  "provider": "browser"
}
```

### `GET /api/asr/health`

获取 ASR 健康状态。

```json
{
  "active_provider": "browser",
  "active_available": true,
  "providers": []
}
```

### `POST /api/asr/transcribe`

上传音频并转写文字。

请求格式：`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `audio` | file | 是 | 音频文件 |
| `provider` | string | 否 | 指定 ASR 提供商 |

响应：

```json
{
  "provider": "faster-whisper",
  "text": "你好"
}
```

## TTS 接口

### `GET /api/tts/providers`

获取 TTS 提供商状态列表。

响应项：

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

返回当前 TTS 配置和提供商状态。

```json
{
  "config": {},
  "providers": []
}
```

### `PUT /api/tts/config`

增量更新 TTS 配置。请求体为 OLV 兼容配置片段。

```json
{
  "active_provider": "edge_tts"
}
```

### `POST /api/tts/switch`

切换当前 TTS 提供商。

```json
{
  "provider": "edge_tts"
}
```

### `GET /api/tts/health`

获取 TTS 健康状态。

```json
{
  "active_provider": "edge_tts",
  "active_available": true,
  "providers": []
}
```

### `GET /api/tts/voices`

获取语音列表。

查询参数：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `provider` | string | 否 | 指定 TTS 提供商 |

响应：

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

文本转语音。响应体是音频二进制，不是 JSON。

请求：

```json
{
  "text": "你好",
  "provider": "edge_tts",
  "voice_id": "zh-CN-XiaoxiaoNeural",
  "options": {}
}
```

响应 Header：

| Header | 说明 |
|---|---|
| `Content-Type` | 音频 MIME 类型，例如 `audio/mpeg` |
| `X-TTS-Provider` | 实际使用的 TTS 提供商 |

## Live2D 接口

### `GET /api/live2d/models`

获取 Live2D 模型列表。

响应项：

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

上传并解压 Live2D ZIP 模型。

请求格式：`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `model` | file | 是 | Live2D ZIP 包 |
| `name` | string | 否 | 展示名称 |

成功返回 `201 Created` 和模型摘要。

### `GET /api/live2d/models/{model_id}/expressions`

获取指定模型的表情列表。

响应：

```json
{
  "model_id": "hiyori",
  "expressions": ["smile", "angry"]
}
```

### `PUT /api/live2d/models/{model_id}`

更新 Live2D 模型元数据。

请求：

```json
{
  "name": "新模型名称"
}
```

`name` 长度限制为 `1-120` 字符。

### `DELETE /api/live2d/models/{model_id}`

删除一个 Live2D 模型目录。

成功返回 `204 No Content`。

## 静态资源

### `GET /api/assets/avatars/{filename}`

访问后端托管的角色头像文件。

### `GET /static/avatars/{filename}`

头像兼容路径，用于旧前端或旧数据。

### `GET /api/assets/live2d/{model_id}/{path}`

访问 Live2D 模型资源。`model_url` 和 `thumbnail_url` 会直接返回可访问 URL。

## 通用错误码

| 状态码 | 含义 | 常见场景 |
|---:|---|---|
| `200 OK` | 请求成功 | 查询、更新成功 |
| `201 Created` | 创建成功 | 创建聊天、角色、Live2D 模型 |
| `204 No Content` | 成功且无响应体 | 删除成功 |
| `400 Bad Request` | 请求参数错误 | 字段格式错误、上传文件不合法 |
| `401 Unauthorized` | 未认证或 token 无效 | 认证开启但缺少 JWT |
| `404 Not Found` | 资源不存在 | 角色、聊天、Live2D 模型不存在 |
| `429 Too Many Requests` | 请求过于频繁 | TTS 提供商限流 |
| `502 Bad Gateway` | 上游服务错误 | TTS 上游 API 调用失败 |
| `503 Service Unavailable` | 提供商不可用 | ASR/TTS 当前提供商不可用 |
| `500 Internal Server Error` | 后端内部错误 | 未预期异常 |

错误响应通常为：

```json
{
  "detail": "Chat '20260421_invalid' not found"
}
```

## 前端对接要点

1. 启动时调用 `GET /api/auth/status` 判断认证是否开启。
2. 认证开启时，未登录用户应跳转登录页，并通过 `GET /api/auth/login` 获取 GitHub OAuth 地址。
3. 登录成功后，前端回调页从 URL 读取 `token`，保存到本地，并在 HTTP 请求中加入 `Authorization: Bearer <token>`。
4. WebSocket 连接时追加 `?token=<token>`，否则认证开启时会被拒绝。
5. `GET /api/chats`、`GET /api/chats/{chat_id}` 等聊天接口只返回当前用户的数据。
6. `POST /api/auth/logout` 只返回成功，真正登出动作是前端删除本地 token。

## 相关源码位置

| 内容 | 路径 |
|---|---|
| FastAPI 应用工厂 | `atri/src/app.py` |
| HTTP 认证中间件 | `atri/src/middleware/auth.py` |
| 认证接口 | `atri/src/routes/auth.py` |
| WebSocket 接口 | `atri/src/routes/chat_ws.py` |
| 聊天接口 | `atri/src/routes/chats.py` |
| 角色接口 | `atri/src/routes/characters.py` |
| ASR 接口 | `atri/src/routes/asr.py` |
| TTS 接口 | `atri/src/routes/tts.py` |
| Live2D 接口 | `atri/src/routes/live2d.py` |
| 认证配置 | `atri/config/auth.yaml` |
