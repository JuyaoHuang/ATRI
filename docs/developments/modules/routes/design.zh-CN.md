---
status: active
owner: routes
created: 2026-07-09
updated: 2026-07-12
source:
  - ../../module-design/CN/后端设计.md
  - ../../module-design/CN/后端API接口文档.md
  - src/app.py
  - src/main.py
  - src/routes/chats.py
  - src/routes/chat_ws.py
related_code:
  - src/app.py
  - src/main.py
  - src/routes/health.py
  - src/routes/auth.py
  - src/routes/characters.py
  - src/routes/chats.py
  - src/routes/chat_ws.py
  - src/routes/asr.py
  - src/routes/tts.py
  - src/routes/vision.py
  - src/routes/data.py
  - src/routes/live2d.py
---

# Routes 模块总设计

本文把 `src/routes/` 的整体设计接起来。旧 `后端设计.md` 和 `后端API接口文档.md` 里有大量路由层信息，但当前代码已经收敛成更清晰的结构：

1. `app.py` 负责应用工厂和共享服务注入。
2. `routes/*.py` 负责请求绑定和错误映射。
3. `api/` 目录负责协议说明，不在 `routes` 文档里重复字段表。

## 模块定位

Routes 模块是后端的**适配层**。它位于：

```text
client
  -> HTTP / WebSocket request
  -> src/routes/*
  -> app.state services / storage / ServiceContext
  -> domain modules
```

它的核心价值不是实现业务，而是把：

- HTTP / WebSocket 协议
- app.state 共享对象
- 领域异常
- 用户身份作用域

变成可被客户端稳定消费的入口。

## 设计目标

当前长期目标可以概括为 5 条：

1. 路由层只做适配，不重复实现领域逻辑。
2. 所有共享服务实例通过 `app.state` 提供，而不是每次请求重新 new。
3. HTTP 路由和 WebSocket 端点分工明确。
4. 用户身份隔离在进入 storage / service 前就被绑定。
5. 领域异常在路由层统一映射为 HTTP 状态码或 WebSocket 错误消息。

## 模块组成

当前 `src/routes/` 包含这些入口：

| 文件 | 类型 | 职责 |
| --- | --- | --- |
| `health.py` | HTTP | 最小健康检查。 |
| `auth.py` | HTTP | 认证开关、GitHub OAuth、当前用户、登出。 |
| `characters.py` | HTTP | 角色 CRUD 与头像上传。 |
| `chats.py` | HTTP | 聊天标题 CRUD、标题生成、消息详情读取。 |
| `asr.py` | HTTP | ASR 配置、Provider、上传转录。 |
| `tts.py` | HTTP | TTS 配置、Provider、声音列表、完整音频合成。 |
| `vision.py` | HTTP | 视觉安全配置读取与 `enabled` 白名单写入。 |
| `data.py` | HTTP | 短期记忆清理、长期记忆删除提交。 |
| `live2d.py` | HTTP | Live2D 模型 CRUD 与表达列表。 |
| `chat_ws.py` | WebSocket | 实时聊天、视觉截图协调、VAD 打断、ASR handoff、TTS segment 下发。 |

## 应用工厂与 app state

`src/app.py` 是 Routes 模块的上游容器。当前会把这些对象挂到 `app.state`：

| 字段 | 类型/来源 |
| --- | --- |
| `config` | 合并后的全局配置 |
| `storage` | `create_chat_storage(...)` 结果 |
| `service_context` | `ServiceContext` |
| `asr_service` | `ASRService` |
| `tts_service` | `TTSService` |
| `vad_service` | `VADService` |
| `vision_service` | `VisionService` |
| `auth_service` | `AuthService` |
| `character_storage` | `CharacterStorage` |
| `live2d_storage` | `Live2DStorage` |

长期约束：

- 路由层优先从 `app.state` 取共享对象；
- 不在路由函数里自己组装业务依赖图；
- lifespan 负责进程级资源启动与关闭。

## HTTP 路由的设计边界

当前 HTTP 路由的稳定职责是：

1. 解析请求体、路径参数、Query 参数、文件上传。
2. 调用 service / storage / service_context。
3. 把领域对象序列化为 API 响应模型。
4. 把领域异常翻译成 HTTP 状态码。

当前路由层**不**负责：

- 直接拼装 LLM 上下文；
- 直接管理 mem0 客户端；
- 直接操作底层 Provider SDK；
- 缓存跨请求的业务状态。

## WebSocket 路由的设计边界

`chat_ws.py` 是 routes 模块里最重的一条链路。它承担：

- 连接级用户身份绑定；
- per-connection send lock；
- 聊天 generation 跟踪；
- VAD 连接态；
- ASR transcript 自动接管；
- TTS 分段音频事件下发；
- 连接级视觉共享状态与 generation-keyed 截图 Future；
- 应用层 WebSocket 文本帧大小限制；
- generation complete、failure 与 interrupt 的终态竞争；
- generation durable-commit 认领与 VAD 重复归档防护。

它的长期定位是：

- WebSocket 编排层
- 不是纯粹的协议转发器
- 也不是 `src/vad/`、`src/asr/`、`src/tts/` 的替身

换句话说，`chat_ws.py` 负责把多个下游模块协同成一条实时链路。

## 用户身份边界

Routes 层当前是“用户作用域进入点”：

- HTTP 走 `get_request_user_id(request)`
- WebSocket 走 `get_websocket_user_id(websocket)`

这一步发生在进入 storage 和 ServiceContext 之前，因此：

- `chats.py` 里的列表、详情、删除都自动按用户隔离；
- `chat_ws.py` 里的 `ServiceContext.get_or_create_agent(...)` 也绑定了正确的 `user_id`；
- `data.py` 的短期/长期清理都以当前用户为作用域。

长期约束：

- 用户隔离不是 storage 的补丁，而是 routes 层就先把作用域带进去。

## 路由层与存储层的关系

当前路由层对 `storage` 的依赖主要有三类：

1. `storage`：
   - 聊天标题和消息
2. `character_storage`：
   - Persona 文件和托管头像
3. `live2d_storage`：
   - Live2D ZIP 与元数据

其中 `data.py` 则更多依赖 `ServiceContext` 和 `LongTermMemory`，而不是直接操作聊天存储本身。

## 标题生成的路由特殊性

`chats.py` 有一个特殊点：聊天标题生成并不通过 `ChatAgent`，而是直接：

```text
create_from_role("title_gen", llm_config)
```

长期意义：

- 路由层里允许存在少量“旁路 LLM 调用”；
- 但这种调用必须职责单一、边界清楚；
- 不能把完整聊天组合逻辑也塞回路由层。

## 错误映射原则

各路由文件当前遵循相同模式：

- 领域层抛自有异常
- 路由层 `_handle_*_error()` 做 HTTP 映射

例如：

- `ASRConfigError` -> `400`
- `ASRProviderUnavailableError` -> `503`
- `TTSAPIError` -> `502`
- `CharacterNotFoundError` -> `404`

WebSocket 路径则使用：

- `error`
- `output:chat:error`
- `control:listen-state(state=error)`

来表达不同层级的失败，而不是关闭连接：

- `error`：协议校验、未知类型、聊天归属等非 generation 终态错误；
- `output:chat:error`：已经关联到 `chat_id + character_id + generation_id` 的 pre-success 生成失败；
- `control:listen-state(state=error)`：VAD/ASR 监听链路错误。

`output:chat:error` 只能携带固定安全文案。Provider 原始错误、完整请求参数和图片 payload 不得跨越路由边界。

新客户端的 `input:text.request_id` 只服务于“generation 建立前的请求拒绝”。顶层 `error` 回显 `chat_id + request_id`，并在可识别时回显 `character_id`。前端只清理 `chat_id + request_id` 匹配且仍为 pending 的 submission；事件若携带 `character_id`，还必须与本地角色一致。`request_id` 不能替代 `generation_id`，也不能让通用协议错误终止正在 streaming 的 generation。

## 视觉路由与 WebSocket 协作

视觉能力同时经过 HTTP 与 WebSocket：

```text
PUT /api/vision/config
  -> 持久化 vision.enabled

input:vision:state
  -> 更新当前连接是否持有活动屏幕共享

input:text.image
  -> 直接文本/普通 ASR 的可选单图

control:vision:capture-request
  <-> input:vision:capture-result
  -> VAD + ASR 的 generation 截图握手
```

`WebSocketVisionState` 只属于单连接。它不能覆盖后端持久化开关；后端实际接受图片必须同时满足模块开启与连接状态开启。

截图 Future 必须在发送 capture request 前注册。等待发生在后台 generation task，不阻塞主 receive loop。timeout、断开、模块关闭、VAD interrupt 和迟到结果都要清理 pending Future。

直接 `input:text.image` 和 VAD capture result 都进入同一个有界校验函数。无效图片只被丢弃，合法文本继续处理。

LLM stream 正常耗尽后，路由先在 send lock 内把 active generation 标记为 `committing`，再进入 Storage/Memory durable effects。此后 speech_start 仍停止音频，但不得取消聊天任务或再次持久化 interrupted round；控制事件携带 `preserve_chat_generation=true`，正常 complete 负责最终收口。Storage/Memory 均为 best effort，complete 不是严格 durability ACK。

若下一轮 speech_end 在旧 generation 提交期间到达，路由最多等待 5 秒。超时后保留旧 commit task，发送 `chat_commit_busy` listen-state error，并且不调用 ASR、不创建新 generation；随后立即返回 receive loop，避免单个持久化 await 无限阻塞整条连接。

## 生命周期管理

当前 `lifespan()` 里做了三件长期有效的事：

1. 初始化 `storage`
2. 初始化 `ServiceContext`
3. 尝试预加载活跃本地 ASR Provider

关闭时：

- `ServiceContext.close_all()` 负责冲刷 Agent 和长期记忆句柄；
- 路由层不自己管理这些资源的最终关闭。

WebSocket 连接关闭时还会释放连接级 Vision coordinator、取消 pending capture，并清理 VAD/TTS 状态。

这意味着生命周期所有权在 `app.py`，不在具体路由文件里。

## 静态资源挂载

`app.py` 当前挂载了两类静态资源：

- `/api/assets/avatars`
- `/api/assets/live2d`

以及一个兼容别名：

- `/static/avatars`

长期约束：

- 路由层返回的是可访问 URL；
- 前端或外部调用方不应自己拼接本地磁盘路径。

## 与旧文档的取舍

旧 `后端设计.md` 和 `后端API接口文档.md` 中，已经被当前实现吸收的部分包括：

- FastAPI 应用工厂
- REST + WebSocket 双入口
- `src/routes/` 分拆
- `app.state` 共享服务
- 聊天 CRUD、认证、ASR/TTS、Live2D、数据清理等路由群

不再应被当作当前事实的部分包括：

- 旧 JWT query token WebSocket 认证说明
- 旧前端分仓假设引出的若干接口叙述
- 某些未落地或已改语义的早期 API 细节

因此，当前 Route 模块文档只保留结构与职责，不复刻整份接口字段表。

## 与 `api/` 文档的关系

需要明确两层文档的分工：

- `modules/routes/`
  - 回答“路由层为什么这样组织、依赖谁、负责什么”
- `docs/developments/api/`
  - 回答“每个接口具体长什么样”

这样可以避免把一份旧 API 文档重复抄到两个目录里。

## 相关文档

- [../../api/README.zh-CN.md](../../api/README.zh-CN.md)
- [../storage/design.zh-CN.md](../storage/design.zh-CN.md)
- [../agent/design.zh-CN.md](../agent/design.zh-CN.md)
- [Vision 模块长期设计](../vision/README.zh-CN.md)
