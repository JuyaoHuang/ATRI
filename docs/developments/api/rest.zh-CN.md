---
status: active
owner: api
created: 2026-07-09
updated: 2026-07-09
related_code:
  - src/routes/health.py
  - src/routes/characters.py
  - src/routes/chats.py
  - src/routes/data.py
  - src/routes/asr.py
  - src/routes/tts.py
  - src/routes/live2d.py
  - src/app.py
---

# REST API 总览

本文按业务分组说明当前 REST 路由。除特别标记为“公开”的路径外，其余业务接口在认证开启时都需要有效会话，具体规则见 [auth.zh-CN.md](auth.zh-CN.md)。

## 通用约定

- 默认响应格式是 `application/json`。
- 时间字段当前统一返回字符串时间戳，调用方应按字符串处理，不要假设固定格式之外的更多语义。
- 只有 `POST /api/tts/synthesize` 和静态资源路径返回非 JSON 内容。
- FastAPI 参数校验失败时会返回 `422`，`detail` 是数组而不是字符串。

## 健康检查

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/health` | 公开 | 服务存活检查。 |

响应示例：

```json
{
  "status": "ok"
}
```

## 角色

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/characters` | 列出所有角色摘要。 |
| `GET` | `/api/characters/{character_id}` | 获取单个角色详情。 |
| `POST` | `/api/characters` | 创建角色。 |
| `PUT` | `/api/characters/{character_id}` | 更新角色。 |
| `DELETE` | `/api/characters/{character_id}` | 删除角色。 |
| `POST` | `/api/characters/{character_id}/avatar` | 上传或替换角色头像。 |

### 返回字段

角色摘要 `CharacterSummary` 包含：

- `character_id`
- `name`
- `avatar`
- `avatar_url`
- `greeting`
- `description`
- `created_at`
- `updated_at`
- `is_system`

角色详情 `CharacterDetail` 在摘要基础上额外包含 `system_prompt`。

### 创建和更新

`POST /api/characters` 请求体：

```json
{
  "character_id": "atri",
  "name": "ATRI",
  "greeting": "你好呀",
  "description": "陪伴型角色",
  "system_prompt": "你是 ATRI。"
}
```

注意点：

- `character_id` 在当前请求模型中可省略；省略时最终 ID 由存储层决定。
- `name` 长度限制为 1 到 50。
- `system_prompt` 在创建时必填，在更新时可选。

### 头像上传

`POST /api/characters/{character_id}/avatar` 使用 `multipart/form-data`，字段名固定为 `avatar`。

成功响应：

```json
{
  "character_id": "atri",
  "avatar": "atri.png",
  "avatar_url": "http://localhost:8430/api/assets/avatars/atri.png"
}
```

常见错误：

- `400`：头像格式或内容不合法，角色名冲突，或系统角色不允许的修改。
- `404`：角色不存在。

## 聊天

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/chats` | 列出当前用户的聊天会话。 |
| `POST` | `/api/chats` | 创建聊天会话元数据。 |
| `GET` | `/api/chats/{chat_id}` | 获取聊天详情和消息历史。 |
| `POST` | `/api/chats/{chat_id}/update` | 更新聊天标题。 |
| `POST` | `/api/chats/{chat_id}/delete` | 删除聊天。 |

### `GET /api/chats`

支持查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `character_id` | string，可选 | 只返回某个角色下的聊天。 |

列表项会返回 `message_count`，便于前端做分页和预估。

### `POST /api/chats`

请求体：

```json
{
  "character_id": "atri",
  "first_message": "今天有点累",
  "defer_title": true
}
```

这个接口只做两件事：

1. 创建聊天元数据。
2. 根据 `first_message` 生成标题，或者先给一个临时标题再异步回填。

它不会把 `first_message` 写入消息历史。真正的聊天正文仍由 WebSocket `input:text` 驱动。

标题行为：

- `defer_title=false`：优先同步调用 LLM 生成标题，失败时回退到截断标题。
- `defer_title=true`：立即返回临时标题，并在后台尝试回填更好的标题。

### `GET /api/chats/{chat_id}`

支持查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `limit` | integer，可选 | 返回消息数上限，范围 `1..5000`。省略时返回整段会话。 |
| `offset` | integer，默认 `0` | 分页偏移量。 |

响应体：

```json
{
  "metadata": {
    "id": "chat_xxx",
    "title": "今天有点累",
    "character_id": "atri",
    "created_at": "2026-07-09T08:00:00Z",
    "updated_at": "2026-07-09T08:05:00Z",
    "message_count": 2
  },
  "messages": [
    {
      "role": "human",
      "content": "今天有点累",
      "timestamp": "2026-07-09T08:00:01Z",
      "name": "octocat"
    },
    {
      "role": "ai",
      "content": "那我们先慢一点说。",
      "timestamp": "2026-07-09T08:00:03Z",
      "name": "atri",
      "generation_id": "gen_xxx",
      "interrupted": false,
      "interrupt_reason": null
    }
  ]
}
```

### 更新和删除

这里保留了历史兼容路径，而不是更“RESTful”的 `PATCH` / `DELETE`：

- 更新标题：`POST /api/chats/{chat_id}/update`
- 删除聊天：`POST /api/chats/{chat_id}/delete`

找不到聊天时返回 `404`。

## 数据维护

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `DELETE` | `/api/data/characters/{character_id}/chats/{chat_id}/short-term-memory` | 清理当前用户在某个聊天下的短期记忆文件与运行时缓存。 |
| `DELETE` | `/api/data/characters/{character_id}/long-term-memory` | 提交当前用户在某个角色下的长期记忆删除请求。 |

统一响应结构：

```json
{
  "character_id": "atri",
  "user_id": "octocat",
  "chat_id": "chat_xxx",
  "target": "short_term_memory",
  "status": "cleared",
  "message": "短期记忆已清理，并已同步当前运行中的记忆状态。",
  "details": {
    "removed_file": true,
    "cache_reset": true
  }
}
```

注意点：

- 短期记忆清理会先验证 `chat_id` 属于当前用户和当前角色，不匹配时返回 `404`。
- 长期记忆后端不可用时返回 `503`。
- 长期记忆提交失败时返回 `502`。

## ASR

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/asr/providers` | 列出已注册 ASR provider 的状态。 |
| `GET` | `/api/asr/config` | 读取当前 ASR 配置和 provider 状态。 |
| `PUT` | `/api/asr/config` | 合并写入部分 ASR 配置。 |
| `POST` | `/api/asr/switch` | 切换当前活跃 provider。 |
| `GET` | `/api/asr/health` | 查询活跃 provider 和整体健康状态。 |
| `POST` | `/api/asr/transcribe` | 上传音频并转写。 |

### Provider 状态

`/providers`、`/config`、`/health` 都会返回 `ASRProviderStatus` 列表，核心字段包括：

- `name`
- `display_name`
- `provider_type`
- `active`
- `available`
- `reason`
- `supports_backend_transcription`
- `supports_browser_streaming`
- `config`

### `POST /api/asr/transcribe`

使用 `multipart/form-data`：

| 字段 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| `audio` | form file | 是 | 上传的音频文件。 |
| `source` | form | 否 | 来源标记。 |
| `sample_rate` | form | 否 | 采样率。 |
| `channels` | form | 否 | 声道数。 |
| `encoding` | form | 否 | 编码格式。 |
| `provider` | query | 否 | 指定本次使用的 provider。 |

成功响应：

```json
{
  "provider": "faster_whisper",
  "text": "你好，今天过得怎么样"
}
```

常见错误：

- `400`：配置错误、请求音频不合法或转写失败。
- `503`：指定 provider 当前不可用。

## TTS

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/tts/providers` | 列出已注册 TTS provider 的状态。 |
| `GET` | `/api/tts/config` | 读取当前 TTS 配置和 provider 状态。 |
| `PUT` | `/api/tts/config` | 合并写入部分 TTS 配置。 |
| `POST` | `/api/tts/switch` | 切换当前活跃 provider。 |
| `GET` | `/api/tts/health` | 查询活跃 provider 和整体健康状态。 |
| `GET` | `/api/tts/voices` | 列出当前或指定 provider 的可用音色。 |
| `POST` | `/api/tts/synthesize` | 合成完整文本并直接返回音频字节。 |

### `GET /api/tts/voices`

支持可选查询参数 `provider`。成功响应：

```json
{
  "provider": "edge_tts",
  "voices": [
    {
      "id": "zh-CN-XiaoxiaoNeural",
      "name": "Xiaoxiao",
      "language": "zh-CN"
    }
  ]
}
```

### `POST /api/tts/synthesize`

请求体：

```json
{
  "text": "你好，欢迎回来。",
  "provider": "edge_tts",
  "voice_id": "zh-CN-XiaoxiaoNeural",
  "options": {
    "rate": "+0%"
  }
}
```

返回值不是 JSON，而是音频二进制：

- `Content-Type`：由 provider 返回的 `media_type` 决定。
- `X-TTS-Provider`：实际参与合成的 provider 名称。

示例：

```bash
curl -X POST http://localhost:8430/api/tts/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text":"你好","voice_id":"zh-CN-XiaoxiaoNeural"}' \
  --output reply.audio
```

常见错误：

- `400`：配置错误或文本请求非法。
- `429`：TTS provider 命中限流。
- `502`：上游 TTS API 调用失败。
- `503`：provider 不可用。

## Live2D

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/live2d/models` | 列出所有已存储模型。 |
| `POST` | `/api/live2d/models` | 上传并解压一个 Live2D ZIP 模型包。 |
| `GET` | `/api/live2d/models/{model_id}/expressions` | 查询模型表情列表。 |
| `PUT` | `/api/live2d/models/{model_id}` | 更新模型可变元数据。 |
| `DELETE` | `/api/live2d/models/{model_id}` | 删除模型目录。 |

`Live2DModelSummary` 会返回：

- `id`
- `name`
- `model_path`
- `model_url`
- `thumbnail_url`
- `expressions`
- `created_at`
- `is_default`

上传接口使用 `multipart/form-data`：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `model` | 是 | ZIP 压缩包。 |
| `name` | 否 | 上传后显示名称。 |

更新接口请求体：

```json
{
  "name": "ATRI Summer"
}
```

常见错误：

- `400`：ZIP 包格式不合法或存储操作失败。
- `404`：模型不存在。

## 静态资源

这些路径是公开的，不参与认证中间件：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/assets/avatars/{filename}` | 角色头像正式资源路径。 |
| `GET` | `/static/avatars/{filename}` | 头像兼容别名路径。 |
| `GET` | `/api/assets/live2d/{model_id}/{relative_path}` | Live2D 模型和缩略图资源。 |

调用方通常不需要手拼这些 URL，而是直接使用业务接口返回的：

- `avatar_url`
- `model_url`
- `thumbnail_url`

## 通用错误

### 字符串 `detail`

多数业务错误会返回：

```json
{
  "detail": "Chat 'chat_xxx' not found"
}
```

常见状态码：

| 状态码 | 典型场景 |
| --- | --- |
| `400` | 配置无效、请求业务参数不成立、上传内容非法。 |
| `401` | 认证开启时缺少 Cookie/Bearer，或会话已过期。 |
| `404` | 聊天、角色、模型等资源不存在。 |
| `429` | TTS 限流。 |
| `502` | 上游服务失败，例如长期记忆删除或某些 TTS API 调用失败。 |
| `503` | provider 或后端能力暂不可用。 |

### FastAPI 校验错误

请求体、查询参数或表单字段不满足模型约束时，会返回 `422`：

```json
{
  "detail": [
    {
      "loc": ["body", "name"],
      "msg": "Field required"
    }
  ]
}
```

## 相关文档

- [认证 API 与鉴权协议](auth.zh-CN.md)
- [WebSocket 协议](websocket.zh-CN.md)
- [事件字典](events.zh-CN.md)
