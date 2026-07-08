# ATRI TTS 分段流式化设计

状态：设计冻结前草案  
日期：2026-07-08  
适用范围：VAD 第一版完成后的独立 TTS streaming 开发

本文描述 ATRI 后续如何把当前“完整文本 -> REST TTS -> 完整音频”的播放方式，升级为“LLM 文本流 -> 分段合成 -> WebSocket 下发音频段 -> 前端按序播放”。

这里的 TTS streaming 指应用层分段流式化，不指 provider 原生音频流式合成。

## 1. 核心原则

TTS 是 LLM 文本回复的下游消费者，不是对话状态的控制者。

因此第一版设计遵守以下规则：

1. 聊天历史保存的是 AI 已经发送或显示给前端的文本。
2. 记忆系统只根据聊天文本和 interrupted metadata 决定是否写入。
3. TTS 播放状态不反向修改聊天历史、记忆、LLM generation 有效性。
4. TTS 失败、延迟、被停止或被 VAD 打断，不改变 `output:chat:*` 文本协议的语义。
5. 第一版不引入 `heard_response`，也不要求前端回传“用户实际听到了哪一段”。

这个原则意味着：TTS 可以更早开始合成和播放，也可以在打断时清空旧音频队列，但它不能决定本轮 AI 回复到底保存哪些文本。

## 2. 背景

### 2.1 当前 ATRI TTS 链路

当前链路是完整回复完成后再合成：

```text
LLM 完整回复完成
  -> 前端拿到完整 AI 文本
  -> 前端调用 REST /api/tts/synthesize
  -> 后端 TTSService.synthesize() 返回完整音频
  -> 前端创建 audio URL 并播放
```

这个方式实现简单，但有两个限制：

1. 用户必须等完整 LLM 回复结束后才能听到声音。
2. VAD 打断时只能停止前端当前播放，不能统一清理后端已经排队的后续 TTS 片段。

### 2.2 OLV 参考结论

Open-LLM-VTuber 的主要思路不是依赖 provider 原生流式 TTS，而是：

```text
LLM token/text stream
  -> 累积成句子或短段
  -> 每段单独调用 TTS provider 生成完整小音频
  -> WebSocket 下发音频 payload
  -> 前端按 sequence 顺序播放
```

OLV 的“流式感”主要来自分段合成和分段下发，而不是音频字节边生成边播放。

ATRI 第一版采用这个方向，但不照搬 OLV 的 `heard_response` 反馈链路。

## 3. 目标

第一版 TTS streaming 目标：

1. 在 LLM 还没完全结束时，让用户尽早听到第一段语音。
2. 复用现有 TTS provider 的完整小段合成能力。
3. 通过 WebSocket 下发音频段，避免前端等到 `output:chat:complete` 后才发起 REST TTS。
4. 每个音频段绑定 `generation_id`，VAD interrupt 后丢弃旧 generation 的音频结果。
5. 前端按 `sequence` 播放，interrupt 时停止当前音频并清空队列。
6. 保留 REST TTS，继续服务手动播放历史消息、测试入口和 streaming disabled fallback。

非目标：

1. 不实现 provider 原生 `synthesize_stream()`。
2. 不重写所有 TTS provider。
3. 不引入 `heard_response`。
4. 不让 TTS 播放结果反向影响聊天历史或记忆。
5. 不保证取消已经发给外部 provider 的 HTTP/API 请求，只保证返回后按 generation 失效规则丢弃。

## 4. 总体链路

目标链路如下：

```text
用户输入或 ASR 自动提交
  -> 后端创建新的 generation_id
  -> LLM 开始输出文本 chunk
  -> 后端继续发送 output:chat:chunk 给前端显示
  -> 同一份文本 chunk 进入 TTS SentenceDivider
  -> SentenceDivider 产出可合成的文本段
  -> TTSSegmentManager 创建分段合成任务
  -> TTSService.synthesize() 合成完整小音频
  -> 后端检查 generation_id 仍然有效
  -> 后端发送 output:audio:segment
  -> 前端按 sequence 入队和播放
```

LLM 文本流和 TTS 音频流是并行消费者关系：

```text
LLM chunk
  -> 聊天显示 / 历史 partial_reply
  -> TTS 分段器 / 音频合成
```

其中聊天显示和历史记录仍以 `output:chat:*` 为准。TTS 只是消费同一份文本，不拥有对话状态。

## 5. 分段策略

第一版引入 `pysbd` 做句子边界检测。

分段规则：

1. LLM chunk 持续追加到当前文本 buffer。
2. `pysbd` 判断 buffer 中是否已经形成完整句子。
3. 有完整句子时，产出一个 TTS segment。
4. LLM complete 时，flush 剩余 buffer，即使它不是完整句子。
5. 每个 segment 都有递增 `sequence`，用于播放顺序。

句子边界字符以中文常用句末符号为基础，同时兼容英文和日文常用句末符号，例如 `。！？!?…．.｡`。`pysbd` 仍负责实际边界识别，字符集合只作为 ATRI 判断“该片段是否可发出”的收口条件。

每个 segment 保留两份文本：`display_text` 是已经发送给前端的原始文本，`tts_text` 是进入 TTS 合成的清洗文本。`tts_text` 会移除 `（...）`、`(...)`、`[...]`、`【...】` 包裹的动作或注释文本；如果清洗后没有可朗读内容，该 segment 不进入 TTS 合成。

### 5.1 faster_first_response

`faster_first_response` 是可选能力。

开启后，第一段语音可以在逗号、顿号、分号、冒号等较短停顿处提前切出，而不必等待完整句号。短停顿字符同样兼容中文、英文和日文常用写法，例如 `，,、､；;：:`。

示例：

```text
关闭 faster_first_response:
  "你好，我刚才在整理资料。" -> 等完整句子后合成

开启 faster_first_response:
  "你好，" -> 可作为第一段先合成
  "我刚才在整理资料。" -> 后续按句子合成
```

第一版只把这个行为作为可配置选项，不强制开启。开启后可以降低首段语音等待时间，但可能让第一段更短，语音自然度略差。

## 6. 后端设计

### 6.1 新增 TTSSegmentManager

建议在 WebSocket 对话链路中增加一个按 generation 管理的 TTS segment manager。

代码位置：

```text
src/tts/segment_manager.py      # TTSSegmentManager，负责任务编排、并发、排序、取消
src/tts/sentence_divider.py     # pysbd 分句封装，负责从 LLM chunk 中切出可合成文本段
tests/tts/test_segment_manager.py
tests/tts/test_sentence_divider.py
```

`src/routes/chat_ws.py` 只持有当前 WebSocket/generation 的 manager 引用，并在 LLM chunk、LLM complete、VAD interrupt、WebSocket close 等生命周期点调用它。分段、排队、并发合成和 ordered delivery 不写进 route。

职责：

1. 接收 LLM 输出 chunk。
2. 维护当前 generation 的分段 buffer。
3. 产出 `display_text` 和 `tts_text`。
4. 为每个 segment 分配 `segment_id` 和 `sequence`。
5. 调用现有 `TTSService.synthesize()`。
6. 限制并发合成数量，避免 provider 被过量请求。
7. 保证音频按 sequence 下发。
8. 在 generation 失效或 WebSocket 断开时取消未完成任务。
9. 对已经无法取消的 provider 请求，返回后执行 stale generation 丢弃。

### 6.2 generation 绑定

每个音频 segment 必须绑定：

1. `chat_id`
2. `character_id`
3. `generation_id`
4. `segment_id`
5. `sequence`

VAD `speech_start` 到来后，当前 generation 会失效。此后旧 generation 的 TTS 结果即使返回，也不得发送给前端播放。

如果某些音频已经发给前端，前端仍会在收到 interrupt 后停止当前播放并清空队列。

### 6.3 complete 语义

`output:chat:complete` 只表示文本回复完成。

TTS streaming 需要独立的音频完成事件，例如 `output:audio:complete`。它表示当前 generation 不会再产生新的音频 segment。

两者不能混用：

```text
output:chat:complete
  -> 文本完成，可以保存聊天历史

output:audio:complete
  -> 音频分段下发完成，可以结束本轮播放队列
```

TTS 合成失败不应回滚 `output:chat:complete`。

## 7. WebSocket 协议

### 7.1 output:audio:segment

后端向前端发送一个可播放音频段。

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
    "display_text": "前端已经显示或将显示的文本段",
    "tts_text": "实际送入 TTS 的文本段"
  }
}
```

第一版建议继续使用 JSON + base64，保持现有 WebSocket 消息风格。后续如果音频 payload 太大，再评估二进制 WebSocket frame。

### 7.2 output:audio:complete

当前 generation 的 TTS 音频段全部结束。

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

### 7.3 output:audio:error

某个 segment 合成失败，但不影响聊天文本完成。

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

前端收到 segment error 后应跳过该 sequence，避免播放队列永久等待。

## 8. 前端设计

### 8.1 自动 TTS

当 `streaming.enabled=true` 时，自动 TTS 不再等待 `output:chat:complete` 后调用 REST TTS。

新的自动 TTS 行为：

```text
收到 output:audio:segment
  -> 校验 generation_id 是否仍有效
  -> 按 sequence 放入播放队列
  -> 前一个 sequence 播完后播放下一个
```

前端仍继续按 `output:chat:chunk` 显示文本。音频播放不决定文本是否显示。

### 8.2 VAD interrupt

收到 `control:interrupt` 后，前端应：

1. 停止当前 audio element。
2. 清空等待播放的音频队列。
3. 标记当前或指定 `generation_id` 的自动 TTS 结果失效。
4. 后续收到旧 generation 的 `output:audio:segment` 时直接丢弃。

这和当前 REST TTS stale generation 处理保持一致，只是对象从完整音频请求扩展为多个音频 segment。

### 8.3 手动 TTS

用户点击历史 AI 消息播放、TTS 测试入口、或者 streaming disabled 时，仍走 REST `/api/tts/synthesize`。

手动 TTS 不参与 generation 历史语义：

1. 它可以播放没有 `generation_id` 的历史消息。
2. 它不会改变聊天历史或记忆。
3. VAD interrupt 到来时，前端只需要停止当前播放并清空本地队列。
4. 如果手动合成请求在 interrupt 后才返回，前端可按本地 `synthesis_id` 或 interrupt epoch 丢弃结果。

## 9. 配置

配置放在现有 `config/tts_config.yaml` 的顶层 `streaming` 区域。

建议第一版新增字段：

```yaml
streaming:
  enabled: false
  segment_method: pysbd
  faster_first_response: true
  max_concurrent_synthesis: 2
  max_pending_segments: 12
```

字段含义：

| 字段 | 含义 |
| --- | --- |
| `enabled` | 是否启用应用层 TTS 分段流式化 |
| `segment_method` | 分句方法，第一版使用 `pysbd` |
| `faster_first_response` | 是否允许第一段按短停顿提前切出 |
| `max_concurrent_synthesis` | 同一 generation 允许同时进行的 TTS 合成任务数 |
| `max_pending_segments` | 后端允许排队但尚未下发或播放的最大 segment 数 |

注意：现有 provider 配置中的 `stream`、`streaming_mode` 等字段属于 provider 请求参数，不等同于 ATRI 应用层 TTS streaming 开关。

## 10. 相对原定方案的调整

基于“TTS 是下游消费者，不产生反馈回路”的原则，原定 TTS streaming 方案需要收窄：

1. 保留分段合成、WebSocket 音频下发、sequence 播放和 interrupt 清队列。
2. 删除第一版 `heard_response` 回传。
3. 删除“前端回传已播放 segment 后修正 partial_reply”的链路。
4. 被打断 AI 回复的 `partial_reply` 继续使用后端已经发送给前端的文本累积值。
5. interrupted 消息是否写历史、是否进入记忆，仍由 VAD M5 已定规则决定，TTS 不参与。
6. TTS segment 的 `display_text` 和 `tts_text` 只用于合成、调试和前端播放关联，不作为聊天历史的新来源。
7. 不预留 provider-native streaming 分支；第一版只做应用层分段合成。

因此，TTS streaming 的边界是：

```text
可以改变：音频何时合成、何时下发、如何排队、如何在打断时丢弃。
不能改变：聊天文本如何保存、记忆如何写入、generation 是否有效。
```

## 11. 验收标准

1. streaming disabled 时，现有 REST TTS 行为不变。
2. streaming enabled 时，第一段音频可以在 `output:chat:complete` 前开始播放。
3. 所有音频段都携带 `generation_id`、`segment_id` 和 `sequence`。
4. 前端按 sequence 顺序播放，不因并发合成乱序。
5. VAD interrupt 后，当前音频立即停止，旧 generation 队列被清空。
6. interrupt 后返回的旧 generation TTS 结果不会播放。
7. `output:chat:complete` 和 `output:audio:complete` 语义独立。
8. TTS segment 失败不会导致聊天文本失败或历史回滚。
9. 手动播放历史消息仍可通过 REST TTS 工作。
10. interrupted partial reply 仍以“已发送给前端的 LLM 文本”为准，不受 TTS 播放进度影响。

## 12. 风险与后续问题

1. `pysbd` 需要新增依赖，并确认中文标点分句效果。
2. base64 音频 payload 可能增大 WebSocket 消息体。
3. 多 segment 并发可能触发 provider 速率限制，需要保守默认并发。
4. 过短首段可能影响语音自然度，`faster_first_response` 必须可关闭。
5. 不同 provider 的音频格式可能不同，前端播放队列需要依赖 `media_type`。
6. provider 请求已发出后可能无法真正取消，只能在返回后丢弃。
7. 如果某个 sequence 合成失败，前端必须收到 error 或 skip 信号，避免队列卡住。

## 13. 推荐实施顺序

1. 新增 `pysbd` 分段器，先用单元测试验证中文文本切分。
2. 增加后端 `TTSSegmentManager`，只在测试中喂入模拟 LLM chunk。
3. 接入现有 `TTSService.synthesize()`，完成单 segment 合成。
4. 接入 WebSocket `output:audio:segment` / `complete` / `error`。
5. 扩展前端 audio player，支持 generation + sequence 队列。
6. 把自动 TTS 从 complete 后 REST 调用切到 WebSocket segment。
7. 验证 VAD interrupt 对音频队列、旧 generation、手动 TTS 的处理。
