---
status: active
owner: tts
created: 2026-07-09
updated: 2026-07-09
source:
  - docs/developments/module-design/CN/TTS模块设计文档.md
  - docs/developments/features/2026-07-tts-segment-streaming/README.zh-CN.md
related_code:
  - src/tts/
  - src/routes/tts.py
  - src/routes/chat_ws.py
  - frontend/src/stores/tts.ts
  - frontend/src/composables/useWebSocket.ts
  - frontend/src/composables/useAudioPlayer.ts
---

# TTS 模块设计

## 模块定位

TTS 是 ATRI 中“消费 AI 文本并产生音频”的下游模块。它接收已经决定好要展示给用户的文本，再把文本转成完整音频或音频分段。

TTS 负责：

- 管理 Provider 注册表、配置和健康状态；
- 列出可选声音；
- 为 REST 请求合成完整音频；
- 在聊天 WebSocket 中按需产生 `output:audio:*` 分段事件。

TTS 不负责：

- 决定聊天历史写什么；
- 决定记忆是否写入；
- 解释 VAD 打断语义；
- 让 Provider 原生流式接口成为当前主路径。

## 设计目标

结合旧设计文档与近期实现日志，当前长期设计目标已经收敛为 4 条：

1. 对上游聊天链路保持“文本消费者”定位：
   TTS 只消费已决定展示的文本，不争夺聊天真相。
2. 对下游前端保持稳定协议：
   REST 完整音频和 WebSocket 分段音频都要有可预测的生命周期。
3. 对 Provider 保持插件式扩展：
   新 Provider 通过装饰器注册接入，而不是修改中心工厂逻辑。
4. 对配置保持后端主导：
   前端只能写白名单字段，敏感项与服务地址由后端拥有。

## 当前组件

| 组件 | 代码 | 职责 |
| --- | --- | --- |
| 接口层 | `src/tts/interface.py` | 定义 `synthesize()`、`get_voices()` 和预留的 `synthesize_stream()`。 |
| 工厂层 | `src/tts/factory.py` | 注册 Provider 元数据并按名称构造实例。 |
| 配置层 | `src/tts/config.py` | 读取 `config/tts_config.yaml`，处理默认值和敏感字段。 |
| 服务层 | `src/tts/service.py` | 协调配置、健康检查、Provider 切换、声音列表和完整音频合成。 |
| REST 路由层 | `src/routes/tts.py` | 暴露 `/api/tts/*` 管理和完整音频合成接口。 |
| 分段编排层 | `src/tts/sentence_divider.py`、`src/tts/segment_manager.py` | 负责应用层分段和有序下发。 |
| WebSocket 集成层 | `src/routes/chat_ws.py` | 在聊天 generation 中创建、喂给和关闭 `TTSSegmentManager`。 |

## 当前 Provider 事实

`src/tts/providers/__init__.py` 当前注册四个 Provider：

| Provider | 类型 | 默认媒体类型 | 说明 |
| --- | --- | --- | --- |
| `edge_tts` | `cloud` | `audio/mpeg` | 浏览器/云端友好的默认完整音频方案。 |
| `gpt_sovits_tts` | `local` | `audio/wav` | 调用外部 HTTP API，本仓库不内嵌模型。 |
| `siliconflow_tts` | `cloud` | 随响应格式变化 | 走 OpenAI 风格音频接口。 |
| `cosyvoice3_tts` | `local` | `audio/wav` | 通过 Gradio WebUI `/generate_audio` 调用外部服务。 |

一个关键当前事实是：**所有已注册 Provider 的 `supports_streaming` 元数据都还是 `false`**。`TTSInterface.synthesize_stream()` 仍然只是预留接口，不是当前主路径。

## 模块生命周期

### 启动与装配

当前装配路径是：

```text
FastAPI app state
  -> get_tts_service()
  -> TTSConfigStore
  -> TTSService
  -> src.tts.providers import side effects
  -> TTSFactory registry becomes available
```

关键约束：

- Provider 注册发生在模块导入阶段，不依赖运行时扫描。
- `TTSService` 是路由层唯一入口，路由层不直接实例化 Provider。
- YAML 配置先合并默认值，再参与 Provider 创建。

### 提供商切换

切换活跃 Provider 的稳定路径是：

```text
POST /api/tts/switch
  -> TTSService.switch_provider()
  -> update tts_model
  -> persist config
  -> later calls read new active provider
```

当前切换不做：

- 预热新 Provider；
- 自动回滚到旧 Provider；
- 抢占正在运行的聊天 generation。

因此切换是“配置切换”，不是“运行中会话迁移”。

### 声音列表与合成

声音列表和文本合成都经由 `TTSService`：

```text
GET /api/tts/voices
  -> create active/requested provider
  -> provider.get_voices()

POST /api/tts/synthesize
  -> create active/requested provider
  -> provider.health()
  -> provider.synthesize()
```

也就是说，当前没有长期存在的 Provider 单例池。Provider 更像按请求创建的轻量门面。

## 两条输出路径

### 1. REST 完整音频路径

```text
frontend manual play / auto-play fallback
  -> POST /api/tts/synthesize
  -> TTSService.synthesize()
  -> Provider returns complete audio bytes
  -> frontend plays Blob URL
```

这条路径仍然用于：

- 手动播放历史 AI 消息；
- 设置页测试播放；
- `streaming.enabled=false` 时的自动朗读 fallback。

### 2. WebSocket 分段音频路径

```text
output:chat:chunk already sent
  -> SentenceDivider
  -> TTSSegmentManager
  -> TTSService.synthesize() for each segment
  -> output:audio:segment / complete / error
```

这条路径只有在以下条件同时满足时才创建：

```text
tts.enabled == true
tts.auto_play == true
tts.streaming.enabled == true
```

它是**应用层分段**，不是 Provider 原生流式音频。

## 接口与服务边界

`modules/tts/interface.zh-CN.md` 详细描述了接口层，这里只保留长期设计结论：

1. `TTSInterface.synthesize()` 必须返回完整音频字节。
2. `TTSInterface.synthesize_stream()` 当前仍是预留接口。
3. `TTSService` 统一承担配置掩码、前端回写白名单、健康状态汇总和异常边界。
4. 路由层只做 HTTP 映射，不直接解释 Provider 细节。

这套分工是从旧设计文档中保留下来的核心骨架，也是当前代码仍在执行的部分。

## 前端消费边界

前端 `useWebSocket.ts` 和 `useAudioPlayer.ts` 共同维护两个事实：

1. `streamingAutoPlayEnabled=true` 时，`chat:complete` 不再触发 REST 自动朗读。
2. 手动播放历史消息依旧走 REST `synthesize()`。

因此即使后端已经支持 `output:audio:*`，前端也仍然保留 REST TTS 路线，不应把当前状态写成“前端已完全切换到流式音频”。

## 配置与 API 边界

当前稳定 REST 接口：

- `GET /api/tts/providers`
- `GET /api/tts/config`
- `PUT /api/tts/config`
- `POST /api/tts/switch`
- `GET /api/tts/health`
- `GET /api/tts/voices`
- `POST /api/tts/synthesize`

前端允许回写的 Provider 配置仍然是受限白名单，详细见 [config.zh-CN.md](config.zh-CN.md)。

## 健康检查与失败边界

当前健康检查不是独立后台任务，而是 Provider 同步 `health()` 的聚合结果：

- `list_providers()` 为每个 Provider 返回 `available` 和 `reason`
- `health()` 汇总活跃 Provider 与全量 Provider 状态
- `synthesize()` 在真正合成前再次检查活跃 Provider 是否可用

当前失败边界：

| 失败类型 | 当前行为 |
| --- | --- |
| 未知 Provider | 作为配置错误拒绝 |
| 必需配置缺失 | 由 Provider `health()` 或构造失败暴露 |
| 上游 API 错误 | 映射为 `TTSAPIError` / `502` |
| 速率限制 | 映射为 `TTSRateLimitError` / `429` |
| 文本为空 | 直接抛 `TTSSynthesisError` / `400` |

当前**没有**：

- 自动切备用 Provider；
- Provider 级指数退避；
- 合成结果缓存；
- 统一批量合成。

## 与聊天和 VAD 的边界

当前长期约束是：

- `output:chat:*` 仍是聊天显示和历史持久化的权威来源；
- TTS segment 的 `display_text` / `tts_text` 只服务于朗读和调试；
- VAD `speech_start` 使旧 generation 音频可丢弃，但不让 TTS 反向改写历史；
- interrupted partial reply 不根据 TTS 播放进度修正。

## 从近期 git log 确认的长期约束

近期主线日志集中在 `feat/tts-streaming`：

- `sentence divider`
- `segment manager`
- `websocket audio segments`
- `frontend websocket fix`
- `multilingual sentence boundaries`

这些提交共同确认了两个长期方向：

1. 第一版流式化已经明确选择“应用层切段 + 多次完整合成”，而不是 Provider 原生流式。
2. 前端消费端已经围绕 `generation_id + sequence` 收敛，TTS 模块后续扩展不能破坏这组协议语义。

因此，后续若新增 Provider 或优化链路，应优先保持：

- `output:audio:segment`
- `output:audio:complete`
- `output:audio:error`
- `generation_id`
- `sequence`

这些字段和事件的长期兼容性。

## 扩展与测试边界

旧设计文档里大量测试、部署、监控章节并未直接迁入当前文档，是因为它们大多还不是当前代码事实。当前仍然成立的扩展与测试边界只有这些：

1. 新 Provider 必须先满足 `TTSInterface` 和 `TTSFactory.register()` 契约。
2. 若前端要修改 Provider 字段，必须先进入后端写白名单。
3. 若未来引入 Provider 原生流式，必须单独补服务层消费设计，不能直接复用当前应用层分段协议。
4. 变更 TTS 分段行为时，至少要回看 `features/2026-07-tts-segment-streaming/` 与前端播放器逻辑。

## 与旧文档的关系

旧 TTS 设计文档中以下内容已不再等于当前事实：

- 6 个 Provider（其中 `openai_tts`、`elevenlabs_tts`、`cosyvoice2_tts` 并未出现在当前注册表）；
- Provider 原生流式输出是当前主路径；
- 前端一定在完整回复后统一走 REST 自动播放。

当前代码已经把“模块总览”和“流式分段设计”拆开：

- 模块总览：本页；
- 接口与工厂：[interface.zh-CN.md](interface.zh-CN.md)；
- 流式分段长期设计：[streaming-design.zh-CN.md](streaming-design.zh-CN.md)；
- CosyVoice3 Provider 细节：[cosyvoice3-provider.zh-CN.md](cosyvoice3-provider.zh-CN.md)；
- 2026-07 feature 过程：[../../features/2026-07-tts-segment-streaming/README.zh-CN.md](../../features/2026-07-tts-segment-streaming/README.zh-CN.md)。
