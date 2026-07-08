# ATRI TTS 分段流式化实施文档

状态：待实施  
日期：2026-07-08  
前置设计：`docs/developments/wiki/TTS/tts-stream-design.md`

本文定义 TTS streaming 的落地步骤、代码位置、模块职责和验收方式。实现时以设计文档为准，不引入 provider 原生流式 TTS，也不引入 `heard_response`。

## 1. 实施边界

第一版只做应用层分段流式化：

```text
LLM 文本 chunk
  -> 后端按句子或短停顿切段
  -> 每段调用现有 TTSService.synthesize()
  -> 后端通过 WebSocket 下发完整小音频
  -> 前端按 sequence 播放
```

不做：

1. 不实现 `TTSInterface.synthesize_stream()`。
2. 不改写各 provider 的核心合成逻辑。
3. 不引入 `heard_response`。
4. 不让 TTS 播放进度影响聊天历史、记忆或 interrupted partial reply。
5. 不保证外部 provider 请求发出后可被真正取消。

## 2. 目标代码位置

后端新增文件：

```text
src/tts/sentence_divider.py
src/tts/segment_manager.py
tests/tts/test_sentence_divider.py
tests/tts/test_segment_manager.py
tests/tts/test-exe.md
```

后端修改文件：

```text
pyproject.toml
uv.lock
config/tts_config.yaml
src/tts/config.py
src/routes/chat_ws.py
tests/routes/test_chat_ws.py
```

前端修改文件：

```text
frontend/src/utils/websocket.ts
frontend/src/composables/useWebSocket.ts
frontend/src/composables/useAudioPlayer.ts
frontend/src/stores/tts.ts
```

可选前端测试位置：

```text
frontend/src/composables/__tests__/useAudioPlayer.spec.ts
frontend/src/utils/__tests__/websocket.spec.ts
```

## 3. 依赖与配置

### 3.1 新增依赖

使用 `uv` 增加后端依赖：

```bash
uv add pysbd
```

`pysbd` 只用于应用层文本切分。不要把它放到 provider 内部。

### 3.2 tts_config.yaml

在 `config/tts_config.yaml` 顶层新增：

```yaml
streaming:
  enabled: false
  segment_method: pysbd
  faster_first_response: true
  max_concurrent_synthesis: 2
  max_pending_segments: 12
```

该配置是 ATRI 应用层 streaming 开关。它不同于 provider 配置里的 `stream` 或 `streaming_mode`。

### 3.3 默认配置

在 `src/tts/config.py` 的 `DEFAULT_TTS_CONFIG` 中加入相同默认值：

```python
"streaming": {
    "enabled": False,
    "segment_method": "pysbd",
    "faster_first_response": True,
    "max_concurrent_synthesis": 2,
    "max_pending_segments": 12,
},
```

开启 TTS streaming 的必要条件：

```text
tts.enabled == true
tts.auto_play == true
tts.streaming.enabled == true
```

如果任一条件不满足，后端不创建 `TTSSegmentManager`，前端继续使用当前 REST 自动 TTS 或不自动朗读。

## 4. sentence_divider.py

`src/tts/sentence_divider.py` 负责把 LLM chunk 累积成可合成文本段。

建议定义：

```python
@dataclass(frozen=True)
class TTSTextSegment:
    segment_id: str
    sequence: int
    display_text: str
    tts_text: str


class SentenceDivider:
    def feed(self, chunk: str) -> list[TTSTextSegment]: ...
    def flush(self) -> list[TTSTextSegment]: ...
    def reset(self) -> None: ...
```

实现规则：

1. `feed()` 只接收新增 chunk，不接收完整回复。
2. 内部维护 buffer。
3. 第一段在 `faster_first_response=true` 时可按短停顿切出。
4. 后续段落按 `pysbd` 判断的句子边界切出。
5. `flush()` 在 LLM 完成或任务取消前调用，输出剩余 buffer。
6. 空白文本、纯标点文本不生成 segment。

句末边界字符在中文子集基础上增加英文、日文常用符号：`。！？!?…．.｡`。短停顿字符为 `，,、､；;：:`，只用于 `faster_first_response=true` 时的第一段提前切出。

第一版不做长度兜底切分。若 provider 对单段长度敏感，后续再增加 `max_segment_chars`。

## 5. segment_manager.py

`src/tts/segment_manager.py` 放置 `TTSSegmentManager`。

它是 TTS 应用层编排器，不是 provider，也不是 route helper。

建议核心结构：

```python
@dataclass(frozen=True)
class TTSAudioSegment:
    chat_id: str
    character_id: str
    generation_id: str
    segment_id: str
    sequence: int
    display_text: str
    tts_text: str
    audio: bytes
    media_type: str


class TTSSegmentManager:
    async def feed_text(self, chunk: str) -> None: ...
    async def finish(self) -> None: ...
    async def interrupt(self) -> None: ...
    async def close(self) -> None: ...
```

构造参数应包含：

1. `tts_service: TTSService`
2. `chat_id`
3. `character_id`
4. `generation_id`
5. streaming 配置
6. `send_segment` 回调
7. `send_complete` 回调
8. `send_error` 回调

### 5.1 并发与排序

`max_concurrent_synthesis` 控制同时合成的 segment 数量。

合成可以并发，但下发必须有序：

```text
sequence 0 合成慢
sequence 1 合成快
  -> 先缓存 sequence 1
  -> 等 sequence 0 下发后再下发 sequence 1
```

manager 内部维护：

```text
next_sequence_to_send
completed_segments: dict[int, TTSAudioSegment]
pending_tasks: set[asyncio.Task]
interrupted: bool
```

后端是 ordered delivery 的权威来源。前端使用 `sequence` 做校验和调试，不承担复杂重排职责。

### 5.2 interrupt

`interrupt()` 必须做到：

1. 设置 `interrupted=true`。
2. 取消尚未完成的 segment task。
3. 清空 `completed_segments`。
4. 阻止后续 `output:audio:segment` 和 `output:audio:complete`。
5. 对已经无法取消的 provider 请求，在返回后直接丢弃。

这只影响 TTS 音频，不修改聊天历史，不生成 interrupted 消息。

### 5.3 finish

`finish()` 在 LLM 正常结束后调用。

它应：

1. 调用 `SentenceDivider.flush()` 产出剩余文本。
2. 等待已创建的 TTS task 完成或失败。
3. 按 sequence 发送所有可用 segment。
4. 发送 `output:audio:complete`。

`output:chat:complete` 不等待 TTS 失败重试，也不因 TTS 失败回滚。

## 6. chat_ws.py 接入

### 6.1 WebSocketVADState 扩展

当前 `WebSocketVADState` 负责 LLM generation 和 VAD 打断。TTS streaming 需要增加独立的 TTS lifecycle。

建议新增字段：

```python
current_tts_generation_id: str | None = None
current_tts_manager: TTSSegmentManager | None = None
```

注意：LLM generation tracking 和 TTS active lifecycle 不能混用。

当前 `complete_generation(generation_id)` 会在 `output:chat:complete` 后释放 LLM 文本跟踪。但 TTS 音频可能还在合成或播放。因此：

1. `current_generation_id` 表示 LLM 文本是否仍能产生聊天副作用。
2. `current_tts_generation_id` 表示当前是否还有可被 VAD interrupt 清理的 TTS 音频任务。
3. 文本 complete 后可以清理 `current_generation_id`。
4. 音频 complete 后才清理 `current_tts_generation_id`。

这样可以处理“LLM 文本已经完成，但 TTS 还在播放时用户开口”的情况。

### 6.2 创建 manager

在 `_handle_chat_message()` 开始处理新 generation 后，判断是否开启 streaming：

```text
TTS module enabled
  && auto_play enabled
  && streaming.enabled
```

满足条件时创建 `TTSSegmentManager`，并挂到 `vad_state.current_tts_manager`。

如果创建失败，只记录 warning 并继续文本聊天。TTS streaming 失败不能阻止 LLM 回复。

### 6.3 LLM chunk 接入

当前 chunk 发送逻辑位于 LLM stream 循环中。新增调用顺序：

```text
检查 generation 仍有效
发送 output:chat:chunk
append_generation_reply()
把同一个 chunk 交给 TTSSegmentManager.feed_text()
```

推荐只在 chat chunk 成功发送给前端后再喂给 TTS manager。这样 TTS 始终消费“已经发送给前端的文本”。

### 6.4 LLM complete 接入

文本完成时：

```text
持久化聊天历史和记忆
发送 output:chat:complete
释放 LLM generation tracking
调用 TTSSegmentManager.finish()
```

`finish()` 可以在同一个 chat task 后半段继续运行，也可以由 manager 内部 background task 运行。无论哪种方式，WebSocket close 时都必须 `close()`。

如果希望 `output:chat:complete` 更快到达前端，不能在发送 complete 前等待所有 TTS 任务完成。

### 6.5 VAD interrupt 接入

在 speech_start interrupt 路径中同时处理两类任务：

```text
取消当前 LLM task
使当前 LLM generation 失效
interrupt 当前 TTS manager
发送 control:interrupt
```

如果 LLM generation 已经完成但 TTS manager 仍存在，`control:interrupt` 应优先携带 `current_tts_generation_id`。这样前端能精准清理对应 generation 的音频队列。

如果两者都不存在，则仍发送不带 `generation_id` 的 interrupt，让前端停止当前本地播放。

### 6.6 WebSocket close

WebSocket 断开时必须调用：

```text
current_chat_task.cancel()
current_tts_manager.close()
VADSession release
```

不要让 TTS provider 请求完成后继续尝试向已关闭 WebSocket 发送音频。

## 7. WebSocket 协议接入

后端新增发送事件：

```text
output:audio:segment
output:audio:complete
output:audio:error
```

字段以设计文档为准。发送前统一检查：

1. WebSocket 仍 connected。
2. manager 未 interrupted。
3. segment 的 `generation_id` 等于 manager 的 generation。

不要把音频事件塞进 `output:chat:*`。

## 8. 前端接入

### 8.1 websocket.ts

在 `frontend/src/utils/websocket.ts` 增加分发：

```text
output:audio:segment  -> audio:segment
output:audio:complete -> audio:complete
output:audio:error    -> audio:error
```

未知事件仍保持 warning，不抛异常。

### 8.2 useWebSocket.ts

新增音频事件监听。

`audio:segment`：

1. 校验 `generation_id`。
2. 将 base64 音频转成 `Blob`。
3. 调用 `audioPlayer.enqueueAudioSegment()`。

`audio:error`：

1. 记录错误。
2. 通知 player 跳过该 sequence。

`audio:complete`：

1. 标记当前 generation 的 streaming audio 完成。
2. 不改变聊天文本状态。

`chat:complete`：

```text
如果 tts.streaming.enabled == true:
  不再调用 enqueueAutoSpeech()
否则:
  保持现有 REST auto TTS 路径
```

### 8.3 useAudioPlayer.ts

现有 player 已有 queue、`generationId`、VAD stale generation、interrupt epoch。需要扩展为可接收后端音频 segment。

建议新增：

```ts
enqueueAudioSegment(segment: {
  generationId: string
  segmentId: string
  sequence: number
  text: string
  audio: Blob
  mediaType: string
}): Promise<void>
```

第一版排序策略：

1. 后端保证 ordered delivery。
2. 前端按接收顺序入队。
3. 前端记录每个 generation 的 last queued sequence。
4. 发现重复 sequence 时丢弃。
5. 发现旧 generation 时丢弃。

VAD interrupt 到来时复用现有 `vadInterruptPlayback(generationId)`，停止当前音频并清空队列。

### 8.4 手动 TTS 保持 REST

用户点击历史消息播放、设置页测试、手动重播仍走当前 REST TTS。

手动 TTS 不依赖 `generation_id`，也不参与 streaming queue lifecycle。

## 9. 错误处理

### 9.1 单 segment 失败

单个 segment 合成失败时：

1. 后端发送 `output:audio:error`。
2. manager 跳过该 sequence。
3. 后续 sequence 继续发送。
4. 不影响 `output:chat:complete`。

### 9.2 TTS provider 不可用

如果 provider 不可用：

1. 记录 warning 或 error。
2. 对当前 segment 发送 `output:audio:error`。
3. 不中断聊天文本。
4. 不切换到 REST TTS 自动补偿。

第一版不做自动 fallback，避免重复朗读或乱序。

### 9.3 WebSocket 发送失败

发送失败时：

1. manager 标记 interrupted 或 closed。
2. 取消 pending tasks。
3. 不继续重试音频。

聊天 WebSocket 已断开时，重试音频没有意义。

## 10. 测试计划

### 10.1 后端单元测试

`tests/tts/test_sentence_divider.py`：

1. 普通中文句子按句号切分。
2. `faster_first_response=true` 时第一段可按逗号切出。
3. `faster_first_response=false` 时等待完整句子。
4. `flush()` 输出剩余 buffer。
5. 空白 chunk 不产生 segment。
6. 英文、日文常用句末符号可作为完整句边界。

`tests/tts/test_segment_manager.py`：

1. 单 segment 合成后发送 `output:audio:segment`。
2. 多 segment 并发完成乱序时，发送仍按 sequence。
3. `finish()` 发送 `output:audio:complete`。
4. `interrupt()` 后不再发送 segment。
5. provider 返回晚于 interrupt 时结果被丢弃。
6. segment 失败时发送 `output:audio:error` 并跳过。

### 10.2 后端 WebSocket 测试

扩展 `tests/routes/test_chat_ws.py`：

1. streaming disabled 时不发送 audio 事件。
2. streaming enabled 时 chunk 后产生 audio segment。
3. `output:chat:complete` 和 `output:audio:complete` 都能收到。
4. VAD interrupt 会取消当前 TTS manager。
5. LLM complete 后、audio complete 前触发 interrupt，仍能停止 TTS manager。

### 10.3 前端验证

最低要求：

```bash
cd frontend
npm run build
```

如已有类型检查或测试脚本，同步运行。

手动验证：

1. 开启 TTS streaming 后，AI 还没完整回复时开始播放第一段。
2. VAD interrupt 后当前音频停止，旧 segment 不再播放。
3. 关闭 TTS streaming 后，REST 自动 TTS 行为不变。
4. 手动点击历史 AI 消息播放仍可用。

### 10.4 test-exe.md

在 `tests/tts/test-exe.md` 写入：

1. 后端单元测试命令。
2. WebSocket 测试命令。
3. 前端构建命令。
4. 人工验收场景。
5. 预期结果。

## 11. 实施顺序

建议拆成多个 commit：

1. `feat(tts): add streaming config and sentence divider`
2. `feat(tts): add TTS segment manager`
3. `feat(tts): emit websocket audio segments`
4. `feat(frontend): play websocket TTS segments`
5. `test(tts): cover segmented synthesis lifecycle`
6. `docs(tts): add streaming acceptance guide`

每一步都保持 REST TTS 可用。

## 12. 验收标准

1. streaming disabled 时现有 REST TTS 不变。
2. streaming enabled 时，第一段音频可早于 `output:chat:complete` 播放。
3. 音频段携带 `generation_id`、`segment_id`、`sequence`。
4. 后端即使并发合成，也按 sequence 下发。
5. VAD interrupt 后旧 generation 音频不再播放。
6. LLM 文本 complete 后、TTS 音频仍在播放时，VAD interrupt 仍能清理 TTS。
7. TTS 失败不影响聊天文本保存、记忆写入或 interrupted partial reply。
8. 手动 REST TTS 仍可播放历史消息。
9. 后端 mypy、ruff、pytest 通过当前改动范围。
10. 前端构建或类型检查通过。
