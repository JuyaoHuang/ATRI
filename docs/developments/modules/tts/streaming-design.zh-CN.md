---
status: active
owner: tts
created: 2026-07-08
updated: 2026-07-08
source_documents:
  - ../../wiki/TTS/tts-stream-design.md
  - ../../wiki/TTS/tts-stream-implement.md
  - ../../features/2026-07-tts-segment-streaming/README.zh-CN.md
related_code:
  - src/tts/sentence_divider.py
  - src/tts/segment_manager.py
  - src/routes/chat_ws.py
  - frontend/src/utils/websocket.ts
  - frontend/src/composables/useWebSocket.ts
  - frontend/src/composables/useAudioPlayer.ts
---

# TTS 分段流式化长期设计

本文沉淀 ATRI TTS 分段流式化的长期模块设计。这里的 streaming 指应用层分段合成和分段下发，不是 provider 原生音频流。

目标是在 LLM 回复仍在生成时尽早合成并播放第一段语音，同时保持聊天文本、历史、记忆和 VAD 打断语义稳定。

## 模块定位

TTS 是 LLM 文本回复的下游消费者。它消费已经发送给前端的文本 chunk，产出可播放音频段，但不拥有对话状态，也不决定聊天历史或记忆如何写入。

TTS 可以决定：

- 音频何时合成。
- 音频何时下发。
- 音频如何按 `sequence` 排队。
- 音频在 VAD interrupt、上下文切换或 WebSocket 关闭时如何丢弃。

TTS 不能决定：

- 哪些 AI 文本写入聊天历史。
- 记忆系统是否写入本轮回复。
- LLM generation 是否仍然有效。
- interrupted partial reply 保存哪些文本。

聊天显示和历史保存始终以 `output:chat:*` 为准。TTS segment 中的 `display_text` 和 `tts_text` 只用于合成、调试和播放关联，不作为聊天历史的新来源。

## 稳定原则

1. **应用层分段优先**：当前稳定路径复用 `TTSService.synthesize()`，每个文本段合成一个完整小音频。
2. **文本语义独立**：`output:chat:complete` 只表示文本完成，TTS 成败不回滚聊天文本。
3. **音频语义独立**：`output:audio:complete` 只表示后端不会再为该 generation 下发新音频段，不表示用户已经听完。
4. **generation 绑定**：每个自动 TTS 音频段必须携带 `generation_id`，旧 generation 的迟到音频必须可丢弃。
5. **有序下发**：后端允许并发合成，但对前端按 `sequence` 有序发送。
6. **打断只清音频**：VAD interrupt 会停止和丢弃旧音频，但不会让 TTS 反向改写历史或记忆。
7. **REST TTS 保留**：历史消息手动播放、测试入口和 streaming disabled fallback 继续走 REST TTS。

## 当前非目标

当前版本明确不做以下内容：

- 不实现 provider-native `synthesize_stream()`。
- 不改写 Edge TTS、SiliconFlow、CosyVoice 等 provider 的核心合成接口。
- 不引入 `heard_response`。
- 不要求前端回传“用户实际听到了哪段文本”。
- 不根据 TTS 播放进度修正 `partial_reply`。
- 不保证已经发给外部 provider 的请求能被真正取消，只保证返回后按 stale generation 规则丢弃。
- 不新增前端切换会话时主动通知后端取消旧 TTS 的 client -> server 协议。
- 不做二进制 WebSocket 音频帧；当前继续使用 JSON + base64。

## 术语

| 名称 | 含义 |
| --- | --- |
| `generation_id` | 一轮 LLM 回复的唯一标识，也是自动 TTS 音频段的失效边界。 |
| `segment_id` | 一个 TTS 文本段和音频段的唯一标识。 |
| `sequence` | 同一 generation 内的递增播放顺序。只有实际进入 TTS 合成的段占用 sequence。 |
| `display_text` | 原始文本段，来自已经发送给前端的 LLM chunk。 |
| `tts_text` | 送入 TTS provider 的清洗后文本。 |

## 整体链路

```text
用户输入或 ASR 自动提交
  -> 后端创建 generation_id
  -> LLM 流式输出文本 chunk
  -> 后端发送 output:chat:chunk
  -> 同一 chunk 进入 SentenceDivider
  -> SentenceDivider 产出可朗读文本
  -> TTSSegmentManager 调用 TTSService.synthesize()
  -> provider 返回完整小音频
  -> TTSSegmentManager 按 sequence 有序下发
  -> 后端发送 output:audio:segment
  -> 前端校验 generation/context 后入队播放
```

文本完成后的生命周期是：

```text
持久化聊天历史和记忆
  -> 发送 output:chat:complete
  -> 释放 LLM generation tracking
  -> 后台继续 finish 当前 TTS manager
  -> 发送 output:audio:complete
```

这里有两个独立生命周期：

- LLM 文本生命周期由 `current_generation_id` 跟踪。
- TTS 音频生命周期由 `current_tts_generation_id` 和 `TTSSegmentManager` 跟踪。

文本完成后，聊天主任务不等待所有 TTS segment 合成结束。TTS finish 在后台执行，避免旧音频合成阻塞下一轮聊天。

## 组件职责

### SentenceDivider

`src/tts/sentence_divider.py` 负责把 LLM chunk 累积为可合成文本段。

分段规则：

1. `feed(chunk)` 只接收新增 chunk，不接收完整回复。
2. 内部维护 buffer，直到可以切出可朗读文本段。
3. `faster_first_response=true` 时，第一段可以按短停顿提前切出。
4. 第一段之后，仍按完整句边界切分。
5. LLM complete 时调用 `flush()` 输出剩余 buffer。
6. 空白文本、纯标点文本和清洗后不可朗读文本不生成 segment。
7. 当前版本不做长度兜底切分，`max_concurrent_synthesis` 只控制并发，不拆分长句。

当前使用 `pysbd` 做句子边界检测，并使用 ATRI 自身的边界字符作为收口条件：

```python
SENTENCE_END_CHARS = frozenset("。！？!?…．.｡")
FIRST_RESPONSE_BREAK_CHARS = frozenset("，,、､；;：:")
```

`display_text` 保留原始文本。`tts_text` 会通过 TTS 文本过滤移除括号类动作或注释，例如 `（...）`、`(...)`、`[...]`、`【...】`。如果清洗后没有可朗读内容，该段会跳过，并且不占用 `sequence`。

`faster_first_response` 能降低首段等待时间，但可能让第一段更短，语音自然度略差。它必须保持可关闭。

### TTSSegmentManager

`src/tts/segment_manager.py` 中的 `TTSSegmentManager` 是应用层 TTS 编排器。它不是 provider，也不应变成 route helper。

它的职责是：

- 持有当前 `chat_id`、`character_id`、`generation_id`。
- 持有 `SentenceDivider`。
- 为每个可合成段分配 `segment_id` 和 `sequence`。
- 调用现有 `TTSService.synthesize()`。
- 用 `max_concurrent_synthesis` 限制同一 generation 内的并发合成数量。
- 用 `max_pending_segments` 控制等待下发的 segment 数量。
- 缓存先完成的后续 segment，直到前序 sequence 就绪或被跳过。
- 发送 `output:audio:segment`、`output:audio:complete`、`output:audio:error`。
- 在 interrupt 或 close 时取消未完成任务并清空内部状态。
- 对无法真正取消的 provider 请求，在返回后按 stale generation 规则丢弃。

合成可以并发，下发必须有序：

```text
sequence 0 合成慢
sequence 1 合成快
  -> manager 先缓存 sequence 1
  -> 等 sequence 0 成功或被 skip 后再发送 sequence 1
```

后端是 ordered delivery 的权威来源。前端可以用 `sequence` 做校验和防重复，但不承担复杂重排职责。

### Chat WebSocket

`src/routes/chat_ws.py` 只负责在 WebSocket 生命周期内挂载和调用 TTS manager：

- 新 generation 创建时，根据配置决定是否创建 manager。
- chat chunk 成功发送后，将同一 chunk 喂给 manager。
- chat complete 后释放 LLM 文本生命周期，并让 manager finish 音频生命周期。
- VAD interrupt 时同时取消 LLM task、失效 generation、interrupt 当前 TTS manager。
- WebSocket close 时关闭当前 TTS manager，避免迟到 provider 结果继续写连接。

分段、并发合成、排序和错误跳过不应写进 route。

### 前端播放器

前端负责消费 `output:audio:*` 事件并维护播放队列：

- `frontend/src/utils/websocket.ts` 将后端事件分发为内部 `audio:*` 事件。
- `frontend/src/composables/useWebSocket.ts` 校验 `chat_id`、`character_id`、`generation_id`，并把 base64 音频转为 `Blob`。
- `frontend/src/composables/useAudioPlayer.ts` 按 `generation_id + sequence` 管理自动 TTS segment。

手动播放历史 AI 消息仍走 REST TTS。手动 TTS 不依赖 `generation_id`，也不参与 streaming queue lifecycle。

## WebSocket Audio 协议

音频事件使用独立的 `output:audio:*` 命名空间，不塞进 `output:chat:*`。

### `output:audio:segment`

后端向前端发送一个完整小音频段。

```json
{
  "type": "output:audio:segment",
  "data": {
    "chat_id": "chat id",
    "character_id": "character id",
    "generation_id": "generation id",
    "segment_id": "segment id",
    "sequence": 0,
    "audio": "base64 encoded audio bytes",
    "media_type": "audio/mpeg",
    "display_text": "前端已显示的原始文本段",
    "tts_text": "实际送入 TTS 的文本段"
  }
}
```

### `output:audio:complete`

后端声明当前 generation 不会再产生新音频段。

```json
{
  "type": "output:audio:complete",
  "data": {
    "chat_id": "chat id",
    "character_id": "character id",
    "generation_id": "generation id",
    "last_sequence": 3
  }
}
```

如果本轮没有任何可朗读 segment，`last_sequence` 可以为 `null`。

### `output:audio:error`

后端声明某个 segment 失败或被跳过。

```json
{
  "type": "output:audio:error",
  "data": {
    "chat_id": "chat id",
    "character_id": "character id",
    "generation_id": "generation id",
    "segment_id": "segment id",
    "sequence": 2,
    "code": "tts_synthesis_failed",
    "message": "TTS synthesis failed for this segment."
  }
}
```

前端收到 error 后应跳过该 `sequence`，避免等待一个永远不会到达的音频段。

常见错误码：

| code | 含义 |
| --- | --- |
| `tts_synthesis_failed` | provider 或 `TTSService.synthesize()` 合成失败。 |
| `tts_invalid_audio` | TTS service 返回的 audio payload 不是 bytes。 |
| `tts_segment_queue_full` | 待处理 segment 数超过 `max_pending_segments`。 |

segment 失败不影响 `output:chat:complete`，也不触发 REST 自动补偿。自动补偿容易造成重复朗读或乱序。

## 播放与丢弃策略

前端接收 `output:audio:*` 后应通过 `frontend/src/utils/websocket.ts` 分发为内部事件：

```text
output:audio:segment  -> audio:segment
output:audio:complete -> audio:complete
output:audio:error    -> audio:error
```

`useWebSocket.ts` 负责协议消费：

- `audio:segment`：校验 `chat_id`、`character_id`、`generation_id`，将 base64 转成 `Blob`，交给 audio player。
- `audio:error`：记录错误，并通知 player 跳过该 `sequence`。
- `audio:complete`：标记该 generation 的后端音频下发完成，不改变聊天文本状态。
- `chat:complete`：当 streaming enabled 时，不再触发完整回复后的 REST auto TTS。

`useAudioPlayer.ts` 负责播放队列：

- 按 `generation_id + sequence` 管理自动 TTS segment。
- 按接收顺序入队，因为后端已经保证 ordered delivery。
- 丢弃重复 sequence。
- 丢弃旧 generation 的迟到 segment。
- VAD interrupt 时停止当前音频、清空队列，并把对应 generation 标记为 discarded。
- 会话或角色切换时停止旧音频，并丢弃旧上下文的迟到结果。

## 配置

应用层 streaming 配置位于 `config/tts_config.yaml` 顶层 `streaming` 区域。该区域与顶层 `enabled`、`auto_play` 共同决定自动分段 TTS 是否启用：

```yaml
enabled: true
auto_play: true

streaming:
  enabled: true
  segment_method: pysbd
  faster_first_response: true
  max_concurrent_synthesis: 2
  max_pending_segments: 12
```

后端创建 `TTSSegmentManager` 需要同时满足：

```text
tts.enabled == true
tts.auto_play == true
tts.streaming.enabled == true
```

字段含义：

| 字段 | 含义 |
| --- | --- |
| `streaming.enabled` | 是否启用应用层 TTS 分段流式化。关闭时保留 REST 自动 TTS 或不自动朗读的旧行为。 |
| `streaming.segment_method` | 文本分段方法。当前只支持 `pysbd`。 |
| `streaming.faster_first_response` | 是否允许第一段按短停顿提前切出。 |
| `streaming.max_concurrent_synthesis` | 同一 generation 内同时进行的 TTS 合成任务数。 |
| `streaming.max_pending_segments` | 后端允许等待下发或跳过的最大 segment 数。 |

`TTSSegmentManagerConfig` 还支持内部 `language` 参数，默认 `zh`。只有在需要暴露多语言分句配置时，才应把它提升为 YAML 用户配置。

provider 配置中的 `stream`、`streaming_mode` 等字段属于 provider 请求参数，不等同于 ATRI 应用层 `streaming.enabled`。

## 边界条件

### VAD interrupt

VAD 检测到 `speech_start` 时，后端应在同一条路径中：

1. 取消当前 LLM task。
2. 使当前 LLM generation 失效。
3. interrupt 当前 TTS manager。
4. 发送 `control:interrupt`。

如果文本 generation 已完成但 TTS manager 仍存在，`control:interrupt` 应携带 `current_tts_generation_id`。前端据此清理对应 generation 的音频队列。

interrupted partial reply 仍以“后端已经发送给前端的 LLM 文本”为准，不受 TTS 播放进度影响。

### TTS finish 后台化

发送 `output:chat:complete` 后，聊天主任务应释放。TTS 的 `finish()` 在后台继续执行，并用 `output:audio:complete` 表示音频下发结束。

后台 finish 失败时，后端记录 warning，并尝试 interrupt 对应 TTS manager。该失败不改变已经完成的聊天文本语义。

### 上下文切换

切换会话、切换角色或开始新一轮聊天不等同于 VAD interrupt。它不会生成 interrupted 历史，也不会改变后端 LLM 或 memory 语义。

前端应立即停止旧音频并丢弃旧上下文的迟到结果。只切换上下文但不发送新消息时，后端旧 TTS 可能自然完成并发送事件；前端按 `chat_id`、`character_id` 和 discarded generation 规则忽略。

切换后发送新消息时，新 generation 创建 TTS manager 前会 interrupt 旧 manager，后端旧 TTS 链路被清理。

### WebSocket close

WebSocket 关闭时，后端必须 interrupt 当前 TTS manager 并释放连接状态。provider 请求即使之后返回，也不得再尝试向已关闭连接发送音频。

### 长句

当前版本没有 `max_segment_chars`。如果一个长句只有逗号、没有句末符号，可能形成较长 segment。`max_concurrent_synthesis` 只控制并发，不控制切片长度。

### Payload 大小

当前使用 JSON + base64，保持现有 WebSocket 消息风格。音频 payload 明显变大时，再评估二进制 WebSocket frame 或音频对象存储引用。

## 后续扩展

后续可以在不破坏当前边界的前提下扩展：

- 增加 `max_segment_chars` 或长句短停顿兜底切分。
- 为 WebSocket 音频 payload 增加受配置控制的 debug 级结构化日志。
- 增加 `input:tts:cancel`，让前端上下文切换时主动通知后端取消旧 TTS。
- 评估二进制 WebSocket frame，降低 base64 开销。
- 抽象 provider-native streaming，但必须作为新接口设计，不影响当前应用层分段路径。
- 引入更细的播放状态统计，但不得默认回写聊天历史或记忆。
