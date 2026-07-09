---
status: accepted
owner: vad
created: 2026-07-08
updated: 2026-07-08
source:
  - docs/developments/features/2026-06-vad-realtime-interrupt/dev-log.zh-CN.md
related_code:
  - src/vad/
  - src/asr/
  - src/routes/chat_ws.py
  - frontend/src/components/chat/
  - frontend/src/composables/
---

# ATRI VAD 实时打断开发复盘

ATRI 原本已经有 ASR 和 TTS，但它们更像两个按钮能力：用户录完音后转文字，AI 回复完整后再把整段文本合成音频。这个模式能跑通语音输入和朗读，却做不到自然对话中的一件关键事：用户一开口，角色就应该停下来。

VAD 实时打断的目标，就是把“用户开始说话”变成对话控制事件，而不是等 ASR 识别完文字后才响应。

这篇文章只复盘 VAD 第一版。它不逐条搬运开发流水，也不把后续 TTS 分段流式化混进来；TTS 在这里始终是 LLM 文本回复的下游消费者。

## 背景

旧链路里有三条相对独立的路径：

```text
ASR：前端录音或浏览器识别 -> 文本
LLM：WebSocket 输入文本 -> 流式输出文本
TTS：完整文本 -> REST TTS -> 完整音频 -> 前端播放
```

这三条链路可以配合，但没有统一的实时控制点。用户在角色回复时开口，前端最多能停止已经开始播放的音频，后端可能仍在继续生成上一轮文本，迟到的 TTS 结果也可能继续入队。

参考 OLV 后，我们确认 VAD 不应只是一个 `/api/vad/detect`。它应该在 WebSocket 实时音频链路中产生语义事件：

- `speech_start`：用户开始说话，立即打断。
- `speech_chunk`：用户仍在说话，继续收集音频。
- `speech_end`：用户说完，提交 ASR。
- `silence` / `error`：维持监听状态或返回错误。

## 问题

要把 VAD 接入 ATRI，核心问题有四个。

第一，实时性。按钮式 ASR 是录完后处理，不能在用户刚开口时触发控制动作。麦克风音频必须持续走 WebSocket 上行。

第二，打断对象不止播放器。只停前端音频不够，后端正在进行的 LLM generation 也要失效，否则旧文本和旧 complete 仍可能进入 UI 或历史。

第三，ASR 不能承担开始和结束判断。ASR 只负责把一整段用户语音转成文本；什么时候开始收集、什么时候结束、什么时候打断，都由 VAD 决定。

第四，被打断的半截回复要有明确语义。它可以展示和审计，但不能被当作普通完整 AI 回复写入记忆轮次。

## 方案

最终方案是一条以 WebSocket 为核心的实时控制链路：

```text
前端麦克风
  -> input:audio:chunk
  -> 后端 VAD
  -> speech_start
  -> control:interrupt
  -> 旧 generation 失效
  -> 前端停止并丢弃旧音频

speech_end
  -> 后端 ASR
  -> output:asr:transcript
  -> 后端自动启动新一轮聊天
```

消息命名沿用 ATRI 当前风格，不照搬 OLV：

- `input:audio:chunk`
- `input:audio:end`
- `control:listen-state`
- `control:interrupt`
- `output:asr:transcript`
- `output:chat:interrupted`

其中最关键的是 `generation_id`。`chat_id` 只能表示聊天窗口，不能表示某一次 LLM 生成是否仍然有效。每次文本输入或 ASR 自动提交都会创建新的 `generation_id`。当 VAD 检测到 `speech_start`，当前 generation 立即失效。

旧 generation 失效后：

- 后端取消当前聊天 task。
- 旧 chunk 不再发送。
- 旧 complete 不再发送。
- 旧普通持久化结果不再写入。
- 前端丢弃旧 generation 的自动 TTS 音频结果。

## 实现路径

第一步是扩展后端 WebSocket。后端开始识别音频消息，把 chunk 交给 VADService，并返回监听状态。聊天生成被放入后台 task，receive loop 因此可以在 LLM 输出期间继续处理音频。

第二步是新增前端实时语音入口。实时 VAD 使用独立开关，不替换原有麦克风按钮。开启后前端持续采集音频，重采样为 16 kHz、mono、PCM float array，通过 `input:audio:chunk` 即时发送。断线时不缓存旧音频，而是停止监听并释放麦克风。

第三步是接上 ASR。`speech_end` 后端把缓存音频转成 ASR 可接收的格式，调用后端 ASR provider。ASR 成功后，后端发送 `output:asr:transcript`，并自动把 transcript 作为用户输入进入新一轮聊天。前端只展示 transcript，不再次调用 `sendMessage()`。

第四步是处理打断语义。后端只累积已经发送给前端的 LLM chunk。发生打断时，如果这段文本非空，就发送：

```json
{
  "type": "output:chat:interrupted",
  "data": {
    "generation_id": "old generation id",
    "partial_reply": "已经发送给前端的半截回复",
    "interrupted": true,
    "reason": "vad_speech_start"
  }
}
```

这条半截回复会进入展示历史和 `chat_history` 审计归档，但不会进入 `recent_messages`，不会增加有效轮次，不触发短期记忆压缩，也不写入长期记忆。

第五步是治理前端状态归属。前端用 `chatId + characterId + generationId` 跟踪 active stream，旧会话、旧角色、旧 WebSocket 连接的事件不能影响当前页面。TTS 侧同时保留 generation tombstone 和播放级 `vadInterruptEpoch`，避免迟到事件误伤新的手动播放。

## 关键坑

### `chat_id` 不足以判断旧输出

同一个 chat 中可以连续产生多轮 LLM 回复。仅靠 `chat_id`，无法判断一个 chunk 属于当前回复还是上一轮被打断的回复。因此必须引入 `generation_id`。

### ASR transcript 不能让前端再发送一次

如果前端收到 `output:asr:transcript` 后调用 `sendMessage()`，就会把控制权重新分散到前端，并可能造成重复提交。最终采用后端自动提交，前端只展示 transcript。

### `partial_reply` 不能等同于用户听到的内容

第一版没有播放确认，也没有 TTS segment 回执。因此 `partial_reply` 只能定义为“后端已经发送给前端的文本”。它比完整模型输出更安全，但仍不等同于用户实际听到的语音内容。

因此本版明确不引入 `heard_response`。等后续 TTS 分段流式化和播放确认独立完成后，再评估是否需要 OLV 式回传。

### 旧 TTS 结果会迟到

REST TTS 请求已经发出后，不一定能 provider 级取消。解决方式是让前端按 generation 丢弃迟到结果：旧 generation 的自动 TTS 返回后直接释放，不入队、不播放。

### 多会话和旧连接会放大竞态

用户切换会话、切换角色或 WebSocket 重连时，旧事件仍可能晚到。前端最终拆分了 `connectionBusy` 和 `isCurrentChatStreaming`，并让 WebSocket manager 幂等化，销毁旧 manager、隔离旧 socket 回调、移除离线消息重放。

## 验收

M4 联调时，浏览器业务 `/ws` 中观察到关键顺序：

```text
input:audio:chunk
control:listen-state
control:interrupt
output:asr:transcript
output:chat:chunk
```

这证明链路已经从实时 VAD 进入 ASR，再由后端自动进入新一轮聊天。

M5 终端 WebSocket 抓包记录了更完整的打断闭环：

```text
interrupt_seen=True
chat_interrupted_seen=True
first_complete=False
stale_after_interrupt_count=0
second_complete=True
```

含义是：

- 第一轮 LLM 正在输出。
- VAD 检测到 `speech_start`。
- 旧 generation 被打断。
- 旧 generation 没有继续 complete。
- 打断后没有旧 chunk 泄漏。
- 第二轮新 generation 可以正常输出并完成。

记录过的主要自动检查包括：

```bash
uv run pytest tests/vad tests/routes/test_chat_ws.py tests/routes/test_asr.py -q
uv run pytest tests/routes/test_chat_ws.py tests/storage/test_json_storage.py tests/memory/test_manager.py -q
uv run python -m mypy src/ --ignore-missing-imports
uv run ruff check src/routes/chat_ws.py tests/routes/test_chat_ws.py
cd frontend
npm run type-check
npm run lint
npm run build
```

阶段记录中，后端全量测试曾达到 `432 passed, 4 deselected`，前端类型检查和构建通过，lint 仅保留既有 warning。

## 留下的边界

VAD 第一版完成边界是：

- 实时麦克风输入。
- 后端 VAD 判断。
- `speech_start` 打断 LLM 流式输出和当前 TTS 播放。
- `speech_end` 后端 ASR 自动接管。
- interrupted 历史、记忆和旧 TTS 结果治理。
- 配置和使用说明可查。

后续 TTS 分段流式化应作为独立 feature 推进。它可以继续遵守本次确定的边界：

- TTS 是 LLM 文本回复的下游消费者。
- 聊天历史和文本显示以 `output:chat:*` 为准。
- VAD `speech_start` 使旧 generation 失效。
- 前端丢弃旧 generation 音频。
- interrupted partial reply 第一版以已发送给前端文本为准。
- 在没有明确播放确认前，不引入 `heard_response`。
