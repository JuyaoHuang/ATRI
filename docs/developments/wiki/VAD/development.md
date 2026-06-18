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

## 2026-06-18: M4 VAD 到 ASR 的衔接实施完成

### 1. 背景与目标

M3 已经完成前端实时麦克风输入，但它只证明前端能持续发送音频 chunk，并能响应后端 interrupt。M4 要完成“实时语音接管闭环”：用户开口时先打断旧输出，用户说完后由后端提交 ASR，并把转写文本自动接入新一轮聊天。

M4 的目标不是处理被打断的半截回复如何进入历史和记忆。该部分已划入 M5。M4 只负责让旧生成停止、让新语音接管、让 ASR 文本进入聊天。

### 2. 方案与决策

#### 考虑过的方案

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| 仅做 `speech_end -> ASR` | 改动较小 | 不能处理 LLM 正在输出时的实时接管 |
| 在 M4 引入 `generation_id` 并取消当前 task | 能阻止旧回复继续输出，符合实时打断目标 | 需要改 WebSocket 会话状态和测试 |
| 前端收到 ASR transcript 后再次调用 `sendMessage()` | 前端复用已有发送路径 | 容易重复提交，且语音接管控制权分散 |
| 后端收到 ASR transcript 后自动启动聊天 | 控制链路集中，符合 OLV 的后端编排思路 | 后端 WebSocket 逻辑更复杂 |

#### 决策理由

M4 选择“后端自动提交 + `generation_id` 失效规则”。`chat_id` 只表示聊天窗口，不能表示某一次 LLM 生成。因此每次文字输入或 ASR 自动提交都生成新的 `generation_id`。

当 VAD 检测到 `speech_start` 时，后端立即发送 `control:interrupt`，并让当前 generation 失效。旧 generation 的 chunk、complete 和普通持久化结果都会被丢弃。这样即使 LLM 或 TTS 请求已经开始，旧结果也不会继续污染当前聊天流程。

### 3. 改动详情

#### 3.1 核心变更

1. 增加聊天 generation 状态。
   - WebSocket 连接维护当前有效 `generation_id`。
   - 文字聊天和 ASR 自动提交聊天都会创建新的 `generation_id`。
   - `output:chat:chunk`、`output:chat:complete`、`output:asr:transcript` 均携带 `generation_id`。

2. 实现 `speech_start` 打断旧输出。
   - `speech_start` 到来时发送 `control:interrupt`。
   - 取消当前 `current_chat_task`。
   - 标记旧 `generation_id` 失效。
   - 旧 generation 的 chunk、complete 和普通持久化结果直接丢弃。

3. 实现 `speech_end -> ASR -> 自动聊天`。
   - `speech_start` 后开始缓存有效音频。
   - 保留 `pre_buffer_ms`，避免 ASR 吞掉句首。
   - `speech_end` 后把缓存音频转成 WAV 字节。
   - 调用现有 ASR service。
   - ASR 成功后发送 `output:asr:transcript`。
   - ASR 文本有效时，后端自动以该文本启动新一轮聊天。

4. 接入后端 ASR provider。
   - 新增 `sherpa_onnx_asr`，用于复用 OLV 默认 SenseVoice / Sherpa-ONNX 思路。
   - 修复传统按钮式 ASR 的浏览器上传格式问题。
   - 增加上传音频元数据，便于后端判断 `source`、`sample_rate`、`channels` 和 `encoding`。

5. 接入真实 VAD provider。
   - 新增 `silero_vad` provider。
   - 使用 `silero-vad` 包中的 `load_silero_vad()` 懒加载模型。
   - 固定 CPU 推理路径，便于本地和服务器一致验证。
   - 使用 OLV 风格的 512 samples / 16 kHz 内部窗口、平滑窗口和防抖参数。

6. 增加本地 ASR 常驻能力。
   - 新增 `persistent_provider`，本地后端 ASR provider 首次加载后可常驻。
   - 新增 `preload_provider`，允许服务启动时预加载本地 ASR。
   - 两个字段为后端私有配置，不暴露给前端配置 API，也不允许前端回写。

7. 完善联调错误提示。
   - `web_speech_api` 场景下，VAD 打断仍可用，但后端自动 ASR 会返回明确错误。
   - 过短音频、空 ASR 文本和 ASR 失败不会触发新一轮聊天。
   - 前端 VAD 错误提示改为 3 秒后自动清除，新的错误仍覆盖旧错误。

#### 3.2 协议 / 数据结构变更

`output:chat:chunk` 和 `output:chat:complete` 新增 `generation_id`：

```json
{
  "type": "output:chat:chunk",
  "data": {
    "chunk": "文本片段",
    "chat_id": "chat id",
    "character_id": "character id",
    "generation_id": "本轮生成 id"
  }
}
```

`output:asr:transcript` 在 M4 变成真实触发事件：

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

`control:listen-state` 在 ASR 不可用或转写失败时返回错误状态：

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

ASR 后端私有配置：

```yaml
asr_model: sherpa_onnx_asr
```

```yaml
persistent_provider: true
preload_provider: false
```

VAD provider 配置：

```yaml
vad_model: silero_vad

silero_vad:
  sample_rate: 16000
  prob_threshold: 0.4
  db_threshold: 60
  required_hits: 3
  required_misses: 24
  smoothing_window: 5
```

当前 Silero 延时估算：

```text
Silero 内部窗口 = 512 samples / 16000 Hz = 32 ms
speech_start 理论防抖延时 = required_hits * 32 ms = 96 ms
speech_end 理论静默结束延时 = required_misses * 32 ms = 768 ms
```

实际体感还会叠加前端采集 chunk、网络传输、平滑窗口和 ASR 耗时。

#### 3.3 文件清单

- `src/routes/chat_ws.py`
  - 增加 `generation_id`、当前聊天 task、旧 generation 丢弃规则。
  - 接入 `speech_end -> ASR -> output:asr:transcript -> 自动聊天`。
  - 处理短音频、空 transcript、browser-only ASR 和 ASR 异常。
- `src/asr/`
  - 增加 ASR provider 常驻缓存和可选预加载。
  - 增加上传音频元数据契约。
  - 增加 `sherpa_onnx_asr` provider。
- `src/vad/`
  - 增加 `silero_vad` provider。
  - 调整 VAD 配置结构和 Silero 参数。
- `frontend/src/composables/useWebSocket.ts`
  - 消费 `output:asr:transcript` 并展示 ASR 文本。
  - 收到 `control:interrupt` 后停止当前音频播放。
- `frontend/src/composables/useRealtimeVoiceInput.ts`
  - 显示后端 VAD/ASR 错误。
  - 错误提示 3 秒后自动清除。
- `frontend/src/stores/chat.ts`
  - 展示 ASR transcript，不再次触发 `sendMessage()`。
- `config/asr_config.yaml`
  - 增加 `sherpa_onnx_asr` 配置。
  - 增加 `persistent_provider` 和 `preload_provider`。
- `config/vad_config.yaml`
  - 切换到 `silero_vad`。
  - 增加 Silero 延时计算说明。
- `tests/routes/test_chat_ws.py`
  - 覆盖 generation、speech_start 取消、speech_end ASR、自动聊天和错误路径。
- `tests/routes/test_asr.py`
  - 覆盖后端 ASR provider、上传格式、后端私有配置和常驻缓存。
- `tests/vad/`
  - 覆盖 fake 和 Silero provider 注册、状态机和防抖行为。
- `docs/developments/wiki/VAD/vad-implementation-plan.md`
  - 同步 M4/M5 边界、协议和后续分支策略。

### 4. 验证

#### 测试结果

```bash
uv run pytest tests/routes/test_asr.py tests/routes/test_chat_ws.py -q
```

```text
51 passed
```

```bash
uv run pytest tests/ -q
```

```text
420 passed, 4 deselected
```

前端验证：

```bash
npm run type-check
npm run lint
npm run build
```

```text
type-check: passed
lint: passed with existing warnings
build: passed
```

既有 lint warning：

```text
src/components/airi-ui/TransitionVertical.vue
  74:14  warning  Unexpected any. Specify a different type
  75:13  warning  Unexpected any. Specify a different type
```

#### 浏览器联调

本次联调使用实时 VAD button，不是传统按钮式 ASR。浏览器 DevTools `Network -> WS -> /ws -> 消息` 中观察到的关键顺序如下：

```text
output:chat:complete
input:audio:chunk
control:listen-state
input:audio:chunk
control:listen-state
control:interrupt
output:asr:transcript
output:chat:chunk
```

该顺序对应的链路为：

```text
AI 第一轮回复完成
  -> 用户开启 VAD button 并说话
  -> 前端持续发送 input:audio:chunk
  -> 后端 VAD 持续返回 control:listen-state
  -> 后端检测到 speech_start，发送 control:interrupt
  -> 后端在 speech_end 后提交 ASR
  -> ASR 成功，后端发送 output:asr:transcript
  -> 后端用 ASR 文本自动启动新一轮聊天
  -> 新一轮聊天开始 output:chat:chunk 流式输出
```

本次联调验证了 M4 的关键剩余点：

1. VAD button 实时音频链路可用。
2. `speech_start` 可触发 `control:interrupt`。
3. `speech_end` 后 ASR 可用。
4. ASR 成功后返回 `output:asr:transcript`。
5. transcript 由后端自动进入新一轮聊天。
6. 新一轮聊天开始流式输出 `output:chat:chunk`。

结论：该 WS 消息序列能证明本次链路不是传统 ASR，也不是手动文字输入，而是 `VAD -> ASR -> 自动聊天` 的 M4 闭环。

#### 代码检查

```bash
uv run ruff check src/asr src/app.py src/routes/chat_ws.py tests/routes/test_asr.py tests/routes/test_chat_ws.py
uv run python -m mypy src/asr src/app.py src/routes/chat_ws.py --ignore-missing-imports
```

结果：通过。

#### 已知问题

1. M4 的 `VAD -> ASR -> 自动聊天` 基本链路已通过浏览器 WS 联调。
2. Chrome DevTools 需要进入单条 `/ws` 连接的“消息”面板查看帧列表；`?token=...` 是 Vite HMR 通道，不是业务 WebSocket。
3. `web_speech_api` 不能作为后端自动 ASR provider。完整 M4 验收需要切到 `sherpa_onnx_asr`。
4. 第一次使用本地 ASR provider 时可能有冷启动延迟。`persistent_provider=true` 后，后续识别会复用常驻 recognizer。
5. `ScriptProcessorNode` 有弃用警告，但当前仍可用于 M4 联调。迁移 `AudioWorklet` 不属于 M4。
6. M4 不处理半截 AI 回复的历史、记忆和 TTS 副作用治理。这些内容属于 M5。

#### Git 记录

主仓库 M4 相关提交：

```text
78d65d8 feat(M4): 增加 ASR 常驻与 VAD 联调修正
a19f2eb feat(M4): implement silero vad provider
e7c88a6 feat(M4): validate traditional asr wav upload contracts
3e5db28 feat(M4): add sherpa onnx asr provider
af85913 fix(M4): update frontend VAD error handling
21ae84e feat(M4): filter invalid ASR handoff
413ebef feat(M4): update frontend transcript handling
6208c90 feat(M4): auto submit ASR transcript chat
700e564 feat(M4): transcribe speech end audio
c7ab12e feat(M4): cancel chat task on speech start
bd5e2d9 feat(M4): add chat generation state
dc786fc docs(M4): update impliment plan for M4 and M5 in VAD.
```

前端子模块 M4 相关提交：

```text
4c51cee fix(M4): 设置 VAD 错误提示自动清除
93ddbac feat(M4): upload traditional asr recordings as pcm wav
cd364a3 fix(M4): show realtime VAD backend errors
5569e7f feat(M4): display ASR transcript events
```

### 5. 后续

M4 后续只保留人工联调验收，不再继续扩展功能。

建议分支策略：

1. `feat/vad-realtime-interrupt` 保留为 M4 验收分支。
2. 从当前 HEAD 新建 `feat/vad-dev`，用于 M5 开发。
3. M4 验证如果发现 bug，先回到 `feat/vad-realtime-interrupt` 修复并提交。
4. M5 分支通过 `rebase feat/vad-realtime-interrupt` 吸收 M4 修复。
5. M4 验收通过后，继续在 `feat/vad-dev` 推进 M5。

M5 将处理：

1. 被打断的半截 AI 回复如何展示为 interrupted 消息。
2. `chat_history` 如何保存 `interrupted=true`。
3. 记忆系统如何跳过 interrupted AI 消息。
4. 旧 generation 的 REST TTS 请求返回后如何丢弃结果。

## 2026-06-19: M5 打断语义与副作用治理完成

### 1. 背景与目标

M4 已经能在 `speech_start` 时取消旧 LLM task，并用 `generation_id` 阻止旧输出继续进入正常完成路径。但 M4 只解决“旧任务如何停下”和“新语音如何接管”，没有定义旧回复已经输出到一半时该如何处理。

M5 的目标是让“被打断”成为一等语义：

1. 已经发送给前端的旧 LLM 文本要能作为半截回复保留下来。
2. 半截回复要能展示给用户，并明确标记为被 VAD 打断。
3. 半截回复要进入 `chat_history` 审计归档，方便回看和排查。
4. 半截回复不能作为正常完成的 AI 回复进入短期记忆有效轮次。
5. 旧 generation 的 TTS 播放结果返回后不能继续播放。

### 2. 方案与决策

#### 考虑过的方案

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| 打断后直接丢弃半截 AI 回复 | 实现最简单 | 用户看不到刚才被打断的上下文，也不利于审计 |
| 使用前端已展示文本作为 `partial_reply` | 更接近 OLV 的 `heard_response` 思路 | 第一版需要新增前端回传协议，链路更复杂 |
| 使用后端已发送 chunk 累积值作为 `partial_reply` | 后端可控，不需要新增前端回传 | 只能代表“已发送到前端”，不等同于“用户已听完” |

#### 决策理由

M5 第一版采用“后端已发送 chunk 累积值”作为 `partial_reply` 的唯一来源。后端只有在 chunk 已经通过 WebSocket 发给前端后，才把它记录到当前 generation 的 partial buffer。

这保证了 `output:chat:interrupted` 的内容不会包含尚未对前端可见的模型输出。它也避免了 M5 引入 OLV 式 `heard_response` 回传，把句子级 TTS 和播放确认留到 M7 再讨论。

`interrupted=true` 的 AI 回复采用双层处理：

1. 写入前端展示历史和 `chat_history` session 归档。
2. 不进入 `short_term_memory.recent_messages`，不增加有效轮次，不触发记忆压缩。

### 3. 改动详情

#### 3.1 核心变更

1. 扩展 WebSocket 生成状态。
   - 每个连接记录当前 `generation_id`、`chat_id`、`character_id` 和用户原始输入。
   - 每个连接累积已经发送给前端的 LLM chunk。
   - 正常 complete 或 generation 失效时释放 partial buffer。

2. 增加 `output:chat:interrupted`。
   - VAD 触发 `speech_start` 后，后端先让旧 generation 失效。
   - 如果旧 generation 已经发送过文本，后端生成 interrupted snapshot。
   - 后端发送 `output:chat:interrupted`，携带 `partial_reply`、`generation_id` 和 `reason`。

3. 持久化 interrupted 元数据。
   - 前端展示历史写入 `generation_id`、`interrupted=true`、`interrupt_reason=vad_speech_start`。
   - `chat_history` session 归档写入同样的 metadata。
   - storage 层只允许白名单元数据：`generation_id`、`interrupted`、`interrupt_reason`。

4. 调整记忆系统策略。
   - `interrupted=true` 的 AI 消息不视为有效轮次。
   - `short_term_memory.recent_messages` 不记录该半截 AI 回复。
   - `total_rounds` 不因 interrupted 回复增加。
   - `append_turn()` 仍会把该消息写入 `chat_history`，用于审计。

5. 调整前端 streaming 状态。
   - 前端识别 `output:chat:interrupted`。
   - 当前 streaming 回复结束为 interrupted 消息。
   - 历史加载时保留 `generation_id`、`interrupted` 和 `interrupt_reason` 字段。
   - 消息列表对 interrupted 回复显示打断标记。

6. 调整 TTS 副作用处理。
   - 前端 audio player 记录 active generation。
   - 收到 `control:interrupt` 或 `output:chat:interrupted` 后，使旧 generation 失效。
   - 旧 generation 的 REST TTS 请求即使稍后返回，也不会继续入队播放。

#### 3.2 协议 / 数据结构变更

新增服务端到前端消息：

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

展示历史中的 AI 消息新增可选字段：

```json
{
  "role": "ai",
  "content": "半截回复",
  "name": "atri",
  "generation_id": "old generation id",
  "interrupted": true,
  "interrupt_reason": "vad_speech_start"
}
```

#### 3.3 文件清单

主仓库：

- `src/routes/chat_ws.py`
  - 增加 interrupted snapshot、partial reply 累积、`output:chat:interrupted` 发送和旧 generation 副作用丢弃。
- `src/routes/chats.py`
  - 聊天历史响应模型暴露 interrupted metadata。
- `src/storage/interface.py`
  - 为 append message 接口增加 metadata 参数。
- `src/storage/json_storage.py`
  - 持久化允许的 interrupted metadata。
- `src/storage/db_storage.py`
  - 同步数据库占位实现的接口签名。
- `src/memory/chat_history.py`
  - `append_ai()` 支持写入 `generation_id`、`interrupted` 和 `interrupt_reason`。
- `src/memory/manager.py`
  - interrupted AI 消息只做审计归档，不进入有效轮次。
- `tests/routes/test_chat_ws.py`
  - 覆盖 speech_start 打断、partial reply 持久化和 interrupted 事件。
- `tests/storage/test_json_storage.py`
  - 覆盖 metadata 白名单持久化。
- `tests/memory/test_manager.py`
  - 覆盖 interrupted 回复不进入 short-term memory。

前端子模块：

- `frontend/src/utils/websocket.ts`
  - 分发 `output:chat:interrupted`。
- `frontend/src/composables/useWebSocket.ts`
  - 消费 interrupted 事件并更新聊天状态。
- `frontend/src/stores/chat.ts`
  - 支持 interrupted streaming 收尾。
- `frontend/src/composables/useAudioPlayer.ts`
  - 按 `generation_id` 丢弃旧 TTS 结果。
- `frontend/src/components/chat/MessageItem.vue`
  - 展示 interrupted 回复标记。
- `frontend/src/api/types.ts`、`frontend/src/types/message.ts`、`frontend/src/composables/useChat.ts`
  - 补齐 interrupted metadata 类型和历史加载映射。

### 4. 验证

#### 终端 WebSocket 抓包

使用专用测试 chat 进行端到端抓包，不依赖浏览器 DevTools：

```text
chat_id=20260618_c2f738e7
```

测试流程：

1. 终端 WebSocket 连接 `ws://localhost:8430/ws`。
2. 发送第一轮 `input:text`，让 LLM 开始流式输出。
3. 收到若干 `output:chat:chunk` 后，发送真实 `zh.wav` 音频 chunk。
4. 等待 Silero VAD 检测到 `speech_start`。
5. 捕获 `control:interrupt` 和 `output:chat:interrupted`。
6. 再发送第二轮 `input:text`。
7. 等待第二轮正常 `output:chat:complete`。

抓包摘要：

```text
first_generation_id=1e8c9519dc0846a09068cebae2a12a53
first_chunk_count=6
audio_chunks_sent=11
listen_states=['silence', 'silence', 'silence', 'silence', 'silence', 'silence', 'silence', 'silence', 'silence', 'silence', 'speech_start', 'speech_end']
interrupt_seen=True
chat_interrupted_seen=True
first_complete=False
stale_after_interrupt_count=0
second_generation_id=466ccc08c2674590aa2df438af0638dc
second_chunk_count=57
second_complete=True
```

关键抓包结果：

```text
control:listen-state state=speech_start
control:interrupt gen=1e8c9519dc0846a09068cebae2a12a53 reason=speech_start
output:chat:interrupted gen=1e8c9519dc0846a09068cebae2a12a53 reason=vad_speech_start partial=主人！亚托莉看到了
```

验收结论：

1. 第一轮 LLM 文本已开始流式输出。
2. VAD `speech_start` 能打断正在输出的 LLM generation。
3. 旧 generation 没有继续发送 `output:chat:complete`。
4. 打断后没有旧 generation 的 chunk 泄漏。
5. 第二轮新 generation 可以继续流式输出并正常 complete。

#### 数据落盘验证

前端展示历史中可以看到 interrupted metadata：

```text
data/chats/default/atri/sessions/20260617_9f2b0f00.json
```

关键字段：

```json
{
  "generation_id": "136af20c3b604a31923b4b735da7fc0b",
  "interrupted": true,
  "interrupt_reason": "vad_speech_start"
}
```

`chat_history` session 归档也保留同一条 interrupted AI 回复：

```text
data/characters/default/atri/chats/20260617_9f2b0f00/sessions/2026-06-18_f6cc0e36.json
```

`short_term_memory.json` 的 `recent_messages` 不包含这条 half reply，符合“可展示、可审计、不参与记忆压缩”的 M5 决策。

#### 测试结果

```bash
uv run pytest tests/routes/test_chat_ws.py tests/storage/test_json_storage.py tests/memory/test_manager.py -q
```

```text
122 passed
```

#### 代码检查

```bash
uv run python -m mypy src/ --ignore-missing-imports
uv run ruff check src/memory/chat_history.py src/memory/manager.py src/routes/chat_ws.py src/routes/chats.py src/storage/db_storage.py src/storage/interface.py src/storage/json_storage.py tests/memory/test_manager.py tests/routes/test_chat_ws.py tests/storage/test_json_storage.py
```

结果：通过。

前端验证：

```bash
npm run type-check
npm run lint
npm run build
```

结果：

```text
type-check: passed
lint: 0 errors, 2 existing warnings
build: passed
```

既有 lint warning：

```text
src/components/airi-ui/TransitionVertical.vue
  74:14  warning  Unexpected any. Specify a different type
  75:13  warning  Unexpected any. Specify a different type
```

### 5. Git 记录

主仓库：

```text
337dc8b feat(M5): 完成 VAD 打断语义治理
```

前端子模块：

```text
f9004b9 feat(M5): 完成前端打断状态处理
```

本次提交未纳入以下本地内容：

```text
config/asr_config.yaml
docs/developments/wiki/Storage/
```

`config/asr_config.yaml` 是当前 ASR provider 的本地运行配置；`docs/developments/wiki/Storage/` 是未整理 Storage 草稿目录。

### 6. 后续

M5 的主要开发和联调已完成。下一步进入 M6：配置、测试与文档补齐。

M6 需要重点处理：

1. 整理配置文档，明确 `web_speech_api`、`sherpa_onnx_asr`、`silero_vad` 的适用边界。
2. 补齐实时语音模式的使用说明和浏览器 WebSocket 验收路径。
3. 更新 VAD wiki 中的最终验收标准。
4. 汇总已有测试和前端检查入口，暂不更新 `tests/*/test-exe.md`。
5. 检查是否需要保留终端 WS 抓包脚本为临时验收工具，或只记录命令与结果。

## 2026-06-19: M6 配置与使用文档补齐

### 1. 背景与目标

M4/M5 已经完成实时语音打断、ASR 自动接管、LLM generation 打断、interrupted 历史和记忆策略。进入 M6 后，主要问题不是继续扩展功能，而是让配置、使用方法和验收路径可查。

本次 M6 文档收尾的目标：

1. 让维护者能快速理解 `config/vad_config.yaml` 的字段含义。
2. 让使用者能知道实时语音 button 怎么开启、怎么验证。
3. 说明 `web_speech_api`、`sherpa_onnx_asr`、`silero_vad` 三者在 VAD 闭环中的边界。
4. 记录当前 Silero 防抖和静默结束时间的计算方式。
5. 保留现有测试和构建检查入口，但本轮不更新 `tests/*/test-exe.md`。

### 2. 方案与决策

#### 考虑过的方案

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| 只在 VAD wiki 中继续补说明 | 改动集中 | 使用者不容易在配置文档目录找到入口 |
| 新增正式配置文档和使用说明 | 更接近现有 ASR/TTS 文档结构，便于发布 | 需要维护中英文两套文档 |
| 同步更新 `tests/*/test-exe.md` | 测试入口更完整 | 当前用户判断这些文件暂不需要补充，容易产生无效文档 churn |

#### 决策理由

M6 采用“正式配置文档 + 使用说明 + wiki 状态同步”的方式。`tests/*/test-exe.md` 本轮不修改；现有测试命令和验收方式记录在配置文档、使用说明和本开发日志中。

### 3. 改动详情

#### 3.1 核心变更

1. 新增 VAD 配置说明。
   - 解释 `enabled`、`vad_model`、`sample_rate`、`pre_buffer_ms`。
   - 区分 `fake` 和 `silero_vad` 两个 Provider。
   - 说明 Silero 32 ms 内部窗口、防抖和静默结束延时。
   - 说明 VAD 与 ASR 的关系，以及 `web_speech_api` 的限制。

2. 新增实时语音模式使用说明。
   - 区分传统按钮式 ASR 和实时 VAD button。
   - 说明 button 启用条件。
   - 给出浏览器 DevTools WebSocket 验收路径。
   - 说明 `control:interrupt`、`output:asr:transcript`、`output:chat:interrupted` 的验收意义。

3. 更新实施计划。
   - 将 M6 当前收尾范围明确为发布文档和人工验收入口。
   - 记录本轮不更新 `tests/*/test-exe.md`。
   - 补齐 M6 文档验收标准。

#### 3.2 文件清单

- `docs/configs/CN/VAD配置说明.md`
  - 新增中文 VAD 配置说明。
- `docs/configs/EN/VAD-configuration.md`
  - 新增英文 VAD 配置说明。
- `docs/configs/CN/实时语音模式使用说明.md`
  - 新增中文实时语音模式使用说明。
- `docs/configs/EN/realtime-voice-mode.md`
  - 新增英文实时语音模式使用说明。
- `docs/developments/wiki/VAD/vad-implementation-plan.md`
  - 同步 M6 当前执行范围和验收标准。
- `docs/developments/wiki/VAD/development.md`
  - 记录本次 M6 文档收尾。

### 4. 验证

#### 文档检查

本次是文档改动，没有新增运行时代码。验证重点是：

1. 新增文档路径位于正式 `docs/` 目录。
2. 配置字段与当前 `config/vad_config.yaml`、`config/asr_config.yaml` 对齐。
3. 使用说明中的 WebSocket 消息顺序与 M4/M5 联调结果一致。
4. M6 计划已明确不更新 `tests/*/test-exe.md`。

#### 可回归命令

后端检查入口：

```bash
uv run pytest tests/vad tests/routes/test_chat_ws.py tests/routes/test_asr.py -q
```

前端检查入口：

```bash
cd frontend
npm run type-check
npm run lint
npm run build
```

### 5. 后续

M6 后续如果继续推进，优先做两件事：

1. 根据用户联调反馈微调 VAD/ASR 配置文档。
2. 决定是否保留终端 WebSocket 抓包脚本作为开发者验收工具。

### 6. 里程碑边界更新

2026-06-19 进一步确认：原计划中的 M7 不再作为 VAD MVP 的后续里程碑。TTS 流式化会作为一次独立开发处理，后续应单独建立分支、设计文档和验收标准。

当前 VAD 第一版完成边界保持为 M0-M6：

1. 实时麦克风输入。
2. 后端 VAD 判断。
3. `speech_start` 打断 LLM 流式输出和当前 TTS 播放。
4. `speech_end` 后端 ASR 自动接管。
5. interrupted 历史、记忆和旧 TTS 结果治理。
6. 配置、使用说明和 README 文档入口。

TTS 流式化后续单独推进，建议分支名为 `feat/tts-streaming` 或 `feat/tts-websocket-streaming`。
