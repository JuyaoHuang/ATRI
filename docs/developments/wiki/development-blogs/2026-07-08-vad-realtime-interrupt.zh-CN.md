---
status: accepted
owner: vad
created: 2026-07-08
updated: 2026-07-09
source:
  - docs/developments/features/2026-06-vad-realtime-interrupt/README.zh-CN.md
  - docs/developments/features/2026-06-vad-realtime-interrupt/dev-log.zh-CN.md
  - docs/developments/modules/vad/design.zh-CN.md
  - docs/developments/modules/vad/architecture.zh-CN.md
  - docs/developments/modules/vad/realtime-interrupt-boundary.zh-CN.md
  - docs/developments/modules/asr/README.zh-CN.md
  - docs/developments/modules/tts/README.zh-CN.md
  - src/routes/chat_ws.py
related_code:
  - src/vad/
  - src/asr/
  - src/routes/chat_ws.py
  - frontend/src/components/chat/
  - frontend/src/composables/
---

# ATRI VAD 实时打断开发复盘

ATRI 很早就具备语音输入和语音播报能力，但那还不等于自然的语音对话。按钮式 ASR 可以把录音转成文字，TTS 可以把 AI 回复读出来，聊天 WebSocket 可以把文本流式送到前端。问题在于，当角色正在说话时，用户突然插话，系统不能只在播放层停一下声音；它还必须让后端正在生成的旧回复失效，把控制权切回用户，并保证旧文本、旧音频、旧持久化副作用都不会继续污染当前会话。

这次 VAD 实时打断 feature 的核心价值，就是把“用户开始说话”从一个事后转写结果，提升为实时对话链路中的控制事件。本文面向 GitHub Wiki 读者，整理这次 feature 的设计动机、协议语义、实现落点、状态归属和验收结论，不机械搬运 M 阶段流水，也不把后续 TTS 分段流式化混进 VAD 第一版的能力范围。

## 背景

旧链路可以概括为三条相对独立的能力：

```text
按钮式 ASR：录音结束 -> 上传音频 -> 转写文本
聊天 WebSocket：输入文本 -> LLM 流式输出文本
TTS 播放：完整回复文本 -> 合成音频 -> 前端播放
```

这套组合能支撑“我说一句，系统识别一句，AI 回答一句，再读出来”。但它缺少一个统一的实时控制点。用户在 AI 播报中途开口时，前端最多能停止当前播放器；后端的 LLM task 可能仍在继续吐出旧 chunk，旧 `complete` 可能稍后抵达，已经发起的 TTS 请求也可能在打断之后才返回音频。

如果系统只把 VAD 理解成“给一段音频返回有没有人声”，那它最多是一个检测工具，无法解决对话控制问题。ATRI 这次真正需要的是一个实时音频控制层：持续接收麦克风 chunk，稳定判断 `speech_start` 和 `speech_end`，再由聊天 WebSocket 把这些事件翻译成打断、转写和新一轮聊天。

因此，VAD 在当前 ATRI 里不是独立 REST 子系统，也不是 ASR 的替代品。它处在实时语音模式的上游控制位置：

```text
frontend realtime audio
  -> input:audio:chunk
  -> VADService / VADSession / provider
  -> VADEvent
  -> chat_ws orchestration
  -> interrupt / ASR handoff / new generation
```

## 旧链路问题

旧链路最大的问题不是缺少模型，而是状态边界不够清楚。语音对话里同一秒可能同时发生三件事：AI 正在生成文本，TTS 正在播放旧文本，用户又开始说话。如果没有统一的 generation 生命周期，系统很难判断哪些输出仍然有效。

第一，按钮式 ASR 的时机太晚。它通常在录音结束后才上传音频并拿到文本，而打断必须发生在用户刚开口的时候。`speech_start` 必须先于 ASR 转写触发，否则用户已经说了一段，角色还在继续说旧回复。

第二，播放器停止不等于后端打断。前端停止播放只能解决“我现在听不到旧音频”，但旧 LLM task 仍可能继续发送 `output:chat:chunk`，最后再发送 `output:chat:complete`。如果这些事件没有被后端和前端共同识别为旧 generation，它们就可能落进 UI、历史或记忆。

第三，ASR 不应该负责裁决语音起止。ASR 的职责是把一段完整语音转成文本；它不应该决定什么时候开始缓存音频、什么时候终止当前 AI 回复、什么时候把音频交给转写。这些都属于 VAD 事件和 WebSocket 编排层。

第四，被打断的半截回复需要独立语义。它既不能完全丢掉，因为用户和开发者需要知道 AI 曾经说到哪里；也不能当成普通完整回复进入记忆轮次，因为它不是一次完成的 AI 回答。这个边界后来沉淀为 `output:chat:interrupted` 和 `interrupted=true` 的审计历史。

第五，多会话和多角色会放大竞态。用户可能切换聊天、切换角色、重连 WebSocket，旧连接里的迟到事件不能误写当前页面。只靠 `chat_id` 不够，因为同一个 chat 里可以连续产生多轮回复，甚至旧回复和新回复都属于同一个窗口。

## 方案

最终方案是把 VAD 放进聊天 WebSocket，而不是另开一条“先检测再提交”的 REST 主路径。WebSocket 本来就承载文本流式输出，它也最适合承载实时音频控制事件。

主链路如下：

```text
前端麦克风
  -> input:audio:chunk
  -> 后端 VAD
  -> control:listen-state(speech_start)
  -> control:interrupt
  -> 旧 generation 失效
  -> 前端停止播放并丢弃旧音频

speech_end
  -> 后端取出本轮音频缓存
  -> ASRService.transcribe_audio()
  -> output:asr:transcript
  -> 后端自动启动新一轮聊天
  -> output:chat:chunk / output:chat:complete
```

这条链路里有三个关键取舍。

第一，VAD 只产生稳定语义事件，不直接拥有聊天、TTS 或记忆。`src/vad/` 内部通过 Provider、factory、config、session、service 分层，把原始检测结果整理成 `speech_start`、`speech_chunk`、`speech_end`、`silence`、`error`。真正把这些事件翻译成“取消聊天 task”“停止 TTS”“交给 ASR”的，是 `src/routes/chat_ws.py`。

第二，`speech_start` 是打断点，`speech_end` 是 ASR 接管点。这两个事件不能互相替代。`speech_start` 不等待 ASR 文本，它只说明用户开始说话，因此要立即打断旧输出；`speech_end` 才说明本轮用户语音可以被取出并交给 ASR。

第三，所有输出都围绕 `generation_id` 做有效性判断。`chat_id` 表示聊天窗口，`character_id` 表示角色归属，`generation_id` 才表示某一次 LLM/TTS 输出生命周期。每次文本输入或 ASR 自动提交都会创建新的 generation；VAD 打断会让旧 generation 失效。

## 协议

VAD 第一版稳定下来的消息不是单一事件，而是一组前后端契约。

| 消息 | 方向 | 职责 |
| --- | --- | --- |
| `input:audio:chunk` | 前端 -> 后端 | 发送实时麦克风片段。当前约定是 16 kHz、mono、PCM float array 风格的 `number[]`。 |
| `input:audio:end` | 前端 -> 后端 | 用户主动停止本次实时监听，重置 VAD session 和音频缓存，用于 UI 收口。它不自动触发 ASR。 |
| `control:listen-state` | 后端 -> 前端 | 报告 VAD 稳定事件，包括 `speech_start`、`speech_chunk`、`speech_end`、`silence` 和 `error`。 |
| `control:interrupt` | 后端 -> 前端 | 表示用户已经开始说话，当前播放和旧 generation 应立即失效。 |
| `output:chat:interrupted` | 后端 -> 前端 | 表示旧 generation 已被打断，并返回后端已经发给前端的半截文本。 |
| `output:asr:transcript` | 后端 -> 前端 | 表示 `speech_end` 后端 ASR 转写成功，前端只展示，不再次提交。 |
| `output:chat:chunk` / `output:chat:complete` | 后端 -> 前端 | 新 generation 的普通聊天文本输出，均携带 `generation_id`。 |

### `speech_start`

`speech_start` 是实时打断链路里最重要的事件。一旦 VAD session 把连续 chunk 判定为说话开始，`chat_ws` 会做一组同步的控制动作：

1. 从 `pre_buffer` 开始构造本轮 `audio_buffer`，避免吞掉句首。
2. 发送 `control:listen-state`，其中 `state=speech_start`。
3. 如果本轮 speaking burst 还没发过 interrupt，则发送一次 `control:interrupt`。
4. 读取并清空当前 generation 的 partial reply 跟踪。
5. 使当前 `generation_id` 失效。
6. 取消当前 `current_chat_task`。
7. 中断当前 TTS generation，使旧 `output:audio:*` 结果可以被丢弃。
8. 如果已经有可见 partial reply，则持久化 interrupted 审计历史，并发送 `output:chat:interrupted`。

这里有两个细节很容易误解。

`control:interrupt` 是控制事件，不是聊天结果。它的职责是让前端立即停止播放、标记旧 generation 失效，并把用户正在说话这件事反馈到 UI。它可以携带 `generation_id`，表示具体哪个 chat 或 TTS generation 被打断；如果没有可绑定的 generation，它仍然代表一次真实的播放级打断。

`output:chat:interrupted` 是结果事件。它不负责再次停止播放器，只负责把“旧 generation 被打断后，后端已经发给前端的文本是什么”交代清楚。它的 `reason` 当前为 `vad_speech_start`，`interrupted=true`，并携带旧 generation 的 `generation_id`。

### `speech_chunk`

`speech_chunk` 表示用户仍在同一轮 speaking burst 中。此时音频继续追加到 `audio_buffer`，但不会重复发送 `control:interrupt`。这条规则保证同一轮连续说话只触发一次打断，避免前端反复清空播放队列或反复制造 interrupted 消息。

### `speech_end`

`speech_end` 是 ASR 接管点。它成立后，后端会：

1. 发送 `control:listen-state`，其中 `state=speech_end`。
2. 清空 `pre_buffer`。
3. 取出并清空当前 `audio_buffer`。
4. 重置 `interrupt_sent=false`，允许下一轮说话再次打断。
5. 检查音频是否为空，或是否短于 `min_speech_ms`。
6. 将 float PCM 样本编码成 `realtime-vad.wav`。
7. 调用 `ASRService.transcribe_audio()`。
8. ASR 成功后发送 `output:asr:transcript`。
9. 后端用同一个 transcript 自动启动新一轮聊天，并为它绑定新的 `generation_id`。

`output:asr:transcript` 的职责是展示和交接。它携带的 `generation_id` 是后端即将用于新一轮聊天的 generation。前端收到它以后不应该再调用一次 `sendMessage()`，否则会把同一段用户语音重复提交。

### `input:audio:end`

`input:audio:end` 和 VAD 事件里的 `speech_end` 名字相近，但职责不同。

`input:audio:end` 是前端主动告诉后端“这次实时监听结束了”。当前实现会重置 VAD session、清空 `audio_buffer` 和 `pre_buffer`，并发送一个 `speech_end` 风格的 listen-state 让 UI 收口。但它不会自动把缓存音频交给 ASR。真正进入 ASR 的路径必须来自 VAD session 产出的 `speech_end` 事件。

这个设计避免了一个风险：用户点击关闭实时监听时，系统不应把任意残留缓冲都当作一句完整语音提交。

## `generation_id`

这次 feature 最关键的设计点是引入并贯彻 `generation_id`。

`chat_id` 只能说明“这是哪个聊天窗口”。同一个聊天窗口里可能先后产生多轮 AI 回复，旧 generation 可能还在路上，新 generation 已经开始。仅靠 `chat_id`，前端和后端都无法判断某个 `chunk`、`complete` 或音频结果是否仍然有效。

`generation_id` 代表一次 LLM 回复生命周期，也被 TTS 下游沿用为音频生命周期标识。它的职责包括：

- 标记 `output:chat:chunk` 和 `output:chat:complete` 属于哪次回复。
- 标记 `output:asr:transcript` 即将启动哪次后端自动聊天。
- 让 `control:interrupt` 指向被打断的旧 generation。
- 让后端在发送 chunk、发送 complete、写入普通历史和提交记忆前检查 generation 是否仍 active。
- 让前端丢弃旧 generation 的自动 TTS 音频结果。
- 让 interrupted 审计历史能追溯到被打断的具体回复。

`src/routes/chat_ws.py` 里的 `WebSocketVADState` 维护了这组连接态：`current_generation_id`、`current_generation_chat_id`、`current_generation_character_id`、`current_generation_user_text`、`current_generation_reply_chunks`、`current_tts_generation_id` 和 `current_tts_manager`。这不是 VAD 模块本体的状态，而是聊天 WebSocket 为了编排 VAD、LLM、ASR、TTS 而拥有的连接级状态。

当 `speech_start` 到来时，后端会先从 `current_generation_reply_chunks` 中拿到已经发送给前端的文本，构造 interrupted snapshot，然后让 `current_generation_id` 失效。后续旧 task 如果继续执行，`_send_generation_chunk()` 和 `_send_generation_complete()` 会在发送前检查 generation 是否仍 active，不 active 就直接丢弃。

普通完成路径也有相同防线。完整回复在写入普通历史、提交记忆和发送 `output:chat:complete` 前都会重新检查 generation。如果打断发生在这些步骤之间，旧 generation 的普通完成副作用也会被阻断。

## 关键实现

### VAD 模块分层

VAD 模块本体保持了比较窄的职责。Provider 返回的是原始 `VADResult`，包括 `is_speech`、`probability`、`energy` 和 `metadata`。`VADSession` 再把连续 chunk 的原始结果防抖成稳定 `VADEvent`。

当前两个 Provider 的现实也影响了实现边界：

- `fake` provider 基于 chunk 能量阈值做原始判断，主要依赖 session 层的 `required_hits` 和 `required_misses` 防抖。
- `silero_vad` provider 已经落地主链路，它内部包含 32 ms 窗口、概率/分贝平滑和 hits/misses，因此 service 层会让 session 外层退化为 1/1，避免重复防抖。

这个拆分的意义在于，上层业务永远消费 `speech_start`、`speech_chunk`、`speech_end` 这样的稳定语义，而不是直接依赖某个模型的概率波动。

### WebSocket 接收循环

为了让“AI 说话时用户可以插话”成立，后端不能在 LLM 流式输出期间阻塞 WebSocket receive loop。当前做法是把聊天处理放进后台 task，由 `current_chat_task` 跟踪。主循环继续接收 `input:audio:chunk`，实时交给 `VADService.process_audio()`。

发送侧也做了串行化。`websocket.state.send_lock` 用于避免聊天 task 和控制路径同时写 WebSocket，`_send_speech_start_interrupt()` 会在锁内完成 generation snapshot、generation invalidation、chat task cancel、TTS interrupt 和 `control:interrupt` 发送。这样可以减少“旧 chunk 刚好和 interrupt 交叉发送”的竞态。

### 音频缓冲

实时音频链路维护两类缓冲：

- `pre_buffer`：在 `speech_start` 前滚动保留一小段音频，由 `pre_buffer_ms` 控制，用来补回句首。
- `audio_buffer`：从 `speech_start` 开始积累本轮 speaking burst，直到 `speech_end` 后交给 ASR。

当 VAD 返回 `speech_start`，`audio_buffer` 会优先从 `pre_buffer` 开始；返回 `speech_chunk` 时继续追加当前 chunk；返回 `speech_end` 时取出完整 buffer 并清空。VAD 处理失败、`input:audio:end` 和 WebSocket close 都会清理这些缓冲。

### ASR 接管

ASR 仍然是独立模块。VAD 不做转写，`chat_ws` 只在 `speech_end` 后把缓存音频编码成 WAV，并调用 `ASRService.transcribe_audio()`。如果后端 ASR 不可用、配置错误、转写失败、返回空文本或音频太短，后端通过 `control:listen-state(state=error, code=..., message=...)` 通知前端，而不是关闭整个聊天 WebSocket。

这也解释了 Web Speech API 的边界。它可以是浏览器侧 ASR 或降级能力，但不是 VAD model，也不是这条后端 VAD 自动提交链路里的 backend ASR provider。

### interrupted 历史和记忆

被打断的 partial reply 只来自“后端已经通过 WebSocket 发给前端的文本”。它不包含模型可能已经生成但尚未发给前端的内容，也不声称等于用户实际听到的 TTS 内容。

发生打断时，如果 partial reply 非空，后端会发送：

```json
{
  "type": "output:chat:interrupted",
  "data": {
    "chat_id": "chat id",
    "character_id": "atri",
    "generation_id": "old generation id",
    "partial_reply": "已经发送给前端的半截回复",
    "interrupted": true,
    "reason": "vad_speech_start"
  }
}
```

这条消息可展示、可审计，但不是普通完整 AI 轮次。存储层会记录 `metadata.generation_id`、`interrupted=true` 和 `interrupt_reason`。记忆系统会跳过 interrupted AI 消息，不把它加入普通 `recent_messages`，不增加有效轮次，不触发短期记忆压缩，也不写入长期记忆。

第一版刻意没有引入 `heard_response`。在没有播放确认和 TTS 回执的情况下，系统只能可靠知道“哪些文本已经发给前端”，不能可靠知道“用户实际听到了哪些音频”。

### TTS 下游失效

VAD 不决定 TTS 用什么 Provider，也不要求 Provider 提供原生 `synthesize_stream()`。VAD 和 TTS 的交界只有 generation 生命周期：`speech_start` 让旧 TTS generation 失效，旧自动音频结果必须可丢弃。

在 VAD 第一版里，这个边界主要用于处理 REST TTS 迟到结果：请求已经发出后未必能在 Provider 层取消，但前端可以按 generation 丢弃旧自动音频。后续 TTS 分段流式化作为独立 feature 接入后，也沿用这条边界：`output:audio:segment`、`output:audio:complete`、`output:audio:error` 都携带 `generation_id`，发送和播放时都要检查是否仍 active。

这不是 VAD feature 夸大了 TTS 能力，而是把跨模块的生命周期约束固定下来。

### 错误恢复

VAD provider 不可用、配置错误或处理失败时，后端不会关闭聊天 WebSocket。它会发送 `control:listen-state(state=error)`，清空音频缓冲，重置 VAD session，并保持文本聊天可继续使用。

WebSocket close 时，后端会中断当前 TTS generation，释放连接态，并调用 `vad_service.reset_session(session_id)`。VAD session 不跨连接保留。

## 状态归属

实时打断最容易出错的地方，是“谁拥有哪段状态”。这次 feature 后期专门补了一轮状态归属和竞态治理。

后端的归属原则是：`src/vad/` 只拥有音频语义状态，`chat_ws` 拥有连接编排状态。VAD session 可以判断当前连接上的说话状态，但它不知道聊天 task、TTS manager、storage 或 memory。`WebSocketVADState` 才跟踪当前 generation、当前聊天 task、当前 TTS generation、pre-buffer、audio buffer、最近的 chat 和 character。

前端的归属原则是：当前 UI 只相信匹配当前 `chatId + characterId + generationId` 的流。后续补丁中，前端 chat store 增加了 `activeStream`，用于跟踪当前输出；增加 `pendingInterruptedStream`，处理 `control:interrupt` 先到、`output:chat:interrupted` 后到的情况；拆分 `connectionBusy` 和 `isCurrentChatStreaming`，避免“连接忙”和“当前聊天正在流式输出”混成一个状态。

WebSocket manager 也做了幂等化和隔离。旧 manager 会被销毁，旧 socket 回调不能继续写当前 UI；离线消息队列被移除，避免重放过期聊天消息或实时音频；实时麦克风启动增加 run id，防止过期异步初始化重新占用音频资源。

TTS 侧也区分了两类状态。`control:interrupt` 是播放级打断，会停止当前播放、递增播放 epoch，并把相关 generation 标记为旧结果。`output:chat:interrupted` 只是文本结果事件，不应该再次制造新的播放级打断。这个区分可以避免同一次打断在前端被处理两遍。

这些状态归属规则共同保证了一个目标：旧连接、旧会话、旧角色、旧 generation 的迟到事件不会误伤当前页面。

## 验收

这次 feature 的验收重点不是“提交了哪些 commit”，而是实时闭环是否成立、旧结果是否被挡住、异常是否能收口。

浏览器联调中，业务 `/ws` 观察到的关键顺序是：

```text
output:chat:complete
input:audio:chunk
control:listen-state
control:interrupt
output:asr:transcript
output:chat:chunk
```

这说明链路已经从实时音频进入 VAD，再由 `speech_end` 进入 ASR，最后由后端自动启动新一轮聊天。它不是按钮式 ASR 的复用，也不是前端收到 transcript 后再手动提交。

打断场景的终端 WebSocket 抓包记录过下面这组结果：

```text
interrupt_seen=True
chat_interrupted_seen=True
first_complete=False
stale_after_interrupt_count=0
second_complete=True
```

它对应五个关键结论：

- 第一轮 LLM 回复已经开始流式输出。
- VAD 的 `speech_start` 可以在转写完成前立即触发打断。
- 旧 generation 没有继续发送 `complete`。
- 打断后没有旧 generation chunk 泄漏到前端。
- ASR 接管后的第二轮 generation 可以正常流式输出并完成。

自动检查覆盖了多个层面：

- `tests/routes/test_chat_ws.py` 覆盖聊天 WebSocket、generation 失效、打断消息和 ASR 接管。
- `tests/vad` 覆盖 VAD service/session/provider 边界。
- `tests/routes/test_asr.py` 覆盖后端 ASR 转写入口。
- `tests/storage/test_json_storage.py` 和 `tests/memory/test_manager.py` 覆盖 interrupted 历史与记忆跳过语义。
- 前端 `type-check`、`lint`、`build` 覆盖实时麦克风、WebSocket 状态和 audio player 相关改动。

阶段记录中，全量后端测试最终达到 `432 passed, 4 deselected`，`mypy` 和 `ruff` 通过；前端类型检查、构建和 lint 通过，lint 仅保留既有 warning。对 Wiki 读者来说，重要的不是这些数字本身，而是它们支撑了三条行为承诺：能打断、旧结果不泄漏、能从 ASR 自动进入新一轮聊天。

## 边界与后续

VAD 第一版稳定下来的边界如下：

- `speech_start` 是打断点，不等待 ASR 文本。
- `speech_end` 是 ASR 接管点，负责把完整 speaking burst 交给后端 ASR。
- `input:audio:end` 是前端停止监听的收口消息，不自动触发 ASR。
- `generation_id` 是旧文本、旧音频、旧 complete、旧持久化副作用能否继续生效的判断基础。
- `control:interrupt` 是播放级和 generation 级控制事件。
- `output:chat:interrupted` 是旧 generation 的半截文本结果事件。
- `output:asr:transcript` 是展示和后端自动提交的交接事件，前端不再重复提交。
- interrupted partial reply 以“后端已经发给前端的文本”为准，不等同于“用户实际听到的 TTS 内容”。
- TTS 是 LLM 文本回复的下游消费者，VAD 只约束旧 generation 音频可丢弃。

同样明确不在本版范围内的事情包括：

- 不提供独立的 VAD REST `/api/vad/detect` 主路径。
- 不把 Web Speech API 当作 VAD model。
- 不引入前端 `heard_response` 回传。
- 不要求 TTS Provider 原生支持 `synthesize_stream()`。
- 不把 TTS 分段流式化并入 VAD MVP。
- 不把 interrupted AI 消息当作普通完整 AI 轮次写入记忆。

后续可以继续推进的方向有三类。

第一类是采集质量。当前前端实时采集仍使用 `ScriptProcessorNode`，后续可以迁移到 `AudioWorklet`，降低浏览器弃用风险并改善实时音频稳定性。

第二类是播放确认。如果未来要精确记录“用户实际听到了多少”，需要 TTS 播放层提供可靠回执，再评估是否引入类似 `heard_response` 的能力。在那之前，`partial_reply` 只能保持“已发送给前端文本”的定义。

第三类是更细的跨模块体验。TTS 分段流式化、自动播放策略、错误提示和多设备麦克风体验都可以继续增强，但它们应继续遵守这次沉淀的核心约束：聊天文本以 `output:chat:*` 为准，打断由 VAD 的 `speech_start` 驱动，旧 generation 的文本与音频都必须可判定、可丢弃、可审计。
