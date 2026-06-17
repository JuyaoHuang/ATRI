# VAD 开发记录

本文是开发 blog，用于记录阶段性讨论、协议草案和实现进度；M0-M7 的职责划分与验收以 `docs/developments/wiki/VAD/vad-implementation-plan.md` 为准。

## 2026-06-15

### 1. WebSocket 协议扩展（M2）

M2 的目标是让后端聊天 WebSocket 认识实时语音输入消息，并能把音频 chunk 交给 `VADService`。M2 不实现前端麦克风采集，也不把语音交给真实 ASR；`output:asr:transcript` 在 M2 只定义和预留协议形态。

当前后端 WebSocket 已有统一消息结构：

```json
{
  "type": "消息类型",
  "data": {}
}
```

VAD 相关消息继续沿用这个结构。

#### 1.1 M2 新增消息类型

前端到后端：

| type | 作用 | M2 处理结果 |
| --- | --- | --- |
| `input:audio:chunk` | 发送一段实时麦克风音频 | 调用 `VADService.process_audio()` |
| `input:audio:end` | 通知本轮实时音频输入结束 | 清理或重置当前监听状态，不提交 ASR |

后端到前端：

| type | 作用 | 触发时机 |
| --- | --- | --- |
| `control:listen-state` | 返回 VAD 监听状态 | 每次处理音频 chunk 或输入结束 |
| `control:interrupt` | 通知前端立即打断播放/旧回复 | VAD 事件为 `speech_start` 时 |
| `output:asr:transcript` | 返回 ASR 转写文本 | M2 只定义和预留，真实触发属于 M4 |

#### 1.2 `input:audio:chunk`

前端发送实时音频片段。

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

字段定义：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | `string` | 是 | 当前聊天 ID。 |
| `character_id` | `string` | 是 | 当前角色 ID。 |
| `audio` | `number[]` | 是 | 音频片段。格式为 16 kHz、mono、PCM float array。 |
| `seq` | `number` | 否 | 客户端音频 chunk 序号，用于调试和排查丢包/乱序。 |

`audio` 的约束：

1. M2 主路径使用 `number[]`，不使用 `Blob`、`webm`、`wav bytes`。
2. 采样率目标为 16 kHz。
3. 单声道。
4. 数值通常在 `-1.0` 到 `1.0` 之间。
5. M2 后端只校验基本类型和非空，不负责浏览器侧重采样。

#### 1.3 `input:audio:end`

前端通知本轮实时语音输入结束。

```json
{
  "type": "input:audio:end",
  "data": {
    "chat_id": "chat_xxx",
    "character_id": "atri"
  }
}
```

字段定义：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | `string` | 是 | 当前聊天 ID。 |
| `character_id` | `string` | 是 | 当前角色 ID。 |

M2 中该消息只表示“实时输入结束”。后端可以返回监听状态并重置当前 VAD session，但不提交真实 ASR。ASR 衔接属于 M4。

#### 1.4 `control:listen-state`

后端返回当前监听状态。

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

字段定义：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | `string` | 是 | 当前聊天 ID。 |
| `character_id` | `string` | 是 | 当前角色 ID。 |
| `state` | `string` | 是 | VAD 语义状态。 |
| `is_speech` | `boolean` | 是 | 当前 chunk 是否被 provider 判断为语音。 |
| `seq` | `number` | 否 | 回传前端传入的 chunk 序号。 |
| `probability` | `number` | 否 | provider 返回的人声概率。fake provider 可返回近似值。 |
| `energy` | `number` | 否 | provider 返回或计算出的音频能量。 |
| `reason` | `string` | 否 | 错误或特殊状态说明。 |

`state` 枚举：

| state | 含义 |
| --- | --- |
| `speech_start` | 用户开始说话。 |
| `speech_chunk` | 用户仍在说话，或仍处于说话回合内。 |
| `speech_end` | 用户说话结束。 |
| `silence` | 当前没有有效语音。 |
| `error` | VAD 处理失败。 |

#### 1.5 `control:interrupt`

后端通知前端立即打断当前播放和旧回复处理。

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

字段定义：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | `string` | 是 | 当前聊天 ID。 |
| `character_id` | `string` | 是 | 当前角色 ID。 |
| `reason` | `string` | 是 | M2 固定为 `speech_start`。 |

`control:interrupt` 不等待 ASR 文本。只要后端 VAD 判断用户开始说话，就可以发送该控制事件。

#### 1.5.1 `output:asr:transcript`（M2 预留）

M2 预留 ASR 转写结果事件，便于 M4 接入真实 ASR 后沿用同一 WebSocket 协议。

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

M2 不要求由真实 ASR 触发该事件；实现上可以先提供消息结构、发送辅助函数或协议测试。

#### 1.6 打断触发规则

M2 采用以下规则：

1. `control:listen-state` 可以每个音频 chunk 都返回。
2. `control:interrupt` 只在 `speech_start` 时返回。
3. 同一轮连续说话期间，`control:interrupt` 只发送一次。
4. 用户说话结束并进入 `speech_end` 后，下一次 `speech_start` 可以再次触发 interrupt。
5. VAD 关闭时，`input:audio:chunk` 返回 `control:listen-state`，`state` 为 `silence`，并带上 disabled 语义。

#### 1.7 M2 后端会话状态

M2 需要为每个 WebSocket 连接维护轻量状态：

| 状态 | 作用 |
| --- | --- |
| `vad_session_id` | 标识当前连接的 VAD session。 |
| `audio_buffer` | 预留当前连接的音频缓存结构和清理路径，M2 不把它提交给 ASR。 |
| `current_chat_task` | 预留当前聊天生成任务引用。M2 可以先建立结构，M5 再真正取消。 |
| `interrupt_sent` | 防止同一轮连续说话重复发送 `control:interrupt`。 |
| `last_chat_id` | 记录最近一次语音消息关联的 chat。 |
| `last_character_id` | 记录最近一次语音消息关联的 character。 |

M2 需要有连接级音频缓存结构和断开清理路径，但不负责把完整语音缓存提交给 ASR。完整语音片段裁剪、有效音频判断和 ASR 提交属于 M4。

#### 1.8 M2 不做的事

M2 明确不做以下内容：

1. 不实现前端麦克风采集。
2. 不实现 AudioContext 或 AudioWorklet。
3. 不提交 ASR。
4. 不由真实 ASR 触发 `output:asr:transcript`。
5. 不真正取消 LLM task。
6. 不写入 `chat_history interrupted=true`。
7. 不修改 TTS 播放链路。
8. 不接入 Silero 真实模型推理。

这些内容分别属于 M3、M4、M5 或后续 provider 实现。

#### 1.9 M2 验收测试

M2 后端测试需要覆盖：

1. 现有 `input:text` 聊天行为不变。
2. VAD disabled 时，`input:audio:chunk` 返回 `control:listen-state`，状态为 `silence`。
3. VAD enabled 且 fake provider 连续命中后，返回 `speech_start`。
4. `speech_start` 时发送 `control:interrupt`，`reason` 为 `speech_start`。
5. 同一轮连续说话只发送一次 `control:interrupt`。
6. `input:audio:end` 可以重置当前监听状态。
7. 非法 `audio` 字段返回 `error` 消息或 `control:listen-state` 的 `error` 状态。
8. `output:asr:transcript` 协议结构或发送辅助能力已预留，但不依赖真实 ASR。

## 2026-06-17

### 2. M2 完成记录：WebSocket 实时语音控制层

状态：已完成  
范围：后端聊天 WebSocket 协议扩展  
对应里程碑：`docs/developments/wiki/VAD/vad-implementation-plan.md` 的 M2

#### 2.1 目标是什么

M2 的目标是让现有聊天 WebSocket 具备实时语音控制能力。它不负责完整语音对话闭环，而是先建立后端可以持续接收音频、判断 VAD 状态、发送控制事件、并维护连接级状态的基础层。

换句话说，M2 要解决的问题是：

1. 后端能识别实时音频消息，而不是把它误当成文字聊天。
2. 后端能把音频 chunk 交给 `VADService`。
3. 后端能在 `speech_start` 时立即发出 `control:interrupt`。
4. 后端能在 LLM 文本输出期间继续接收音频控制消息。
5. 后端能为后续 M4/M5 预留 ASR transcript 和 LLM task 管理结构。

M2 明确不做真实 ASR、真实 LLM task 取消、前端麦克风采集、TTS 链路修改和真实 Silero 推理接入。

#### 2.2 做了什么

本阶段完成了以下后端能力：

1. 增加 `input:audio:chunk` 消息处理。
2. 增加 `input:audio:end` 消息处理。
3. 增加 `control:listen-state` 监听状态返回。
4. 增加 `control:interrupt` 控制事件，并在 `speech_start` 时触发。
5. 确保同一轮连续说话只发送一次 `control:interrupt`。
6. 预留 `output:asr:transcript` 协议发送能力，但不接真实 ASR。
7. 为每个 WebSocket 连接维护 `VADSession` 标识。
8. 为每个 WebSocket 连接维护 `audio_buffer`，并在 `speech_end`、`input:audio:end`、连接清理时释放。
9. 为每个 WebSocket 连接维护 `current_chat_task` 引用，作为 M5 取消 LLM 回复的基础。
10. 将文字聊天处理调整为后台 task，使 WebSocket receive loop 在 LLM 输出期间仍能继续接收音频消息。
11. 为 WebSocket 输出增加连接级 `send_lock`，避免聊天后台 task 和 VAD 控制消息并发写同一个连接。
12. 补充 WebSocket 路由测试，覆盖音频消息、interrupt、缓存、ASR transcript 协议、聊天 task 引用和发送锁。

#### 2.3 最终效果怎么样

M2 完成后，后端聊天 WebSocket 已经从单纯的文本流通道，扩展为可以承载实时语音控制事件的通道。

当前效果是：

1. 文字聊天行为保持兼容。
2. 音频 chunk 可以独立进入 VAD 流程。
3. VAD disabled 时会返回 `silence` 监听状态，不影响现有功能。
4. fake VAD provider 检测到 `speech_start` 后，后端会发送 `control:interrupt`。
5. 同一轮连续说话不会重复打断。
6. `input:audio:end` 可以重置当前监听状态并清理音频缓存。
7. LLM 文本输出期间，WebSocket 仍能继续处理 `input:audio:chunk`。
8. 后端已经具备 M4 接入 ASR 和 M5 取消 LLM task 所需的协议与连接级状态基础。

这意味着 M2 已经完成“后端实时语音控制层”的建设。后续 M3 可以在前端接入实时麦克风输入，M4 再把 `speech_end` 后的音频缓存交给 ASR，M5 再把 `control:interrupt` 接到真正的 LLM task 取消和历史记录策略。

#### 2.4 验证结果

最近一次完整验证结果：

```bash
uv run ruff format src/routes/chat_ws.py tests/routes/test_chat_ws.py
uv run ruff check . --fix
uv run python -m mypy src/ --ignore-missing-imports
uv run pytest tests/routes/test_chat_ws.py -q
uv run pytest tests/ -q
```

测试结果：

```text
tests/routes/test_chat_ws.py: 14 passed
tests/: 391 passed, 4 deselected
```

#### 2.5 后续工作

M2 不再继续扩展真实语音闭环。后续工作按里程碑推进：

1. M3：前端实时麦克风输入，持续发送 `input:audio:chunk`。
2. M4：VAD 到 ASR 的衔接，`speech_end` 后提交完整语音段。
3. M5：LLM 生成打断，`speech_start` 后真正取消当前聊天 task。
