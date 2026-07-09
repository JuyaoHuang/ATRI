---
status: accepted
owner: vad
created: 2026-06-15
updated: 2026-07-08
source:
  - docs/developments/wiki/VAD/development.md
  - docs/developments/wiki/VAD/vad-implementation-plan.md
related_code:
  - src/vad/
  - src/asr/
  - src/routes/chat_ws.py
  - frontend/src/components/chat/
  - frontend/src/composables/
---

# VAD 实时打断开发日志

本文从旧的 `docs/developments/wiki/VAD/development.md` 重组而来，只保留可追溯的开发事实、阶段决策、问题修正和验收结果。临时流水、重复说明和与 VAD MVP 无关的大段 TTS 流式化记录不再机械复制。

## 取舍口径

- 保留：每个阶段的目标、已完成行为、对外协议、关键边界、自动检查和人工验收结论。
- 合并：同一阶段里重复出现的背景说明、文件清单和测试命令，只保留能支撑追溯的版本。
- 删减：临时调试手段、长篇过程描述、已被后续阶段覆盖的中间说法。
- 不迁入：2026-07-08 的 TTS 分段流式化流水。这里只保留与 VAD 有关的结论：TTS 是 LLM 文本回复的下游消费者，旧 generation 音频必须可丢弃，TTS 流式化属于后续独立 feature。
- 不补造：旧日志没有单独 M1 开发条目，因此本日志不凭实施计划倒推出虚构阶段，只在 M4/M6 记录真实落地的 `silero_vad`、配置和验证结果。

## 阶段总览

| 阶段 | 日期 | 结果 |
|---|---|---|
| M0 范围冻结 | 2026-06-15 | 明确 VAD 是实时控制链路，不做 REST VAD 主路径 |
| M2 WebSocket 控制层 | 2026-06-15 到 2026-06-17 | 定义并实现音频 chunk、监听状态和 interrupt 协议 |
| M3 前端实时麦克风 | 2026-06-17 | 新增独立实时 VAD 开关和音频上行链路 |
| M4 VAD 到 ASR | 2026-06-18 | 引入 `generation_id`，完成 `speech_end -> ASR -> 自动聊天` |
| M5 打断语义治理 | 2026-06-19 | 保存 interrupted 半截回复，并让记忆和 TTS 跳过旧副作用 |
| M6 文档收尾 | 2026-06-19 | 补齐配置、使用说明和人工验收入口 |
| 状态归属补丁 | 2026-06-19 | 治理多会话、多角色和旧 WebSocket 事件竞态 |

## M0：文档与范围冻结

### 完成

- 明确 ATRI 原有语音链路由三条相对独立的链路组成：按钮式 ASR、聊天 WebSocket 文本流、REST TTS 播放。
- 明确 VAD 的职责不是判断单段音频是否有人声，而是在实时音频流中产生控制事件。
- 明确第一版采用“WebSocket 麦克风输入 + 后端 VAD + 前端停止播放 + 后端取消 LLM”的路线。
- 明确第一版保留 REST TTS，不要求 TTS provider 原生流式输出。
- 明确不复用 OLV 的 WebSocket 外壳和 sentinel bytes，只复用状态机、防抖、pre-buffer 和打断思路。

### 关键边界

- `speech_start` 不等待 ASR 文本，立即触发打断。
- `speech_end` 才把完整语音片段交给 ASR。
- Web Speech API 是浏览器侧 ASR 或降级能力，不是 VAD model。
- VAD 模块以 provider/factory/service/session 形式接入，不把模型细节写进聊天 route。

## M2：WebSocket 协议与后端控制层

### 协议草案

M2 先确定同一聊天 WebSocket 中的消息边界：

- `input:audio:chunk`：前端发送 16 kHz、mono、PCM float array 音频片段。
- `input:audio:end`：前端通知本轮实时音频输入结束。
- `control:listen-state`：后端返回 `speech_start`、`speech_chunk`、`speech_end`、`silence` 或 `error`。
- `control:interrupt`：后端通知用户已开始说话，前端应立即停止播放。
- `output:asr:transcript`：M2 只预留协议，真实 ASR 接入属于 M4。

`control:interrupt` 的 `generation_id` 是条件字段。存在时表示本次 `speech_start` 实际使某个 LLM generation 失效；不存在时只表示播放级打断和用户开始说话。

### 实现

- `src/routes/chat_ws.py` 增加音频消息分发。
- 每个 WebSocket 连接维护 VAD session、音频缓存、聊天 task 引用和发送锁。
- 文字聊天处理调整为后台 task，使 receive loop 在 LLM 输出期间仍能接收音频。
- `speech_start` 时发送 `control:interrupt`，并确保同一轮连续说话只发送一次。
- `input:audio:end` 可重置监听状态并清理音频缓存。

### 验证

```bash
uv run pytest tests/routes/test_chat_ws.py -q
uv run pytest tests/ -q
uv run ruff format src/routes/chat_ws.py tests/routes/test_chat_ws.py
uv run ruff check . --fix
uv run python -m mypy src/ --ignore-missing-imports
```

记录结果：

- `tests/routes/test_chat_ws.py`：14 passed。
- 全量 `tests/`：391 passed, 4 deselected。
- ruff 和 mypy 通过。

### 遗留

- M2 不做前端麦克风采集。
- M2 不做真实 ASR。
- M2 不真正取消 LLM task。
- M2 不写入 `chat_history interrupted=true`。
- M2 不接入真实 Silero 推理。

## M3：前端实时麦克风输入

### 完成

- 新增独立实时 VAD 开关，位于 `InputBox.vue` 的工具区，紧邻原有 `VoiceInput`。
- 新增实时语音输入 composable，通过浏览器麦克风和 `AudioContext` 获取音频。
- 将音频转换为 16 kHz、mono、PCM float array，并按序发送 `input:audio:chunk`。
- 停止监听时发送 `input:audio:end`。
- WebSocket 断开时立即停止监听并释放麦克风，不缓存过期音频。
- 前端识别 `control:interrupt`、`control:listen-state` 和 `output:asr:transcript`。
- 收到 interrupt 后调用 audio player 的 stop 能力，停止当前 TTS 播放并清空队列。

### 决策

- 不复用按钮式 ASR 的 `VoiceInput`，避免混淆“一次性录音识别”和“持续实时 VAD”。
- 实时音频只在 WebSocket 已连接时发送，绕开普通离线消息队列。
- WebSocket 重连后不自动恢复监听，由用户手动重新开启。
- 原有按钮式 ASR、MediaRecorder 路径和 stop button 保持可用。

### 验证

```bash
cd frontend
npm run type-check
npm run lint
npm run build
```

记录结果：

- type-check 通过。
- build 通过。
- lint 通过，保留既有 `TransitionVertical.vue` 中的 `no-explicit-any` warning。
- 浏览器手动联调确认开启后持续发送 `input:audio:chunk`，关闭时发送 `input:audio:end`。

### 遗留

- 当前实时采集使用 `ScriptProcessorNode`，存在弃用警告；迁移 `AudioWorklet` 留给后续优化。
- M3 不负责 speech_end 后自动 ASR，不负责取消后端 LLM task。

## M4：VAD 到 ASR 的衔接

### 完成

- 引入 `generation_id`，每次文字输入或 ASR 自动提交聊天都会创建新的 generation。
- `output:chat:chunk`、`output:chat:complete` 和 `output:asr:transcript` 均携带 `generation_id`。
- `speech_start` 到来时发送 `control:interrupt`，取消当前 `current_chat_task`，并使旧 generation 失效。
- 旧 generation 的 chunk、complete 和普通持久化结果在发送或写入前被丢弃。
- `speech_start` 后开始缓存有效音频，并保留 `pre_buffer_ms` 避免吞掉句首。
- `speech_end` 后把缓存音频转成 WAV 字节，调用后端 ASR service。
- ASR 成功后发送 `output:asr:transcript`，并由后端自动用 transcript 启动新一轮聊天。
- 接入 `sherpa_onnx_asr` 后端 provider 与 `silero_vad` provider。
- `web_speech_api` 场景下保留 VAD 打断，但后端自动 ASR 返回明确错误。

### 核心决策

- `chat_id` 只表示聊天窗口，不能判断某一次 LLM 生成是否有效。
- `generation_id` 是打断、旧结果丢弃和前端音频失效的基础。
- `output:asr:transcript` 是展示事件，前端不能再调用 `sendMessage()`，否则会重复提交。

### 验证

```bash
uv run pytest tests/routes/test_asr.py tests/routes/test_chat_ws.py -q
uv run pytest tests/ -q
uv run ruff check src/asr src/app.py src/routes/chat_ws.py tests/routes/test_asr.py tests/routes/test_chat_ws.py
uv run python -m mypy src/asr src/app.py src/routes/chat_ws.py --ignore-missing-imports
```

记录结果：

- `tests/routes/test_asr.py tests/routes/test_chat_ws.py`：51 passed。
- 全量 `tests/`：420 passed, 4 deselected。
- ruff 和 mypy 通过。
- 前端 type-check、lint、build 通过。

### 浏览器联调

DevTools 的业务 `/ws` 消息顺序记录为：

```text
output:chat:complete
input:audio:chunk
control:listen-state
control:interrupt
output:asr:transcript
output:chat:chunk
```

该顺序证明本阶段打通了 `VAD -> ASR -> 后端自动聊天` 闭环，而不是传统按钮式 ASR 或手动文字输入。

## M5：打断语义与副作用治理

### 完成

- 每个 generation 累积已经发送给前端的 LLM chunk。
- VAD `speech_start` 使旧 generation 失效时，如果 partial buffer 非空，发送 `output:chat:interrupted`。
- `partial_reply` 只来自后端已经通过 WebSocket 发送给前端的文本，不包含尚未对前端可见的模型输出。
- 前端将 interrupted 回复收束成一条 AI 消息，并显示打断标记。
- `chat_history` 审计归档保存 `generation_id`、`interrupted=true` 和 `interrupt_reason`。
- 记忆系统跳过 interrupted AI 消息：不进入 `recent_messages`，不增加有效轮次，不触发短期记忆压缩，不写入长期记忆。
- 前端 audio player 按 `generation_id` 丢弃旧自动 TTS 结果。
- 旧 REST TTS 请求即使稍后返回，也不会入队播放已失效 generation 的音频。

### 核心决策

- 第一版不引入 OLV 式 `heard_response`。
- `partial_reply` 表示“后端已发送给前端的文本”，不强行等同于“用户实际听到的 TTS 文本”。
- interrupted 消息可展示、可审计，但不是普通完整 AI 轮次。

### 协议

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

### 验证

终端 WebSocket 抓包验证：

```text
interrupt_seen=True
chat_interrupted_seen=True
first_complete=False
stale_after_interrupt_count=0
second_complete=True
```

关键结果：

- 第一轮 LLM 文本已开始流式输出。
- VAD `speech_start` 打断了正在输出的 generation。
- 旧 generation 没有继续发送 complete。
- 打断后没有旧 generation chunk 泄漏。
- 第二轮新 generation 可以正常流式输出并 complete。

自动检查：

```bash
uv run pytest tests/routes/test_chat_ws.py tests/storage/test_json_storage.py tests/memory/test_manager.py -q
uv run python -m mypy src/ --ignore-missing-imports
uv run ruff check src/memory/chat_history.py src/memory/manager.py src/routes/chat_ws.py src/routes/chats.py src/storage/db_storage.py src/storage/interface.py src/storage/json_storage.py tests/memory/test_manager.py tests/routes/test_chat_ws.py tests/storage/test_json_storage.py
```

记录结果：

- 相关后端测试：122 passed。
- mypy 和 ruff 通过。
- 前端 type-check、lint、build 通过，lint 保留既有 warning。

## M6：配置与使用文档补齐

### 完成

- 新增 VAD 配置说明，解释 `enabled`、`vad_model`、`sample_rate`、`pre_buffer_ms`、fake provider 和 `silero_vad` provider。
- 新增实时语音模式使用说明，区分传统按钮式 ASR 和实时 VAD button。
- 记录 `web_speech_api`、`sherpa_onnx_asr`、`silero_vad` 在闭环中的边界。
- 记录 Silero 32 ms 内部窗口、防抖和静默结束延时的计算方式。
- 明确本轮不更新 `tests/*/test-exe.md`，现有测试入口记录在配置文档、使用说明和本日志中。

### 验证入口

后端：

```bash
uv run pytest tests/vad tests/routes/test_chat_ws.py tests/routes/test_asr.py -q
```

前端：

```bash
cd frontend
npm run type-check
npm run lint
npm run build
```

## 状态归属与竞态治理

### 背景

M0-M6 完成后，review 重点转向多会话、多角色、页面切换和异步 WebSocket 事件的归属问题。旧 WebSocket 连接、旧聊天或旧角色的事件不能误写当前 UI。

### 完成

- 前端 chat store 新增 `activeStream`，用 `chatId + characterId + generationId` 跟踪当前流。
- 新增 `pendingInterruptedStream`，处理 `control:interrupt` 先到、`output:chat:interrupted` 后到的顺序。
- 拆分 `connectionBusy` 和 `isCurrentChatStreaming`。
- WebSocket manager 幂等化，销毁旧 manager，并隔离旧 socket 回调。
- 移除离线消息队列，不再重放过期聊天消息或实时音频。
- 实时麦克风启动增加 run id，避免过期异步初始化重新占用音频资源。
- `chat:error` 只影响匹配中的 active stream。
- TTS 打断分为播放级 `vadInterruptEpoch` 和 generation tombstone。
- 后端普通 AI 历史写入补齐 `metadata.generation_id`。

### 边界

- `control:interrupt` 代表真实播放级 VAD 打断，会停止播放、递增 epoch、标记 generation。
- `output:chat:interrupted` 只说明某个 generation 已被打断，不应再次制造新的播放级打断。
- 没有正在跟踪的 LLM generation 时，后端仍可发送 VAD interrupt；前端按播放级打断兜底。
- TTS 流式化不并入 VAD MVP，后续单独建分支和设计文档。

### 验证

```bash
cd frontend
npm run type-check
npm run build
npm run lint
uv run pytest tests/routes/test_chat_ws.py -q
uv run pytest tests/vad tests/routes/test_chat_ws.py tests/routes/test_asr.py -q
uv run pytest tests/ -q
uv run python -m mypy src/ --ignore-missing-imports
uv run ruff format src/routes/chat_ws.py tests/routes/test_chat_ws.py --check
uv run ruff check src/routes/chat_ws.py tests/routes/test_chat_ws.py
```

记录结果：

- `tests/routes/test_chat_ws.py`：32 passed。
- `tests/vad tests/routes/test_chat_ws.py tests/routes/test_asr.py`：68 passed。
- 全量 `tests/`：432 passed, 4 deselected。
- mypy 和 ruff 通过。
- 前端 type-check、build、lint 通过，保留既有 warning。

## 收尾结论

VAD 第一版的完成边界是 M0-M6：

1. 实时麦克风输入。
2. 后端 VAD 判断。
3. `speech_start` 打断 LLM 流式输出和当前 TTS 播放。
4. `speech_end` 后端 ASR 自动接管。
5. interrupted 历史、记忆和旧 TTS 结果治理。
6. 配置、使用说明和 README 文档入口。

2026-07-08 的 TTS 分段流式化与 TTS 流式边界补丁已确认属于后续独立 feature。对 VAD 本 feature 只保留以下长期边界：

- TTS 是 LLM 文本回复的下游消费者。
- VAD `speech_start` 使旧 generation 失效。
- 前端丢弃旧 generation 音频。
- interrupted partial reply 以已发送给前端文本为准。
- 第一版不引入 `heard_response`。
