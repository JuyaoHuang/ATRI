# ATRI VAD 实时打断实施计划

状态：待执行  
日期：2026-06-15  
前置文档：`docs/developments/wiki/VAD/vad-design.md`、`docs/developments/wiki/VAD/vad-implement.md`

文档职责：本文件是 VAD M0-M7 的唯一实施步骤与验收来源；`vad-implement.md` 用于记录具体开发说明，`development.md` 仅作为开发 blog。

## 1. 实施总原则

1. 先实现 VAD 实时打断，不先重写全部 TTS 架构。
2. 后端负责 VAD 判断和会话打断控制，前端负责麦克风采集和本地音频停止。
3. VAD 模块按 provider/factory/service/session 形式设计，保持与 ASR、TTS 模块风格一致。
4. 第一版保留现有 REST TTS，后续再选择是否增加 WebSocket TTS payload。
5. 所有新增能力必须可配置、可关闭，关闭后不影响现有聊天、ASR、TTS。
6. WebSocket 消息命名沿用 ATRI 当前 `input:*`、`output:*`、`control:*` 风格，不直接照搬 OLV 的消息名。
7. 被 VAD 打断的 AI 半截回复可以写入 `chat_history`，但必须标记 `interrupted=true`。
8. 被打断的 AI 半截回复不作为普通完整 AI 回复进入短期记忆压缩或长期记忆写入流程。
9. Web Speech API 是浏览器侧 ASR 或降级事件源，不作为 VAD model。
10. OLV 的状态机、防抖和任务取消机制可复用；OLV 的 WebSocket 消息名和 sentinel bytes 不直接复用。
11. VAD 开发每完成一个独立小点单独提交，提交信息统一使用 `<type>(M<X>): <subject>` 格式，例如 `feat(M2): emit VAD interrupt events`。

## 2. 里程碑

### M0：文档与范围冻结

目标：明确 ATRI 当前链路、OLV 参考思路和 ATRI 第一版实现边界。

执行内容：

1. 完成 VAD 概念设计文档。
2. 完成 VAD 开发文档。
3. 完成 VAD 实施计划。
4. 明确第一版采用“WebSocket 麦克风输入 + 后端 VAD + 前端停止播放 + 后端取消 LLM”的路线。

验收：

1. 文档能解释为什么 VAD 不适合只做 REST API。
2. 文档能解释为什么第一版可以保留 REST TTS。
3. 文档能解释 OLV 的 VAD、ASR、TTS 联动方式。

### M1：后端 VAD 模块骨架

目标：建立独立 VAD 模块，不侵入 ASR/TTS/聊天主代码。

预计涉及位置：

1. `src/vad/`
2. `src/vad/interface.py`
3. `src/vad/factory.py`
4. `src/vad/service.py`
5. `src/vad/session.py`
6. `src/vad/providers/`
7. 配置文件或现有配置加载入口

执行内容：

1. 定义 VAD provider 统一接口。
2. 定义 VAD 事件类型，例如 speech_start、speech_end、silence、error。
3. 定义每个连接独立的 VADSession。
4. 增加一个测试用 fake provider，用于不依赖真实模型的单元测试。
5. 增加 Silero provider 的配置占位和懒加载策略。

验收：

1. VADService 可以接收音频 chunk 并输出稳定事件。
2. 测试环境不需要下载或加载真实 Silero 模型也能验证状态机。
3. provider 可通过配置选择或关闭。

### M2：WebSocket 协议扩展

目标：让现有聊天 WebSocket 支持实时音频输入和控制事件。

已确认协议方向：

1. 前端发送实时音频 chunk：`input:audio:chunk`。
2. 前端通知本轮音频输入结束：`input:audio:end`。
3. 后端通知用户开口打断：`control:interrupt`，`reason` 为 `speech_start`。
4. 后端通知 ASR 结果：`output:asr:transcript`。M2 只定义和预留该事件，真实 ASR 转写与触发属于 M4。
5. 后端通知监听状态：`control:listen-state`，`state` 可为 `speech_start`、`speech_end`、`silence`、`error`。
6. 音频 chunk 优先采用 16 kHz、mono、PCM float 数组，和 OLV 的 VAD 输入方向一致。
7. 不使用 OLV 的 `b"<|PAUSE|>"`、`b"<|RESUME|>"` sentinel bytes 作为模块外部协议。

预计涉及位置：

1. `src/routes/chat_ws.py`
2. WebSocket 消息模型或消息分发逻辑
3. 应用启动时的服务注册位置

执行内容：

1. 增加 `input:audio:chunk` 消息处理。
2. 增加 `input:audio:end` 消息处理。
3. 增加 `control:interrupt` 控制事件。
4. 增加 `output:asr:transcript` ASR 转写结果事件定义或发送辅助能力，M2 不调用真实 ASR。
5. 增加 `control:listen-state` 监听状态事件。
6. 为每个 WebSocket 连接维护当前 VADSession 和音频缓存结构，M2 不把缓存提交给 ASR。
7. 为每个 WebSocket 连接维护当前 LLM task 引用结构，M2 不真正取消 LLM task。

验收：

1. 普通文字聊天 WebSocket 行为不变。
2. 音频消息不会被误当成文字消息。
3. VAD 检测到 `speech_start` 后，后端能向前端发送 `control:interrupt`。
4. WebSocket 断开时能释放 VADSession、音频缓存和当前任务引用。
5. 同一轮连续说话期间，`speech_start` 只触发一次 `control:interrupt`。

M2 不负责前端麦克风采集、真实 ASR 转写、真实 LLM 任务取消、`chat_history interrupted=true` 写入、TTS 链路修改或真实 Silero 推理接入。

### M3：前端实时麦克风输入

目标：前端新增实时语音模式，把麦克风小片段持续发给后端。

已确认决策：

1. 实时 VAD 使用独立开关，不替换现有麦克风按钮。
2. 开关放在 `frontend/src/components/chat/InputBox.vue` 的 `chat-input-tools` 区域，紧邻当前 `VoiceInput`。
3. 开关随所有 `InputBox` 入口显示；当前包括普通聊天模式和 Live2D stage 聊天模式。
4. 第一版必须已有 `character_id`、有效 `chat_id` 且 WebSocket 已连接后才允许开启。
5. 没有有效聊天窗口时禁用开关，不自动创建空聊天或 draft chat。
6. 实时音频 chunk 只在 WebSocket 已连接时发送，不进入 `WebSocketManager` 的普通消息队列。
7. 断线或重连中直接丢弃实时音频 chunk；如果正在监听，则立即停止监听、释放麦克风并进入错误状态。
8. WebSocket 重连成功后不自动恢复监听，必须由用户手动再次打开开关。
9. 收到 `control:interrupt` 后调用现有 `useAudioPlayer().stop()`，停止当前 TTS 播放并清空播放队列。
10. 保留现有按钮式 ASR、MediaRecorder 降级路径和 stop button。

预计涉及位置：

1. `frontend/src/composables/`
2. `frontend/src/utils/websocket.ts`
3. `frontend/src/components/chat/InputBox.vue`
4. `frontend/src/components/chat/VoiceInput.vue`
5. `frontend/src/composables/useWebSocket.ts`
6. `frontend/src/stores/websocket.ts`
7. `frontend/src/composables/useAudioPlayer.ts`

执行内容：

1. 扩展前端 WebSocket 消息分发，识别 `control:listen-state`、`control:interrupt`、`output:asr:transcript`。
2. 在当前 WebSocket composable 中接收 `control:interrupt`，并调用现有 audio player stop 能力。
3. 新增实时语音输入 composable，例如 `useRealtimeVoiceInput.ts`。
4. 优先使用 AudioContext/AudioWorklet 获取小片段音频。
5. 将音频重采样为 16 kHz、mono、PCM float 数组。
6. 将音频片段通过 WebSocket 的 `input:audio:chunk` 发送到后端。
7. 实时音频发送必须绕开普通离线消息队列，未连接时直接丢弃并停止监听。
8. 新增实时 VAD 独立开关组件或在 `InputBox.vue` 中封装等价 UI，样式与当前麦克风按钮保持一致。
9. 为实时语音模式增加连接、监听中、说话中、错误、禁用等状态。
10. 保留 MediaRecorder 作为非实时按钮式 ASR 或降级路径，不作为 VAD 主路径。

验收：

1. 用户开启实时语音模式后，前端能持续发送音频片段。
2. 后端发送 interrupt 后，前端能停止当前 TTS 播放和播放队列。
3. 关闭实时语音模式后，麦克风资源被释放。
4. 原有按钮式 ASR 仍可使用。
5. 没有 `character_id`、有效 `chat_id` 或 WebSocket 连接时，实时 VAD 开关不可用。
6. WebSocket 断线或重连时，实时 VAD 自动停止并释放麦克风，不补发旧音频。
7. 普通聊天模式和 Live2D stage 聊天模式中，开关都位于当前麦克风按钮旁边。
8. 前端类型检查和构建通过。

### M4：VAD 到 ASR 的衔接

目标：完成“实时语音接管闭环”。用户开口时先打断旧输出；用户说完后，后端把本轮音频交给现有 ASR service，得到转写文本后由后端自动进入新一轮聊天流程。

已确认决策：

1. M4 不只是 `speech_end -> ASR`，还要补齐实时语音接管所需的最小后端控制能力。
2. `speech_start` 到来时，后端发送 `control:interrupt`，前端按 M3 已完成逻辑停止当前 TTS 播放和播放队列。
3. `speech_start` 到来时，后端对当前聊天生成执行机械取消：取消当前 `current_chat_task`，停止继续向前端发送旧回复。
4. 当前 ATRI 聊天协议没有能区分“一次生成”的 id；M4 需要新增 `generation_id`，用于判断旧 LLM 输出是否已经失效。
5. `chat_id` 只表示聊天窗口或会话，不能用于判断某一轮 LLM 生成是否仍有效。
6. `generation_id` 由后端生成。每次文字输入或 ASR 自动提交触发新一轮聊天时，都创建新的 `generation_id`。
7. `output:chat:chunk`、`output:chat:complete`、`output:asr:transcript` 都应携带 `generation_id`。
8. 后端发送 chunk、发送 complete、持久化本轮消息前，都必须检查当前任务的 `generation_id` 是否仍是有效 generation；如果已经失效，直接丢弃旧结果。
9. `output:asr:transcript` 是展示事件，不是前端再次调用 `sendMessage()` 的触发器；否则会重复提交。
10. M4 采用后端自动提交：`speech_end -> ASR -> output:asr:transcript -> 后端启动聊天`。
11. 如果当前 ASR provider 是 `web_speech_api`，后端不能执行自动 ASR，因为它是浏览器侧能力，不是后端可调用的 ASR provider。
12. `web_speech_api` 场景下，VAD 打断仍可用，但 `speech_end` 后端自动 ASR 和自动聊天必须跳过，并返回明确错误状态。

预计涉及位置：

1. `src/asr/`
2. `src/routes/chat_ws.py`
3. WebSocket 会话状态管理逻辑
4. 前端 WebSocket 消息类型与 ASR transcript 展示逻辑
5. 后端 WebSocket 测试

执行内容：

1. 扩展 WebSocket 会话状态，记录当前有效 `generation_id`。
2. 每次启动文本聊天或 ASR 自动提交聊天时，生成新的 `generation_id`。
3. 在 `speech_start` 时标记旧 `generation_id` 失效。
4. 在 `speech_start` 时取消当前 `current_chat_task`，实现机械取消。
5. 在聊天 chunk 发送前检查 `generation_id`，旧 generation 的 chunk 不再发送。
6. 在聊天 complete 发送前检查 `generation_id`，旧 generation 的 complete 不再发送。
7. 在消息持久化前检查 `generation_id`，旧 generation 的普通完整消息不再写入。
8. 修改 `output:chat:chunk` 和 `output:chat:complete`，在 data 中带上 `generation_id`。
9. VADSession 在 `speech_start` 后开始缓存有效音频，保留必要的 pre-buffer，避免吞掉句首。
10. VADSession 在 `speech_end` 后输出完整语音段，而不是直接清空 `audio_buffer`。
11. 把完整语音段转换为现有 ASR service 可接受的音频输入。
12. 调用现有 ASR service 执行后端转写。
13. 如果 ASR provider 是 `web_speech_api` 或其它 browser-only provider，返回 `control:listen-state` 错误，不触发自动聊天。
14. ASR 成功后发送 `output:asr:transcript`，包含 `text`、`chat_id`、`character_id`、`generation_id`、`is_final`。
15. ASR 文本为空、全空白、过短或明显无效时，不启动新一轮聊天。
16. ASR 成功且文本有效时，后端直接把该文本作为用户输入进入现有聊天处理流程。
17. 前端收到 `output:asr:transcript` 后只负责展示用户刚说的话，不调用 `sendMessage()`。
18. ASR 失败时返回明确错误，不断开 WebSocket。
19. 保持普通文字聊天、按钮式 ASR 和 REST TTS 既有行为不变。

建议协议字段：

`output:asr:transcript`：

```json
{
  "type": "output:asr:transcript",
  "data": {
    "text": "用户刚说的话",
    "chat_id": "chat id",
    "character_id": "character id",
    "generation_id": "本轮生成 id",
    "is_final": true
  }
}
```

`control:listen-state` 在后端 ASR 不可用时：

```json
{
  "type": "control:listen-state",
  "data": {
    "state": "error",
    "code": "backend_asr_unavailable",
    "message": "VAD auto-submit requires a backend ASR provider; current provider is browser-only.",
    "chat_id": "chat id",
    "character_id": "character id"
  }
}
```

验收：

1. 用户说一句话后，不需要再次点击发送即可进入聊天。
2. 前端能显示 ASR 转写文本。
3. ASR 失败时能返回明确错误，不破坏 WebSocket 连接。
4. 过短音频或纯噪声不会触发一轮新对话。
5. LLM 正在输出文字时，用户开口后旧回复停止继续输出。
6. 用户开口后，旧 `generation_id` 的 chunk、complete 和普通持久化结果会被丢弃。
7. ASR 自动提交触发的新一轮聊天使用新的 `generation_id`。
8. 当前 ASR provider 为 `web_speech_api` 时，VAD 打断仍可用，但 `speech_end` 后不会自动提交聊天，并返回明确错误状态。
9. 前端不会因为 `output:asr:transcript` 再次调用 `sendMessage()` 导致重复提交。
10. 普通文字聊天、按钮式 ASR、REST TTS 不受影响。

M4 不做：

1. 不写入 `chat_history interrupted=true`。
2. 不保存被打断的半截 AI 回复。
3. 不处理被打断回复是否进入短期记忆压缩或长期记忆。
4. 不重构 TTS 为 WebSocket payload。
5. 不保证取消已经发出的 REST TTS API 请求。
6. 不做完整 TTS 队列治理。

### M5：打断语义与副作用治理

目标：让“被打断”成为一等语义。M4 负责让旧输出停止、让新语音接管；M5 负责处理旧输出已经产生的半截文本、历史记录、记忆系统、前端 streaming 状态和 REST TTS 请求结果。

已确认决策：

1. M5 不再负责基础 LLM task 取消；机械取消和旧 `generation_id` 丢弃规则属于 M4。
2. M5 采用后端已发送 chunk 的累积文本作为 `partial_reply` 的唯一来源。
3. M5 第一版不引入 OLV 的前端 `heard_response` 回传。
4. `partial_reply` 表示“后端已经发送给前端的文本”，不强行等同于“用户实际听到的 TTS 文本”。
5. 被打断的半截 AI 回复可以展示和审计保存，但必须标记 `interrupted=true`。
6. 被打断的半截 AI 回复不作为普通完整轮次进入记忆系统。
7. 被打断的半截 AI 回复不进入 `recent_messages`，不增加 `total_rounds`，不触发短期记忆压缩，不写入长期记忆。
8. 从 `chat_history` rebuild 短期记忆时，也必须跳过 `interrupted=true` 的 AI 消息。
9. 被打断 generation 不触发新的自动 TTS。
10. 已经发出的 REST TTS 请求不要求 provider 级取消；请求返回后如果 `generation_id` 已失效，前端直接丢弃结果。

M5 与 M4 的边界：

1. M4 解决“旧任务如何停下”和“新语音如何接管”。
2. M5 解决“已经输出的旧内容如何被记录、展示和排除副作用”。
3. M5 的核心输入是旧 `generation_id`、后端累积的 `partial_reply` 和 VAD interrupt reason；核心输出是 `output:chat:interrupted`、带 metadata 的历史消息，以及对记忆和 TTS 队列的跳过规则。

预计涉及位置：

1. `src/routes/chat_ws.py`
2. `src/agent/chat_agent.py`
3. `src/memory/chat_history.py`
4. `src/memory/manager.py`
5. `src/storage/`
6. `frontend/src/utils/websocket.ts`
7. `frontend/src/composables/useWebSocket.ts`
8. `frontend/src/composables/useAudioPlayer.ts`
9. `frontend/src/stores/chat.ts`
10. 前后端消息类型定义

执行内容：

1. 在 WebSocket 会话状态中为当前 generation 维护 `partial_reply`。
2. 每次发送 `output:chat:chunk` 后，把已发送 chunk 追加到当前 generation 的 `partial_reply`。
3. VAD `speech_start` 使旧 generation 失效时，如果 `partial_reply` 非空，发送 `output:chat:interrupted`。
4. `output:chat:interrupted` 携带 `chat_id`、`character_id`、`generation_id`、`partial_reply`、`interrupted=true`、`reason`。
5. 前端收到 `output:chat:interrupted` 后结束当前 streaming 状态。
6. 如果 `partial_reply` 非空，前端把当前半截回复收束成一条 AI 消息，并标记 `interrupted=true`。
7. 如果 `partial_reply` 为空，前端只清空 `streamingText`，不生成 AI 消息。
8. 扩展前端 `Message` 类型，支持 `generation_id`、`interrupted`、`interrupt_reason`。
9. 扩展前端历史响应类型，使历史消息可以携带 interrupted metadata。
10. 扩展后端普通聊天历史存储，使 AI 消息可以保存 `generation_id`、`interrupted`、`interrupt_reason`。
11. 扩展 MemoryManager 的 `chat_history` 写入能力，使 interrupted AI 消息能进入审计历史。
12. 修改 MemoryManager 有效轮次判断，使 `interrupted=true` 的 AI 消息不计入有效轮次。
13. 修改 MemoryManager rebuild 逻辑，使从 `chat_history` 恢复短期记忆时跳过 `interrupted=true` 的 AI 消息。
14. 确保 interrupted AI 消息不进入 `recent_messages`。
15. 确保 interrupted AI 消息不触发 L3/L4 短期记忆压缩。
16. 确保 interrupted AI 消息不写入长期记忆。
17. 前端自动 TTS 调用携带 `generation_id`。
18. `useAudioPlayer` 为队列项和正在进行的合成请求记录 `generation_id`。
19. VAD interrupt 到来时，前端标记旧 `generation_id` 的 TTS 结果失效。
20. 旧 REST TTS 请求返回后，如果 `generation_id` 已失效，直接释放结果，不入队、不播放。
21. 普通 `output:chat:complete` 路径继续表示正常完整回复；只有 `output:chat:interrupted` 表示被打断回复。

建议协议字段：

`output:chat:interrupted`：

```json
{
  "type": "output:chat:interrupted",
  "data": {
    "chat_id": "chat id",
    "character_id": "character id",
    "generation_id": "被打断的生成 id",
    "partial_reply": "已经发送给前端的半截 AI 回复",
    "interrupted": true,
    "reason": "vad_speech_start"
  }
}
```

历史消息 metadata：

```json
{
  "role": "ai",
  "content": "已经发送给前端的半截 AI 回复",
  "generation_id": "被打断的生成 id",
  "interrupted": true,
  "interrupt_reason": "vad_speech_start"
}
```

验收：

1. LLM 正在流式输出文字时，用户开口后前端 streaming 状态能正常结束。
2. 已经输出的半截 AI 回复能在前端显示为 interrupted 消息。
3. 空 `partial_reply` 不生成空 AI 消息。
4. 被打断的半截 AI 回复能写入可审计历史，并带 `interrupted=true`。
5. 被打断的半截 AI 回复不增加 `total_rounds`。
6. 被打断的半截 AI 回复不进入 `recent_messages`。
7. 被打断的半截 AI 回复不触发短期记忆压缩。
8. 被打断的半截 AI 回复不写入长期记忆。
9. 从 `chat_history` rebuild 后，`interrupted=true` 的 AI 消息仍不会进入短期记忆。
10. 被打断 generation 不会触发新的自动 TTS。
11. 已经发出的旧 REST TTS 请求返回后不会入队播放。
12. 普通完整聊天回复仍按原有 complete 路径展示、持久化和自动 TTS。
13. 用户下一句话能正常接续对话。

M5 不做：

1. 不做 VAD 检测。
2. 不做 ASR 自动提交。
3. 不做后端机械取消。
4. 不做基础 `generation_id` 引入。
5. 不引入前端 `heard_response` 回传。
6. 不引入 OLV 的句子级 TTS 管线。
7. 不做 TTS WebSocket 化。
8. 不保证 provider 级取消已经发出的 TTS API 请求。

### M6：配置、测试与文档补齐

目标：让功能可配置、可测试、可回归。

当前收尾范围：M4/M5 已补齐主要后端测试、WebSocket 测试、存储测试、记忆测试和前端构建验证；M6 本轮以发布文档和人工验收入口为主，不再更新 `tests/*/test-exe.md`。

执行内容：

1. 增加 VAD 配置文档。
2. 增加前端实时语音模式说明。
3. 在文档中明确 `web_speech_api`、`sherpa_onnx_asr`、`silero_vad` 的适用边界。
4. 在文档中明确 Silero 防抖、静默结束时间和调参方法。
5. 在文档中明确浏览器 DevTools 的 WebSocket 验收路径。
6. 汇总现有后端测试、WebSocket 测试和前端检查命令。

验收：

1. VAD 默认配置清晰可查，入口为 `docs/configs/CN/VAD配置说明.md` 和 `docs/configs/EN/VAD-configuration.md`。
2. 实时语音模式使用方法清晰可查，入口为 `docs/configs/CN/实时语音模式使用说明.md` 和 `docs/configs/EN/realtime-voice-mode.md`。
3. 文档能解释为什么 `web_speech_api` 不能完成后端 VAD 自动 ASR。
4. 文档能解释 `silero_vad.required_hits`、`required_misses`、`smoothing_window` 的作用和延时估算。
5. 文档能指导用户在 DevTools 中确认 `VAD -> ASR -> 后端自动聊天` 链路。
6. 文档记录现有测试和构建检查入口，便于回归。

### M7：可选 TTS WebSocket 化

目标：在第一版稳定后，评估是否把 TTS 输出改成更接近 OLV 的 WebSocket 分段音频。

OLV 可借鉴机制：

1. OLV 的 LLM token stream 不直接按 token 驱动 TTS。
2. OLV 先用 sentence divider 把 token 累积成句子或短句。
3. 每个句子产生一个 `SentenceOutput`，同时包含 `display_text` 和 `tts_text`。
4. `display_text` 用于前端展示。
5. `tts_text` 用于 TTS 合成。
6. TTS task manager 为每个句子创建 TTS 任务，并用 sequence 保证音频按顺序下发。
7. interrupt 到来时，conversation task 被取消，TTS manager 清理未发送音频队列。
8. OLV 可由前端发送 `heard_response`，表示用户实际已经听到或看到的回复片段。
9. 后端把 `heard_response` 交给 agent 的 interrupt handler。
10. agent 将半截回复写入上下文，并追加 `[Interrupted by user]`，让下一轮模型知道上一轮被用户打断。

OLV 打断处理流程：

1. 用户开口触发 VAD interrupt 后，WebSocket 层通知当前 conversation 停止继续处理旧输出。
2. conversation task 取消后，LLM token stream 停止继续消费；各 provider 在 `finally` 中关闭流式连接或释放上下文。
3. TTS manager 清空尚未发送或尚未播放的句子级音频任务，避免旧回复继续出声。
4. 前端把已经实际展示或播放到的内容作为 `heard_response` 回传。
5. 后端 interrupt handler 优先使用 `heard_response` 作为半截回复，而不是使用完整模型输出。
6. 半截回复只作为“这轮被打断”的上下文事实保留，并带 interrupt marker；它不等同于一轮正常完成的 AI 回复。

执行内容：

1. 将 LLM 文本按句子或短段切分。
2. 每段调用现有 TTS provider 合成完整小音频。
3. 后端通过 WebSocket 下发音频 payload 和 sequence。
4. 前端按 sequence 播放。
5. interrupt 到来时，前端清空音频队列，后端取消未完成 TTS 任务。
6. 为每个句子级输出分配 `generation_id`、`segment_id` 和 `sequence`。
7. 前端记录已经展示或已经播放完成的 segment。
8. interrupt 到来时，前端可回传 `heard_response` 或已播放 segment 列表。
9. 后端使用前端回传内容修正被打断回复的 `partial_reply`，使其更接近用户实际听到的内容。
10. 后端将 interrupt marker 注入下一轮上下文，但仍避免把 interrupted 回复当作普通完整轮次写入记忆。

验收：

1. 即使 TTS provider 不支持真正流式，也能实现分段播放。
2. 用户能更早听到角色回复。
3. 打断时未播放的 TTS 队列能被清理。
4. 打断时后端能知道哪些句子或片段已经展示/播放。
5. `heard_response` 能用于更准确地保存被打断的半截回复。
6. interrupted 回复仍不会污染普通记忆轮次。

M7 不进入第一版必做范围。M5 第一版仍以“后端已发送 chunk 累积值”作为 `partial_reply`；只有在 M7 引入句子级 TTS 和播放确认后，才考虑切换为 OLV 式 `heard_response`。

## 3. 推荐执行顺序

1. 先做 M1，用 fake provider 验证 VAD 事件模型。
2. 再做 M2，把事件接入 WebSocket，但暂不接真实前端。
3. 再做 M3，让前端能发送音频并响应 interrupt。
4. 再做 M4，把 speech_end 接到 ASR 和聊天。
5. 再做 M5，补齐打断语义、历史策略、记忆跳过和旧 TTS 结果丢弃。
6. 最后做 M6 的测试和文档收尾。
7. M7 不进入第一版必做范围。

这个顺序能保证每一步都有独立可验收结果，避免一开始同时改 VAD、ASR、TTS、LLM 和前端播放器。

提交时按当前所属里程碑填写 scope，例如 `feat(M3): implement microphone capture`，不把不同里程碑或无关仓库变更混入同一个提交。

## 4. 配置计划

建议新增或扩展 VAD 配置。公共字段只保留链路级开关和音频格式；阈值、防抖和平滑窗口归属到具体 provider，避免 fake 测试 provider 与 Silero 模型 provider 共用同名参数导致语义混乱。

建议配置项：

1. `enabled`：是否启用 VAD。
2. `provider`：选择 VAD provider。
3. `sample_rate`：后端 VAD 使用的目标采样率。
4. `pre_buffer_ms`：speech_start 前保留的音频长度，用于避免 ASR 吞掉句首。
5. `chunk_ms`：前端音频片段长度。
6. `fake.speech_threshold`：fake provider 的能量阈值。
7. `fake.required_hits` / `fake.required_misses`：fake provider 的防抖参数。
8. `silero_vad.prob_threshold` / `silero_vad.db_threshold`：Silero provider 的语音概率与分贝阈值。
9. `silero_vad.required_hits` / `silero_vad.required_misses` / `silero_vad.smoothing_window`：Silero provider 的 OLV 风格状态机参数。
10. `min_speech_ms`：最短有效语音长度。
11. `interrupt_on_speech_start`：是否在 speech_start 立即触发打断。
12. `auto_submit_after_speech_end`：speech_end 后是否自动 ASR 并提交对话。

配置原则：

1. 所有阈值都应可调。
2. 模型实现细节不写死在业务代码。
3. 关闭 VAD 后不加载重型模型。
4. fake 被视为一个正式测试 provider，而不是全局 VAD 参数的特殊分支。
5. Silero 的防抖参数按 512-sample 小窗口理解，不能直接和前端 WebSocket chunk 次数混用。
6. Silero model 通过 `silero-vad` 包依赖提供，运行时用 `load_silero_vad()` 懒加载，不要求手动网页下载模型文件。

## 5. 测试计划

### 5.1 后端单元测试

覆盖内容：

1. fake provider 连续命中后触发 speech_start。
2. fake provider 连续静音后触发 speech_end。
3. 过短语音不进入 ASR。
4. VAD disabled 时音频消息被忽略或返回明确状态。
5. provider 异常时不会导致 WebSocket 崩溃。

### 5.2 后端集成测试

覆盖内容：

1. WebSocket 文本聊天保持原行为。
2. WebSocket 收到音频 chunk 后进入 VAD 流程。
3. VAD speech_start 触发 interrupt 消息。
4. speech_end 后调用 ASR service。
5. interrupt 会取消当前 LLM task。

### 5.3 前端验证

覆盖内容：

1. 实时语音模式能申请并释放麦克风权限。
2. WebSocket 断线时前端显示连接异常。
3. interrupt 到来时当前音频立即停止。
4. interrupt 到来时待播放队列被清空。
5. 原有 stop button 仍然可用。
6. 原有 REST TTS 自动朗读仍然可用。

### 5.4 手动测试场景

1. 角色正在播放 TTS，用户开口打断。
2. 角色正在输出文字但尚未 TTS，用户开口打断。
3. 用户短促咳嗽或背景噪声，不应触发完整新对话。
4. 用户说完一句话后自动 ASR 并进入聊天。
5. 关闭 VAD 后，系统退回原有交互方式。
6. 移动端浏览器在 VPN 网络下保持 WebSocket 稳定。

## 6. 回滚策略

1. VAD 功能必须有全局开关。
2. 前端实时语音模式必须是显式开启，不替换原有输入方式。
3. 后端 WebSocket 扩展不能改变现有文本消息协议的兼容行为。
4. 如果 Silero provider 不可用，可以切回 fake/disabled provider，保证系统仍可启动。
5. 如果 LLM task cancellation 出现问题，可以先只启用播放层打断，再单独修复对话层打断。

## 7. 第一版完成定义

第一版完成不以“所有音频都 WebSocket 化”为标准，而以下列结果为准：

1. ATRI 有独立 VAD 模块。
2. 前端能通过 WebSocket 持续发送麦克风音频。
3. 后端能基于 VAD 判断用户开口和说完。
4. 用户开口能停止当前 TTS 播放。
5. 用户开口能取消正在生成的 LLM 回复。
6. 用户说完后能自动 ASR，并进入新一轮对话。
7. 现有 REST TTS、按钮式 ASR、文字聊天不被破坏。
