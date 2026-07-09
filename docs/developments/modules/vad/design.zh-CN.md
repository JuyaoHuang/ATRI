---
status: active
owner: vad
created: 2026-07-09
updated: 2026-07-09
source:
  - ../../module-design/CN/VAD语音唤醒模块设计.md
  - ../../features/2026-06-vad-realtime-interrupt/README.zh-CN.md
  - src/vad/interface.py
  - src/vad/factory.py
  - src/vad/session.py
  - src/vad/service.py
  - src/routes/chat_ws.py
related_code:
  - src/vad/interface.py
  - src/vad/factory.py
  - src/vad/session.py
  - src/vad/service.py
  - src/vad/config.py
  - src/vad/exceptions.py
  - src/routes/chat_ws.py
---

# VAD 模块总设计

本文把 `src/vad/` 的整体设计接起来。现有文档已经分别讲了架构、配置和实时打断边界，但还缺一页说明：

1. VAD 本体和 `chat_ws` 连接态是怎样分工的。
2. Provider、防抖、session、打断语义为什么这样拆。
3. 旧“语音唤醒模块”设计里哪些已经被当前实现替代。

## 模块定位

当前 VAD 是一个**实时音频控制模块**，不是独立的上传分析服务。它的角色是把连续麦克风 chunk 转成少量稳定事件，再交给聊天 WebSocket 路径消费。

它在系统中的位置更接近：

```text
frontend realtime audio
  -> input:audio:chunk
  -> VADService / VADSession / provider
  -> VADEvent
  -> chat_ws orchestration
  -> interrupt / ASR handoff / new generation
```

因此，VAD 的长期目标不是“做一套通用语音 API”，而是为实时语音模式提供稳定控制语义。

## 设计目标

结合旧设计文档、当前代码和近期 M4-M6 演化，长期目标已经收敛为 5 条：

1. 用稳定事件而不是原始概率流驱动上层逻辑。
2. 把原始检测和防抖拆开，避免 Provider 能力和系统语义耦死。
3. 把 VAD 事件和聊天 generation / TTS generation 绑定起来。
4. 让 Provider 失败只影响当前实时语音链路，不杀死整条聊天 WebSocket。
5. 明确 VAD 不拥有独立 REST 子系统。

## 模块组成

当前 `src/vad/` 可以稳定拆成六部分：

| 组件 | 代码 | 职责 |
| --- | --- | --- |
| 接口层 | `interface.py` | 定义 `VADInterface`、`VADResult`、`VADEvent`、`VADHealth`。 |
| 工厂层 | `factory.py` | 维护 Provider 注册表和静态元数据。 |
| 配置层 | `config.py` | 读写 `config/vad_config.yaml`。 |
| 异常层 | `exceptions.py` | 统一配置错误、Provider 不可用和处理失败。 |
| session 层 | `session.py` | 把单 chunk 检测结果防抖成稳定语义事件。 |
| 服务层 | `service.py` | 管理按 `session_id` 归属的 `VADSession` 实例。 |

真正把 VAD 事件翻译成“打断聊天”“停止 TTS”“交给 ASR”的，是 `src/routes/chat_ws.py`，不在 `src/vad/` 模块本体里。

## 事件模型

当前 VAD 的对上游输出不是“bool + confidence”，而是固定事件集：

| 事件 | 语义 |
| --- | --- |
| `speech_start` | 当前 speaking burst 第一次被确认开始。 |
| `speech_chunk` | 当前 speaking burst 仍在进行中。 |
| `speech_end` | 当前 speaking burst 被确认结束。 |
| `silence` | 当前 chunk 没有触发说话语义。 |
| `error` | 处理失败，需前端和连接态收口。 |

长期约束：

- 打断逻辑只在 `speech_start` 上触发；
- ASR 接管只在 `speech_end` 上触发；
- `speech_chunk` 只是持续态，不应重复触发 interrupt。

## 原始检测与防抖分层

### Provider 层：`VADResult`

Provider 返回的是单 chunk 检测结果：

```python
VADResult(
    is_speech: bool,
    probability: float | None,
    energy: float | None,
    metadata: dict[str, Any],
)
```

这仍然是“原始检测层”，不代表最终语义。

### Session 层：`VADEvent`

`VADSession.process_audio()` 把连续 chunk 的结果变成防抖后的稳定事件：

- `state = idle / active`
- `_speech_hits`
- `_silence_misses`

这一步才决定：

- 什么时刻算 `speech_start`
- 什么时刻算 `speech_end`
- 中间 chunk 是继续说话还是恢复静音

长期意义是：上层业务不需要关心概率抖动，只消费稳定事件。

## 防抖所有权

当前系统最容易误写错的点，就是“防抖到底在 Provider 内还是在 session 外”。

当前真实情况是：

| Provider | 原始判断 | 防抖主责 |
| --- | --- | --- |
| `fake` | 基于 chunk 能量阈值 | `VADSession` |
| `silero_vad` | Provider 内部就有概率/平滑/hits/misses | `silero` 内部为主，session 外层退化为 1/1 |

`VADFactory` 元数据里的 `uses_internal_debounce`，就是为了表达这条差异。

因此长期规则是：

- 不能假设所有 Provider 都靠 `VADSession` 做完整防抖；
- 也不能把所有防抖都塞进 Provider 内部；
- service 层必须根据 Provider 类型动态决定 session 的 `required_hits` / `required_misses`。

## Service 层设计

`VADService` 是路由层唯一正式入口。它负责：

- 管理当前配置；
- 切换 Provider；
- 为每个 `session_id` 提供一个 `VADSession`；
- 把 provider 健康状态暴露给上层。

### 会话缓存

`VADService` 按 `session_id` 缓存 `VADSession`：

```text
session_id -> VADSession(provider, config)
```

这和 `ASRService` 的“本地模型长驻缓存”不同。VAD 的 session 缓存是为了保存说话状态机，而不是为了保存重量级模型生命周期。

### 配置更新后的行为

当前 `update_config()` 和 `switch_provider()` 都会：

- 更新配置；
- 清空 `_sessions`

这意味着：

- 参数一变，旧 session 状态全部作废；
- 下一次音频 chunk 会按新 Provider / 新防抖参数重新建 session。

## `chat_ws` 的连接态所有权

VAD 本体只判断音频语义。真正的连接级协同状态在 `WebSocketVADState`：

- `interrupt_sent`
- `current_chat_task`
- `current_generation_id`
- `current_tts_generation_id`
- `audio_buffer`
- `pre_buffer`
- `last_chat_id`
- `last_character_id`

这层状态让 `chat_ws` 可以把 `VADEvent` 变成业务动作：

- `speech_start`
  -> invalidate generation
  -> cancel chat task
  -> interrupt TTS
  -> maybe persist partial reply
- `speech_end`
  -> consume audio buffer
  -> call backend ASR
  -> auto-start a new chat generation

长期边界：

- `src/vad/` 不知道聊天任务和 TTS 任务；
- `chat_ws` 不重新做音频判别，只消费 `VADEvent`。

## 音频缓冲语义

当前实时语音链路里有两类缓冲：

1. `pre_buffer`
   - 用于在 `speech_start` 前保留一小段音频，避免截掉开头。
2. `audio_buffer`
   - 用于积累当前 speaking burst 的完整语音片段，供 `speech_end` 后交给 ASR。

这两层缓冲都不属于 `src/vad/` 本体，而属于 `chat_ws` 连接态。

长期约束：

- `speech_start` 时，`audio_buffer` 应该从 `pre_buffer` 开始；
- `speech_end` 后才把 `audio_buffer` 交给 ASR；
- `input:audio:end` 和错误恢复都会清空这两层缓冲。

## Provider 现实

当前系统里有两个 VAD Provider：

- `fake`
- `silero_vad`

旧设计文档里强调“Silero VAD 待实现 / 独立 Phase”，而当前实现已经不同：

- `silero_vad` 已经落地并接入主链路；
- `fake` 仍然保留，主要用作简化环境或测试兜底。

这意味着当前 VAD 的长期设计，应以“双 Provider 现实”来写，而不是只写未来计划。

## 失败语义

当前 VAD 失败时，不会直接关闭聊天 WebSocket。错误路径长期约束是：

- 发送 `control:listen-state(state=error, code=..., message=...)`
- 清空音频缓冲
- 重置当前 VAD session
- 保持 WebSocket 可继续处理文本聊天

这一点已经被近期日志 `保持 VAD 失败时 WebSocket 可用` 明确确认。

## 与 ASR 的边界

VAD 不做转录，只在 `speech_end` 决定“现在把音频交给 ASR”。

当前真实边界：

- `VADService` 只产生事件；
- `chat_ws` 在 `speech_end` 时编码成 `realtime-vad.wav`；
- `ASRService.transcribe_audio()` 负责真正转录；
- 产出的 transcript 再触发新一轮聊天。

因此，VAD 和 ASR 是顺序协作，不是混成同一个模块。

## 与 TTS 的边界

当前 VAD 和 TTS 的耦合点只有 generation 生命周期：

- `speech_start` 让旧 TTS generation 失效；
- `output:audio:*` 是否还应下发，由 generation 是否仍 active 决定。

VAD 本身不关心：

- TTS 用哪个 Provider；
- TTS 如何切段；
- TTS 如何播放。

## 与旧设计文档的取舍

旧 `VAD语音唤醒模块设计.md` 中这些内容已不再代表当前事实：

- 独立 `/api/vad/detect` REST 主路径
- “待实现 / Phase 12” 状态
- 把 VAD 当作独立模块功能，而不是聊天 WebSocket 集成能力

保留下来的骨架是：

- 需要稳定的语音起止事件；
- 需要可配置阈值和防抖；
- Silero VAD 仍是主要高质量后端方案。

## 相关文档

- [architecture.zh-CN.md](architecture.zh-CN.md)
- [config.zh-CN.md](config.zh-CN.md)
- [realtime-interrupt-boundary.zh-CN.md](realtime-interrupt-boundary.zh-CN.md)
- [../../features/2026-06-vad-realtime-interrupt/README.zh-CN.md](../../features/2026-06-vad-realtime-interrupt/README.zh-CN.md)
