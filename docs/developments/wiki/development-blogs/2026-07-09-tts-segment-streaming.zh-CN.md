---
status: accepted
owner: tts
created: 2026-07-09
updated: 2026-07-09
source:
  - docs/developments/features/2026-07-tts-segment-streaming/README.zh-CN.md
  - docs/developments/wiki/TTS/tts-stream-design.md
  - docs/developments/wiki/TTS/tts-stream-implement.md
  - docs/developments/modules/tts/README.zh-CN.md
  - docs/developments/modules/tts/design.zh-CN.md
  - docs/developments/modules/tts/interface.zh-CN.md
  - docs/developments/modules/tts/streaming-design.zh-CN.md
related_code:
  - src/tts/sentence_divider.py
  - src/tts/segment_manager.py
  - src/routes/chat_ws.py
  - frontend/src/composables/useWebSocket.ts
  - frontend/src/composables/useAudioPlayer.ts
---

# ATRI TTS 分段流式化开发复盘

2026 年 7 月，ATRI 的 TTS 链路完成了一次很关键的转向：自动朗读不再只能等待完整 AI 回复结束后才开始，而是可以消费已经发送给前端的 LLM 文本 chunk，把它们切成更小的语音段，并通过 WebSocket 按序下发。

这篇复盘讲的是这次转向背后的取舍。这里的 streaming 指 **应用层分段流式化**，不是 provider 原生音频流；第一版也没有引入 `heard_response` 或播放确认回写。TTS 只是聊天文本的下游消费者，它让声音更早出现，但不改变聊天历史、记忆和 VAD interrupted partial reply 的语义。

## 背景

ATRI 的对话链路已经是流式的。后端通过 WebSocket 持续发送：

```text
output:chat:chunk
output:chat:complete
```

前端可以边收到 chunk 边显示文本，用户不必等整段回复生成完才看到内容。

但早期自动朗读链路还是完整音频模式：

```text
LLM 完整回复完成
  -> 前端收到 output:chat:complete
  -> 前端调用 REST /api/tts/synthesize
  -> 后端调用 TTSService.synthesize()
  -> provider 返回完整音频
  -> 前端播放 Blob URL
```

这条链路仍然有价值。它简单、稳定，也适合历史消息手动播放、设置页测试播放，以及关闭分段流式后的自动播放 fallback。问题是，它无法利用 LLM 文本本身已经流式输出这个事实。

当一个角色回复较长时，用户会先看到文本不断增长，却要等整段回复结束、REST 请求完成、完整音频返回之后，才听到第一句。对于语音陪伴或实时语音模式来说，这个等待很明显。

VAD 实时打断上线后，这个矛盾更突出。用户一开口，前端应当立即停掉旧音频；后端也要能识别旧 generation 的迟到 TTS 结果，避免它们混入新一轮对话。完整 REST 自动播放只有一个“整段音频请求”，很难表达“第 0 段、第 1 段、第 2 段分别属于哪一轮回复”。

因此，TTS 需要从“完整回复后的附加动作”变成“LLM 文本流的并行消费者”。

## 旧链路问题

旧链路的核心问题不是 REST 本身，而是它把自动朗读绑定在 `output:chat:complete` 之后。

第一，首段语音等待时间被完整回复长度放大。只要必须等完整文本，provider 再快也只能优化完整回复之后的合成时间，不能让用户在回复中途听到声音。

第二，文本生命周期和音频生命周期被挤在一起。`output:chat:complete` 本来只应该表示“聊天文本已经完成，可以显示、持久化、进入记忆流程”。如果自动朗读也只能从这里开始，前端就会把“文本完成”当成“现在开始发起音频”的信号。

第三，VAD interrupt 的清理粒度不够细。被打断时，前端可以停掉当前 audio element，也可以丢弃本地请求结果，但后端缺少一套和聊天 generation 对齐的音频事件生命周期。旧音频迟到时，系统需要明确知道它属于哪一轮回复。

第四，完整音频请求无法表达局部失败。如果一整段合成失败，就只有整段没有声音；但分段后可以让第 0 段失败、第 1 段继续播放，并通过协议告诉前端跳过失败的 `sequence`。

这次改造的目标不是删除 REST TTS，而是把“自动朗读长回复”从完整 REST 模式升级为 WebSocket 分段模式，同时保留 REST fallback。

## 为什么不是 Provider 原生流式

一个自然的问题是：既然要 streaming，为什么不直接实现 provider 原生 `synthesize_stream()`？

答案是：第一版需要解决的是产品链路和生命周期问题，不是先重写所有 provider。

当前 TTS 模块的稳定接口仍以 `TTSInterface.synthesize()` 为主。它接收文本，返回完整音频字节。`TTSInterface.synthesize_stream()` 只是预留接口，当前内置 provider 的 `supports_streaming` 元数据也没有把原生流式作为已落地主路径。

这意味着，如果第一版选择 provider-native streaming，需要同时解决几件额外事情：

- 每个 provider 的流式能力不一致，有的配置里存在 `stream` 或 `streaming_mode` 字段，但它们是 provider 请求参数，不等于 ATRI 应用层 `streaming.enabled`。
- 服务层需要定义如何消费 `AsyncIterator[bytes]`、如何映射音频分片边界、如何处理 provider 级失败和取消。
- 前端需要适配更底层的音频字节流，而不是接收一个可播放的小音频段。
- VAD interrupt、generation 失效、上下文切换、错误跳过仍然要重新设计。

相比之下，应用层分段更符合当时的代码现状：

```text
LLM 文本 chunk
  -> 应用层切成句子或短段
  -> 每段调用一次 TTSService.synthesize()
  -> 每段得到完整小音频
  -> WebSocket 按 sequence 下发
```

这样可以复用已有 provider、已有异常映射和已有媒体类型处理。用户感受到的“流式感”来自文本生成、分段合成和分段播放之间的重叠，而不要求 provider 边生成音频字节边播放。

这也是长期文档中强调的边界：未来可以单独设计 provider 原生流式，但它不是第一版 TTS segmented streaming 的事实，也不应把当前应用层分段协议包装成 provider-native streaming。

## 新链路改变了什么

新链路把聊天文本和 TTS 音频拆成两个并行但独立的生命周期：

```text
用户输入或 ASR 自动提交
  -> 后端创建 generation_id
  -> LLM 流式输出文本 chunk
  -> 后端发送 output:chat:chunk
  -> 同一份已发送文本进入 SentenceDivider
  -> TTSSegmentManager 调用 TTSService.synthesize()
  -> 后端发送 output:audio:segment
  -> 前端按 generation_id + sequence 入队播放
  -> 文本完成时发送 output:chat:complete
  -> 音频完成时发送 output:audio:complete
```

这里最重要的变化有三点。

第一，TTS 消费的是“已经发送给前端的文本”。`src/routes/chat_ws.py` 里先通过 `_send_generation_chunk()` 发送 `output:chat:chunk`，并把 chunk 追加到 generation partial reply 追踪里；发送成功后，才调用 `vad_state.feed_tts_text(generation_id, chunk)`。这样 TTS 不会朗读一段前端还没有看到、也不应进入 interrupted partial reply 的文本。

第二，文本完成和音频完成分离。`output:chat:complete` 仍是聊天显示、历史持久化和记忆流程的文本完成信号；`output:audio:complete` 只是说明该 `generation_id` 不会再产生新的音频 segment。它不表示用户已经听完，也不表示前端播放队列为空。

第三，自动 TTS 的身份从“整段回复”变成了 `generation_id + sequence`。`generation_id` 表示这段音频属于哪一轮 AI 回复；`sequence` 表示同一轮内的播放顺序。VAD interrupt 或上下文切换后，旧 `generation_id` 的迟到音频可以被后端拦截，也可以被前端丢弃。

## 配置与开关

应用层分段流式化由 `config/tts_config.yaml` 顶层 `streaming` 区域控制：

```yaml
enabled: true
auto_play: true

streaming:
  enabled: true
  segment_method: pysbd
  faster_first_response: true
  max_concurrent_synthesis: 3
  max_pending_segments: 12
```

后端只有在三个条件同时成立时，才会为当前聊天 generation 创建 `TTSSegmentManager`：

```text
tts.enabled == true
tts.auto_play == true
tts.streaming.enabled == true
```

其中 `streaming.enabled` 的职责非常明确：它只控制 ATRI 应用层“文本切段、多次完整合成、WebSocket 下发音频段”这条自动 TTS 路径。它不代表 provider 原生流式已经开启，也不覆盖 provider 配置里的 `stream`、`streaming_mode` 等字段。

如果 `streaming.enabled=false`，前端仍按旧逻辑在 `chat:complete` 后走 REST 自动 TTS。无论 streaming 是否开启，历史 AI 消息手动播放和设置页测试播放也继续走 REST `/api/tts/synthesize`。这就是 REST fallback 的边界：它不是旧代码残留，而是完整音频场景的稳定路径。

## 协议设计

音频事件没有塞进 `output:chat:*`，而是单独放在 `output:audio:*` 命名空间里。这样可以避免聊天文本协议被音频播放状态污染。

### `output:audio:segment`

`output:audio:segment` 表示后端下发了一个完整、可播放的小音频段：

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

`generation_id` 是失效边界。只要这轮回复被打断，旧 generation 的 segment 就不应该继续播放。

`sequence` 是播放顺序。后端允许多个 segment 并发合成，但下发时仍按 `sequence` 有序发送。前端可以用它做去重、跳过和调试，但不需要承担复杂重排。

`display_text` 和 `tts_text` 刻意分开。前者保留原始展示文本，后者是送入 TTS 的清洗文本。例如括号动作、旁白注释可以在展示中保留，但不一定适合朗读。

`audio` 第一版使用 JSON + base64，延续现有 WebSocket 消息风格。二进制 WebSocket frame 是后续可评估方向，不是当前事实。

### `output:audio:complete`

`output:audio:complete` 表示后端不会再为该 generation 下发新的音频 segment：

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

如果本轮没有任何可朗读 segment，`last_sequence` 可以是 `null`。需要注意，它不是“用户听完了”的确认，也不是播放进度回传。前端收到它，只能知道后端音频下发生命周期结束。

### `output:audio:error`

`output:audio:error` 表示某个 segment 合成或投递失败：

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

前端收到后应跳过该 `sequence`，避免播放队列永远等待一个不会到来的音频段。当前常见错误包括：

- `tts_synthesis_failed`：provider 或 `TTSService.synthesize()` 合成失败。
- `tts_invalid_audio`：服务层返回的 audio payload 不是 bytes。
- `tts_segment_queue_full`：待处理 segment 超过 `max_pending_segments`。

单段错误不回滚 `output:chat:complete`，也不触发 REST 自动补偿。自动补偿很容易造成重复朗读或乱序。

## SentenceDivider

`src/tts/sentence_divider.py` 负责把 LLM chunk 累积成可合成文本段。它的输入不是完整回复，而是每次新增的 chunk：

```text
feed(chunk) -> list[TTSTextSegment]
flush()     -> 剩余 buffer 的最后一个 segment
reset()     -> 清空 buffer 和 sequence
```

内部有一个 buffer。chunk 到来时追加到 buffer，然后尝试切出已经完整的文本段。第一版使用 `pysbd` 做句子边界检测，同时用 ATRI 自己的边界字符做收口：

```python
SENTENCE_END_CHARS = frozenset("。！？!?…．.｡")
FIRST_RESPONSE_BREAK_CHARS = frozenset("，,、､；;：:")
```

普通情况下，后续段落按完整句末符号切分。开启 `faster_first_response` 后，第一段可以在逗号、顿号、分号、冒号等短停顿处提前切出：

```text
关闭 faster_first_response:
  你好，我刚才在整理资料。 -> 一整句合成

开启 faster_first_response:
  你好， -> 先合成第一段
  我刚才在整理资料。 -> 后续按完整句合成
```

这个开关是体验取舍。它能降低首段等待时间，但第一段可能更短，语音自然度略差，所以必须可关闭。

`SentenceDivider` 还负责区分 `display_text` 和 `tts_text`：

- `display_text` 是已经发送给前端的原始文本段。
- `tts_text` 是经过 TTS 文本清洗后的朗读文本。

清洗会移除括号类动作或注释，例如 `（...）`、`(...)`、`[...]`、`【...】`。如果清洗后没有可朗读内容，该段直接跳过，并且不占用 `sequence`。这能避免“（微笑）。”这类文本被朗读成奇怪内容。

当前版本不做 `max_segment_chars` 长度兜底。如果模型输出一个很长但没有句末符号的句子，它可能在 `flush()` 时形成较长 segment。这是后续可以增强的地方。

## TTSSegmentManager

`src/tts/segment_manager.py` 里的 `TTSSegmentManager` 是这次改造的核心编排器。它不是 provider，也不是路由 helper，而是应用层 TTS 生命周期管理器。

它持有当前：

- `chat_id`
- `character_id`
- `generation_id`
- `SentenceDivider`
- `TTSService`
- 三个发送回调：`send_segment`、`send_complete`、`send_error`

它的主要工作是把 `SentenceDivider` 产出的 `TTSTextSegment` 变成 `TTSAudioSegment`：

```text
TTSTextSegment
  -> TTSService.synthesize(tts_text)
  -> TTSAudioSegment
  -> output:audio:segment
```

并发和排序是这里最重要的两个细节。

`max_concurrent_synthesis` 通过 `asyncio.Semaphore` 控制同一 generation 内同时进行的合成数量，避免一条长回复把 provider 请求打满。

合成可以并发完成，但下发必须有序。manager 内部维护 `completed_segments`、`skipped_sequences` 和 `next_sequence_to_send`。如果 `sequence=1` 先于 `sequence=0` 合成完成，它会先被缓存，直到 `sequence=0` 成功下发或被 error 跳过：

```text
sequence 0 合成慢
sequence 1 合成快
  -> 缓存 sequence 1
  -> 等 sequence 0 完成或跳过
  -> 再下发 sequence 1
```

这让前端播放器保持简单。前端可以按接收顺序入队，因为后端已经承担 ordered delivery。

`finish()` 做三件事：先 `flush()` 分句器中的剩余文本，再等待已经创建的合成任务完成，最后发送 `output:audio:complete`。`interrupt()` 和 `close()` 则会清空内部缓存、取消未完成任务，并重置分句器。对于已经发给外部 provider、无法真正取消的请求，返回后也会因为 manager 已经 interrupted 或 closed 而被丢弃。

这里的边界很关键：TTS manager 可以清理音频任务，但不持久化聊天、不写记忆、不生成 interrupted partial reply。

## 后端 WebSocket 协同

`src/routes/chat_ws.py` 负责把 manager 挂进聊天 WebSocket 生命周期，但不把分段、排序和并发逻辑写进 route。

在一轮新聊天开始时，后端创建新的 `generation_id`，并用 `WebSocketVADState` 追踪两类生命周期：

- `current_generation_id`：LLM 文本生命周期，用于判断聊天 chunk、complete、历史和记忆副作用是否仍有效。
- `current_tts_generation_id`：TTS 音频生命周期，用于判断音频 segment、complete、error 是否仍可发送。

这两个字段不能混用。文本完成后，`current_generation_id` 可以释放；但 TTS 可能还在合成或播放，所以 `current_tts_generation_id` 需要等 `output:audio:complete` 或 interrupt 后再释放。

chunk 循环中的顺序也很讲究：

```text
检查 generation 仍有效
  -> 发送 output:chat:chunk
  -> append_generation_reply()
  -> feed_tts_text()
```

这保证 interrupted partial reply 仍以“已经发送给前端的 LLM 文本”为准。

文本完成时，后端先完成原有聊天流程：

```text
持久化 human / ai 消息
  -> memory_manager.on_round_complete()
  -> 发送 output:chat:complete
  -> complete_generation()
```

然后如果存在 TTS manager，启动后台 `_start_tts_finish_task()`。这样 `output:chat:complete` 不会被剩余 TTS 合成阻塞。后续音频 flush 和 `output:audio:complete` 在音频生命周期里结束。

发送音频事件时，`_send_tts_generation_event()` 会在 WebSocket send lock 下检查 `vad_state.is_tts_generation_active(generation_id)`。这一步是后端 stale generation 防线：如果 TTS generation 已经被 interrupt 或 close，迟到的音频事件不会再发给前端。

VAD `speech_start` 到来时，后端会在同一路径中：

```text
获取 interrupted partial reply snapshot
  -> invalidate_current_generation()
  -> cancel_current_chat_task()
  -> interrupt_tts_generation()
  -> 发送 control:interrupt
```

如果 LLM 文本已经完成但 TTS 还没结束，`control:interrupt` 仍可携带 `current_tts_generation_id`。这让前端能准确清理仍在播放或排队的旧音频。

WebSocket 关闭时，后端同样会 interrupt 当前 TTS manager，并释放 VAD session，避免 provider 请求完成后继续尝试写一个已经关闭的连接。

## 前端协同

前端改造主要落在 `frontend/src/composables/useWebSocket.ts` 和 `frontend/src/composables/useAudioPlayer.ts`。

`useWebSocket.ts` 负责消费协议事件。收到 `audio:segment` 后，它会检查：

- `generation_id` 是否存在；
- `segment_id` 是否存在；
- `sequence` 是否是非负整数；
- `chat_id` 和 `character_id` 是否仍是当前上下文。

如果上下文已经切换，前端会调用 `audioPlayer.discardGenerationAudio(generationId)`，让这个旧 generation 的后续音频都失效。通过校验后，前端把 base64 音频转成 `Blob`，再交给 `enqueueAudioSegment()`。

`useAudioPlayer.ts` 负责播放队列。streaming 音频被标记为 `source: 'stream'`，并携带 `generationId`、`segmentId`、`sequence` 和 `mediaType`。

播放器维护了几个关键状态：

- `discardedGenerationIds`：记录已被丢弃的 generation，用于拒绝迟到音频。
- `streamedAudioGenerationStates`：记录每个 generation 已见过的 `sequence`，用于去重和跳过。
- `activeSynthesisGenerationIds`：保留 REST 自动合成期间的 generation 失效检查。
- `discardEpoch`：帮助手动或自动合成请求识别 interrupt 前后的边界。

收到 `audio:error` 时，前端调用 `skipAudioSegment(generationId, sequence)`。它不会播放音频，只是把这个 sequence 标记为已见过，避免后续等待。

收到 `audio:complete` 时，前端调用 `completeAudioGeneration(generationId)`，标记后端不会再发新 segment。但这仍然不是播放完成确认。

`chat:complete` 的逻辑也发生了变化。当前端发现 `ttsStore.streamingAutoPlayEnabled` 为 true 时，不再调用 `enqueueAutoSpeech()` 发起 REST 自动朗读。只有 streaming disabled 时，才回到旧的 complete 后 REST 自动 TTS。

VAD interrupt 或上下文切换时，前端会停止当前 audio element、清空队列，并把相关 generation 标记为 discarded。后续如果旧 generation 的 `output:audio:segment` 迟到，会在进入队列前被丢弃。

## 验收

这次验收关注的是协议语义和生命周期，而不只是“能播放声音”。

后端 TTS 单元测试覆盖：

```bash
uv run pytest tests/tts/ -v
```

重点验证：

- `SentenceDivider` 能按中文句号切分。
- `faster_first_response=true` 时，第一段可以按短停顿提前切出。
- 英文、日文常见句末符号可以作为完整句边界。
- 括号动作和注释只影响 `tts_text`，不影响 `display_text`。
- 空白、纯标点、清洗后不可朗读文本不会生成 segment。
- `TTSSegmentManager` 可以在合成乱序完成时按 `sequence` 下发。
- `interrupt()` 后迟到 provider 结果不会再发送。
- 单段失败会产生 `output:audio:error`，并继续后续 segment。

后端 WebSocket 测试覆盖：

```bash
uv run pytest tests/routes/test_chat_ws.py -v
```

重点验证：

- `streaming.enabled=false` 时不发送 `output:audio:*`。
- `streaming.enabled=true` 时会发送 `output:audio:segment` 和 `output:audio:complete`。
- `output:chat:complete` 不等待后台 TTS finish。
- VAD `speech_start` 会取消当前 TTS manager，并发送带 `generation_id` 的 `control:interrupt`。
- TTS segment 失败不影响 `output:chat:complete`。

基础检查和前端检查记录为：

```bash
uv run python -m mypy src/ --ignore-missing-imports
uv run ruff format src/tts src/routes/chat_ws.py tests/tts tests/routes/test_chat_ws.py
uv run ruff check src/tts src/routes/chat_ws.py tests/tts tests/routes/test_chat_ws.py --fix
uv run pytest tests/ -v

cd frontend
npm run type-check
npm run lint
npm run build
```

人工验收则围绕四个场景：

1. 开启 `enabled=true`、`auto_play=true`、`streaming.enabled=true` 后，长回复第一段音频应早于 `output:chat:complete` 播放。
2. 说话触发 VAD interrupt 后，当前音频立即停止，旧 generation 的后续 segment 不再播放。
3. 关闭 `streaming.enabled` 后，自动 TTS 回到 complete 后 REST 合成路径。
4. 点击历史 AI 消息播放时，仍通过 REST TTS 播放，不依赖 streaming generation。

## 和原链路相比

这次改造后，ATRI 同时保留了两条 TTS 输出路径。

| 场景 | 改造前 | 改造后 |
| --- | --- | --- |
| 自动朗读长回复 | `output:chat:complete` 后 REST 合成完整音频 | `output:chat:chunk` 后分段合成，通过 `output:audio:segment` 下发 |
| 手动播放历史消息 | REST `/api/tts/synthesize` | 仍走 REST `/api/tts/synthesize` |
| 设置页测试播放 | REST `/api/tts/synthesize` | 仍走 REST `/api/tts/synthesize` |
| streaming disabled fallback | REST 自动 TTS | 仍走 REST 自动 TTS |
| 打断旧音频 | 前端停播完整音频 | 前后端都按 `generation_id` 丢弃旧 segment |
| 音频完成语义 | 隐含在完整 REST 请求结束里 | 独立 `output:audio:complete` |
| 单段失败 | 整段自动朗读失败或前端报错 | `output:audio:error` 跳过失败 `sequence`，后续继续 |

换句话说，TTS segmented streaming 改变的是自动朗读的时机、粒度和生命周期；它没有改变聊天文本的权威来源，也没有移除 REST 完整音频能力。

## 边界与后续

第一版已经明确的边界有：

- 当前是应用层分段流式，不是 provider 原生 `synthesize_stream()`。
- `streaming.enabled` 控制的是 ATRI 应用层分段自动 TTS，不等同于 provider 配置中的 `stream` 或 `streaming_mode`。
- `output:audio:complete` 不表示用户已经听完。
- 当前没有 `heard_response`，也没有前端播放确认回写聊天历史或记忆。
- interrupted partial reply 仍以已经发送给前端的 `output:chat:chunk` 文本为准。
- 对已发出的外部 provider 请求，不承诺真正取消；系统只保证返回后按 generation 失效规则丢弃。
- 前端上下文切换当前主要由前端本地丢弃旧音频处理，没有新增 `input:tts:cancel` 这类 client -> server 主动取消协议。
- WebSocket 音频仍是 JSON + base64，不是二进制 audio frame。

后续可以沿着几条线继续演进。

第一是分段质量。当前没有 `max_segment_chars`，长句兜底切分还可以加强。`faster_first_response` 也可以继续调优，让首段更快但不过碎。

第二是音频承载方式。如果 base64 payload 成为瓶颈，可以评估二进制 WebSocket frame，或者让后端返回可下载的临时音频对象引用。

第三是前后端取消协议。上下文切换时，如果需要更快释放后端 provider 请求，可以新增 `input:tts:cancel`，但它应是音频生命周期协议，不应影响聊天历史。

第四是 provider 原生流式。如果未来某些 provider 真正提供稳定的音频流接口，应先补服务层消费设计，再考虑如何映射到 WebSocket。它可以成为新的优化路径，但不能偷换当前应用层分段协议的语义。

第五是播放状态统计。系统可以收集“开始播放、播放结束、用户中断”等指标，但默认不应把它们回写为聊天真相。是否引入类似 `heard_response` 的链路，需要单独设计，并明确它和历史、记忆、interrupted partial reply 的关系。

这次改造最重要的收获，是把 TTS 从“完整回复之后的附属动作”推进成了一个有独立生命周期的下游消费者。它可以更早、更稳地把角色声音送到前端，同时仍然守住 ATRI 的核心边界：聊天文本由 `output:chat:*` 决定，音频只负责被听见。
