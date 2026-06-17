# VAD 开发记录

本文是 VAD 实时打断功能的开发 blog，用于记录阶段性背景、关键决策、改动内容和验证结果。

里程碑职责、执行顺序和验收标准以 `docs/developments/wiki/VAD/vad-implementation-plan.md` 为准。本文只记录已经讨论或完成的阶段性开发事实，避免替代实施计划。

## 2026-06-15: M2 WebSocket 协议草案

### 1. 背景与目标

ATRI 原有聊天 WebSocket 主要承担文字输入和文本流式输出。VAD 实时打断需要前端持续上传麦克风小片段，后端在检测到用户开口时立即通知前端停止播放。

本次草案的目标是先确定 M2 的消息边界：后端能接收实时音频、返回监听状态、发送打断控制事件，并为后续 ASR 和 LLM task cancel 预留协议。

### 2. 方案与决策

#### 考虑过的方案

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| 沿用 ATRI WebSocket JSON 消息结构 | 与现有 `input:*`、`output:*`、`control:*` 风格一致，前后端易扩展 | 音频数组会带来较大的 JSON payload |
| 直接复用 OLV sentinel bytes | 接近参考项目实现，控制事件很轻量 | 与 ATRI 当前协议风格不一致，也不利于浏览器侧调试 |
| 继续使用 REST 上传完整音频 | 实现简单 | 无法在用户开口瞬间打断 TTS 或 LLM 输出 |

#### 决策理由

M2 选择 WebSocket JSON 消息结构。第一版优先保证协议清晰、可调试、与现有聊天通道兼容；不直接复用 OLV 的 `b"<|PAUSE|>"`、`b"<|RESUME|>"` sentinel bytes。

音频 chunk 采用 `16 kHz / mono / PCM float array`。这与后续 Silero VAD 输入方向一致，也方便 fake provider 和测试先行。

### 3. 改动详情

#### 3.1 核心变更

1. 明确 VAD 相关消息继续使用统一结构：

```json
{
  "type": "消息类型",
  "data": {}
}
```

2. 定义前端到后端的实时音频消息。
3. 定义后端到前端的监听状态、打断控制和 ASR transcript 预留消息。
4. 明确 M2 只做后端实时语音控制层，不做前端麦克风采集、真实 ASR、真实 LLM 取消和 TTS 链路重写。

#### 3.2 协议 / 数据结构变更

前端到后端：

| type | 作用 | M2 处理结果 |
| --- | --- | --- |
| `input:audio:chunk` | 发送一段实时麦克风音频 | 调用 `VADService.process_audio()` |
| `input:audio:end` | 通知本轮实时音频输入结束 | 清理或重置当前监听状态，不提交 ASR |

后端到前端：

| type | 作用 | 触发时机 |
| --- | --- | --- |
| `control:listen-state` | 返回 VAD 监听状态 | 每次处理音频 chunk 或输入结束 |
| `control:interrupt` | 通知前端立即打断播放或旧回复 | VAD 事件为 `speech_start` 时 |
| `output:asr:transcript` | 返回 ASR 转写文本 | M2 只定义和预留，真实触发属于 M4 |

`input:audio:chunk`：

```json
{
  "type": "input:audio:chunk",
  "data": {
    "chat_id": "chat_xxx",
    "character_id": "atri",
    "audio": [0.01, -0.02, 0.03],
    "seq": 1
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | `string` | 是 | 当前聊天 ID。 |
| `character_id` | `string` | 是 | 当前角色 ID。 |
| `audio` | `number[]` | 是 | 16 kHz、mono、PCM float array。 |
| `seq` | `number` | 否 | 客户端音频 chunk 序号，用于调试丢包或乱序。 |

`input:audio:end`：

```json
{
  "type": "input:audio:end",
  "data": {
    "chat_id": "chat_xxx",
    "character_id": "atri"
  }
}
```

`control:listen-state`：

```json
{
  "type": "control:listen-state",
  "data": {
    "chat_id": "chat_xxx",
    "character_id": "atri",
    "state": "speech_start",
    "is_speech": true,
    "seq": 1,
    "probability": 0.86,
    "energy": 0.72
  }
}
```

`state` 枚举：

| state | 含义 |
| --- | --- |
| `speech_start` | 用户开始说话。 |
| `speech_chunk` | 用户仍在说话，或仍处于说话回合内。 |
| `speech_end` | 用户说话结束。 |
| `silence` | 当前没有有效语音。 |
| `error` | VAD 处理失败。 |

`control:interrupt`：

```json
{
  "type": "control:interrupt",
  "data": {
    "chat_id": "chat_xxx",
    "character_id": "atri",
    "reason": "speech_start"
  }
}
```

`control:interrupt` 不等待 ASR 文本。只要后端 VAD 判断用户开始说话，就可以发送该控制事件。

`output:asr:transcript`：

```json
{
  "type": "output:asr:transcript",
  "data": {
    "chat_id": "chat_xxx",
    "character_id": "atri",
    "text": "你好",
    "is_final": true,
    "seq": 1
  }
}
```

M2 不要求真实 ASR 触发该事件。它只预留消息结构，方便 M4 沿用同一 WebSocket 协议。

打断触发规则：

1. `control:listen-state` 可以每个音频 chunk 都返回。
2. `control:interrupt` 只在 `speech_start` 时返回。
3. 同一轮连续说话期间，`control:interrupt` 只发送一次。
4. 用户说话结束并进入 `speech_end` 后，下一次 `speech_start` 可以再次触发 interrupt。
5. VAD 关闭时，`input:audio:chunk` 返回 `control:listen-state`，`state` 为 `silence`，并带上 disabled 语义。

M2 后端连接级状态：

| 状态 | 作用 |
| --- | --- |
| `vad_session_id` | 标识当前连接的 VAD session。 |
| `audio_buffer` | 预留当前连接的音频缓存结构和清理路径，M2 不提交 ASR。 |
| `current_chat_task` | 预留当前聊天生成任务引用，M5 再真正取消。 |
| `interrupt_sent` | 防止同一轮连续说话重复发送 `control:interrupt`。 |
| `last_chat_id` | 记录最近一次语音消息关联的 chat。 |
| `last_character_id` | 记录最近一次语音消息关联的 character。 |

#### 3.3 文件清单

- `docs/developments/wiki/VAD/development.md`
  - 记录 M2 WebSocket 协议草案。
  - 明确 M2 不负责的内容和后续里程碑边界。
- `docs/developments/wiki/VAD/vad-implementation-plan.md`
  - 作为 M2 职责和验收来源。

### 4. 验证

#### 测试结果

本条是协议草案，不包含代码执行。

#### 代码检查

未运行代码检查。

#### 已知问题

- JSON float array 的 payload 较大，第一版接受该成本，后续可再评估二进制帧。
- M2 只定义 ASR transcript 协议，不实现 speech_end 后的真实 ASR。
- M2 只预留 LLM task 引用，不真正取消 LLM 回复。

### 5. 后续

进入 M2 实现：在后端聊天 WebSocket 中接入音频消息分发、VAD session、interrupt 事件和测试覆盖。

## 2026-06-17: M2 WebSocket 实时语音控制层完成

### 1. 背景与目标

协议草案完成后，后端需要真正具备实时语音控制能力。M2 的目标不是完成完整语音对话，而是让 WebSocket 可以持续接收音频、判断 VAD 状态、发送控制事件，并保持原有文字聊天兼容。

M2 要解决的问题：

1. 后端能识别实时音频消息，而不是把它误当成文字聊天。
2. 后端能把音频 chunk 交给 `VADService`。
3. 后端能在 `speech_start` 时立即发出 `control:interrupt`。
4. 后端能在 LLM 文本输出期间继续接收音频控制消息。
5. 后端能为 M4 的 ASR transcript 和 M5 的 LLM task 取消预留结构。

### 2. 方案与决策

#### 考虑过的方案

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| 在现有 WebSocket receive loop 中同步处理聊天生成 | 改动少 | LLM 输出期间无法及时处理音频 chunk |
| 将文字聊天生成放入后台 task | WebSocket 可以继续接收 VAD 控制消息 | 需要处理并发发送同一连接的问题 |
| 每个连接维护 `send_lock` | 避免聊天 chunk 和 VAD 控制事件并发写连接 | 增加连接状态管理复杂度 |

#### 决策理由

M2 选择“聊天生成后台 task + 连接级 `send_lock`”。这样用户在 LLM 输出期间开口时，WebSocket receive loop 仍能处理 `input:audio:chunk`，并尽快发出 `control:interrupt`。

### 3. 改动详情

#### 3.1 核心变更

1. 增加 `input:audio:chunk` 消息处理。
2. 增加 `input:audio:end` 消息处理。
3. 增加 `control:listen-state` 监听状态返回。
4. 增加 `control:interrupt` 控制事件，并在 `speech_start` 时触发。
5. 确保同一轮连续说话只发送一次 `control:interrupt`。
6. 预留 `output:asr:transcript` 协议发送能力，但不接真实 ASR。
7. 为每个 WebSocket 连接维护 `VADSession` 标识。
8. 为每个 WebSocket 连接维护 `audio_buffer`，并在 `speech_end`、`input:audio:end`、连接清理时释放。
9. 为每个 WebSocket 连接维护 `current_chat_task` 引用，作为 M5 取消 LLM 回复的基础。
10. 将文字聊天处理调整为后台 task，使 WebSocket receive loop 在 LLM 输出期间仍能接收音频消息。
11. 为 WebSocket 输出增加连接级 `send_lock`，避免聊天后台 task 和 VAD 控制消息并发写同一个连接。
12. 补充 WebSocket 路由测试，覆盖音频消息、interrupt、缓存、ASR transcript 协议、聊天 task 引用和发送锁。

#### 3.2 协议 / 数据结构变更

M2 实现沿用 2026-06-15 的协议草案。本阶段没有引入新的外部消息类型。

实现后的关键行为：

1. VAD disabled 时，`input:audio:chunk` 返回 `control:listen-state`，状态为 `silence`。
2. fake VAD provider 检测到 `speech_start` 后，后端发送 `control:interrupt`。
3. `input:audio:end` 可以重置当前监听状态并清理音频缓存。
4. `output:asr:transcript` 只作为发送辅助能力预留。

#### 3.3 文件清单

- `src/routes/chat_ws.py`
  - 增加 VAD WebSocket 消息分发。
  - 增加连接级 VAD 状态、音频缓存、聊天 task 引用和发送锁。
  - 增加 `control:listen-state`、`control:interrupt`、`output:asr:transcript` 发送路径。
- `tests/routes/test_chat_ws.py`
  - 覆盖音频消息、interrupt、防重复打断、缓存清理、ASR transcript 预留和并发发送锁。

### 4. 验证

#### 测试结果

```bash
uv run pytest tests/routes/test_chat_ws.py -q
uv run pytest tests/ -q
```

```text
tests/routes/test_chat_ws.py: 14 passed
tests/: 391 passed, 4 deselected
```

#### 代码检查

```bash
uv run ruff format src/routes/chat_ws.py tests/routes/test_chat_ws.py
uv run ruff check . --fix
uv run python -m mypy src/ --ignore-missing-imports
```

结果：通过。

#### 已知问题

- M2 不做前端麦克风采集。
- M2 不做真实 ASR。
- M2 不真正取消 LLM task。
- M2 不写入 `chat_history interrupted=true`。
- M2 不接入 Silero 真实模型推理。

### 5. 后续

进入 M3：前端新增实时麦克风输入，把音频 chunk 通过 WebSocket 发送给后端，并响应后端的 interrupt 控制事件。

## 2026-06-17: M3 前端实时麦克风输入完成

### 1. 背景与目标

M2 已经让后端 WebSocket 支持实时音频控制，但前端还没有实时麦克风输入。M3 的目标是在不替换原有按钮式 ASR 的前提下，新增一个独立实时 VAD 开关。

M3 要达到的效果：

1. 用户开启实时语音模式后，前端持续发送麦克风音频片段。
2. 后端发送 `control:interrupt` 后，前端立即停止当前 TTS 播放和播放队列。
3. 关闭实时语音模式或 WebSocket 断开时，前端释放麦克风资源。
4. 原有按钮式 ASR、MediaRecorder 路径和 stop button 保持可用。
5. 没有角色、有效 chat 或 WebSocket 连接时，实时 VAD 开关不可用。

### 2. 方案与决策

#### 考虑过的方案

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| 复用现有 `VoiceInput` 按钮 | UI 改动少 | 会混淆按钮式 ASR 和实时 VAD 两条链路 |
| 新增独立实时 VAD 开关 | 行为边界清晰，便于禁用和回滚 | 需要新增组件和状态管理 |
| WebSocket 未连接时把音频 chunk 入队 | 不丢消息 | 实时语音过期后再发送没有意义，还可能误触发 VAD |
| WebSocket 未连接时直接停止监听 | 符合实时控制语义 | 用户需要重连后手动重新开启 |

#### 决策理由

M3 选择独立开关，放在 `InputBox.vue` 的 `chat-input-tools` 区域，紧邻当前 `VoiceInput`。这样用户能清楚区分“一次性按钮式 ASR”和“持续实时 VAD”。

实时音频发送只允许在 WebSocket 已连接时发生。断线或重连中不补发旧音频，正在监听时立即停止并释放麦克风。

### 3. 改动详情

#### 3.1 核心变更

1. 扩展前端 WebSocket 消息分发。
   - 识别 `output:asr:transcript`。
   - 识别 `control:listen-state`。
   - 识别 `control:interrupt`。
2. 将 `control:interrupt` 接到现有 audio player。
   - 收到 interrupt 后调用 `useAudioPlayer().stop()`。
   - 停止当前 TTS 播放并清空播放队列。
3. 新增实时语音输入 composable。
   - 使用浏览器麦克风和 `AudioContext` 获取实时音频。
   - 将音频转换为 `16 kHz / mono / PCM float array`。
   - 按序号发送 `input:audio:chunk`。
   - 停止时发送 `input:audio:end`。
   - WebSocket 断开时自动停止监听并释放资源。
4. 增加 WebSocket 即时发送能力。
   - 新增 `sendIfOpen()`。
   - 实时音频发送绕开普通消息队列。
   - 未连接时直接失败，不缓存音频 chunk。
5. 新增实时 VAD 开关 UI。
   - 新增 `RealtimeVoiceInput.vue`。
   - 插入 `InputBox.vue`，位于当前麦克风按钮旁边。
   - 普通聊天和 Live2D stage 复用同一个 `InputBox`，因此两个入口都会显示该开关。
6. 增加实时语音状态。
   - 支持禁用、启动中、监听中、说话中和错误状态。
   - `control:listen-state` 中的 `speech_start`、`speech_chunk` 会驱动说话中状态。
   - `error` 状态会显示错误提示。
7. 保留原有按钮式 ASR。
   - `VoiceInput.vue` 和 `useVoiceInput.ts` 的 MediaRecorder/Web Speech API 路径保持不变。

#### 3.2 协议 / 数据结构变更

M3 不新增后端协议。前端实现并消费 M2 已定义的协议：

前端发送：

```json
{
  "type": "input:audio:chunk",
  "data": {
    "chat_id": "chat_xxx",
    "character_id": "atri",
    "audio": [0.01, -0.02, 0.03],
    "seq": 1
  }
}
```

前端停止监听时发送：

```json
{
  "type": "input:audio:end",
  "data": {
    "chat_id": "chat_xxx",
    "character_id": "atri"
  }
}
```

前端消费：

| type | 前端行为 |
| --- | --- |
| `control:interrupt` | 调用 `useAudioPlayer().stop()`。 |
| `control:listen-state` | 更新监听中、说话中和错误状态。 |
| `output:asr:transcript` | 先完成事件分发，真实接入聊天属于 M4。 |

实时 VAD 开关启用条件：

1. ASR 模块启用。
2. 已选择聊天角色。
3. 当前存在有效 chat。
4. 当前 chat 不能是 `draft_` 临时 chat。
5. WebSocket 已连接。

#### 3.3 文件清单

- `frontend/src/utils/websocket.ts`
  - 增加 VAD 相关事件分发。
  - 增加 `sendIfOpen()`。
  - 增加 `off()`，用于 composable 解绑监听。
- `frontend/src/stores/websocket.ts`
  - 暴露 store 层 `sendIfOpen()`。
- `frontend/src/composables/useWebSocket.ts`
  - 收到 `vad:interrupt` 后调用 audio player stop。
- `frontend/src/composables/useRealtimeVoiceInput.ts`
  - 新增实时麦克风采集、重采样、音频 chunk 发送、断线停止和监听状态消费。
- `frontend/src/components/chat/RealtimeVoiceInput.vue`
  - 新增实时 VAD 独立开关。
  - 展示禁用、启动中、监听中、说话中和错误状态。
- `frontend/src/components/chat/InputBox.vue`
  - 在当前 `VoiceInput` 旁边插入实时 VAD 开关。

### 4. 验证

#### 测试结果

本阶段没有新增前端自动化单元测试。验证以类型检查、lint、生产构建、代码路径检查和浏览器手动联调为主。

浏览器手动联调结果：

1. 实时 VAD button 可用，`disabled=false`，初始 `aria-pressed=false`。
2. 点击开启实时 VAD 后，浏览器控制台出现 `ScriptProcessorNode is deprecated` 警告。该警告说明当前实现已经进入 `AudioContext` 采集路径，不阻塞 M3 验证。
3. 通过临时 hook `WebSocket.prototype.send`，确认开启后前端持续发送 `input:audio:chunk`。
4. 再次点击关闭实时 VAD 后，确认前端发送 `input:audio:end`。

手动验证时捕获到的关键消息：

```text
[WS SEND] {"type":"input:audio:chunk","data":{"chat_id":...}}
[WS SEND] {"type":"input:audio:end","data":{"chat_id":"20260617_9f2b0f00","character_id":"atri"}}
```

这说明 M3 的核心前端链路已经打通：实时 VAD button 可以启动麦克风采集，前端能通过 WebSocket 发送实时音频 chunk，并能在手动关闭时发送结束消息。

#### 代码检查

```bash
npm run type-check
npm run lint
npm run build
```

结果：

```text
npm run type-check: passed
npm run lint: passed with existing warnings
npm run build: passed
```

lint 保留的既有 warning：

```text
src/components/airi-ui/TransitionVertical.vue
  74:14  warning  Unexpected any. Specify a different type
  75:13  warning  Unexpected any. Specify a different type
```

开发服务器验证：

```text
http://127.0.0.1:5173/ started
```

#### 已知问题

- 当前实时采集使用 `AudioContext` 配合 `ScriptProcessorNode`。它能满足 M3 范围，但后续可评估迁移到 `AudioWorklet`。
- 浏览器 DevTools 的 `Network -> WS` 面板未稳定显示消息；临时 hook `WebSocket.prototype.send` 已确认发送路径有效。
- 后端返回 `control:listen-state`、后端返回 `control:interrupt`、interrupt 时 TTS 实际停止、WebSocket 断线时自动停止监听，仍需在 M4/M5 联调时继续回归。
- M3 只负责前端发送音频和停止播放，不负责 speech_end 后自动 ASR。
- M3 不负责取消后端 LLM task，也不写入 `chat_history interrupted=true`。

### 5. 后续

进入 M4：后端在 `speech_end` 后把缓存的音频提交给现有 ASR service，并通过 `output:asr:transcript` 把转写结果接入前端和聊天流程。
