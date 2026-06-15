# ATRI VAD 实时打断实施计划

状态：待执行  
日期：2026-06-15  
前置文档：`docs/developments/wiki/VAD/vad-design.md`、`docs/developments/wiki/VAD/vad-implement.md`

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
4. 后端通知 ASR 结果：`output:asr:transcript`。
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
4. 增加 `output:asr:transcript` ASR 转写结果事件。
5. 增加 `control:listen-state` 监听状态事件。
6. 为每个 WebSocket 连接维护当前 VADSession 和音频缓存。
7. 为每个 WebSocket 连接维护当前 LLM task 引用。

验收：

1. 普通文字聊天 WebSocket 行为不变。
2. 音频消息不会被误当成文字消息。
3. VAD 检测到 `speech_start` 后，后端能向前端发送 `control:interrupt`。
4. WebSocket 断开时能释放 VADSession、音频缓存和未完成任务。
5. 同一轮连续说话期间，`speech_start` 只触发一次 `control:interrupt`。

### M3：前端实时麦克风输入

目标：前端新增实时语音模式，把麦克风小片段持续发给后端。

预计涉及位置：

1. `frontend/src/composables/`
2. `frontend/src/utils/websocket.ts`
3. 当前语音输入控件所在组件
4. 当前 WebSocket 消息处理 composable
5. 当前 audio player composable

执行内容：

1. 新增实时语音输入 composable。
2. 优先使用 AudioContext/AudioWorklet 获取小片段音频。
3. 将音频重采样为 16 kHz、mono、PCM float 数组。
4. 将音频片段通过 WebSocket 的 `input:audio:chunk` 发送到后端。
5. 接收后端 interrupt 控制事件。
6. 收到 interrupt 后调用现有 audio player stop 能力。
7. 为实时语音模式增加连接、监听中、说话中、错误等状态。
8. 保留 MediaRecorder 作为非实时按钮式 ASR 或降级路径，不作为 VAD 主路径。

验收：

1. 用户开启实时语音模式后，前端能持续发送音频片段。
2. 后端发送 interrupt 后，前端能停止当前 TTS 播放和播放队列。
3. 关闭实时语音模式后，麦克风资源被释放。
4. 原有按钮式 ASR 仍可使用。

### M4：VAD 到 ASR 的衔接

目标：用户说完后，后端把本轮音频交给现有 ASR service，并把转写结果接入聊天流程。

预计涉及位置：

1. `src/asr/`
2. `src/routes/chat_ws.py`
3. WebSocket 会话状态管理逻辑

执行内容：

1. VADSession 在 speech_start 后开始缓存有效音频。
2. VADSession 在 speech_end 后输出完整语音段。
3. 后端把完整语音段交给 ASR service。
4. 后端把 ASR 文本推送给前端展示。
5. 后端将 ASR 文本作为用户输入进入现有聊天处理流程。

验收：

1. 用户说一句话后，不需要再次点击发送即可进入聊天。
2. 前端能显示 ASR 转写文本。
3. ASR 失败时能返回明确错误，不破坏 WebSocket 连接。
4. 过短音频或纯噪声不会触发一轮新对话。

### M5：LLM 生成打断

目标：让用户开口不仅停止播放，还能取消后端正在生成的上一轮回复。

预计涉及位置：

1. `src/routes/chat_ws.py`
2. Agent/聊天生成任务封装位置
3. 记忆写入或对话历史更新位置

执行内容：

1. WebSocket 会话保存当前 LLM 生成 task。
2. VAD speech_start 触发 interrupt 时，取消当前 task。
3. 已经发送给前端的部分文本标记为 `interrupted=true`。
4. 被打断的半截 AI 回复可以写入 `chat_history`，但必须带 `interrupted=true` 元数据。
5. 被打断的半截 AI 回复不按普通完整回复写入短期记忆压缩或长期记忆。
6. 用户新语音完成 ASR 后进入新一轮对话。

验收：

1. LLM 正在输出文字时，用户开口能停止继续输出。
2. 被打断的回复不会继续触发新的 TTS 合成。
3. `chat_history` 能保留半截回复，并用 `interrupted=true` 区分普通完整回复。
4. 用户下一句话能正常接续对话。
5. 记忆系统不会把被打断的半截回复当作完整对话轮次。

### M6：配置、测试与文档补齐

目标：让功能可配置、可测试、可回归。

执行内容：

1. 增加 VAD 配置文档。
2. 增加前端实时语音模式说明。
3. 增加后端单元测试，覆盖 VAD 状态机和 fake provider。
4. 增加 WebSocket 消息流测试。
5. 增加前端类型检查或构建验证。
6. 增加手动测试清单。

验收：

1. VAD 默认配置清晰可查。
2. 关闭 VAD 后所有现有功能保持可用。
3. 单元测试覆盖 speech_start、speech_end、误触发、短音频等情况。
4. 前端构建通过。

### M7：可选 TTS WebSocket 化

目标：在第一版稳定后，评估是否把 TTS 输出改成更接近 OLV 的 WebSocket 分段音频。

执行内容：

1. 将 LLM 文本按句子或短段切分。
2. 每段调用现有 TTS provider 合成完整小音频。
3. 后端通过 WebSocket 下发音频 payload 和 sequence。
4. 前端按 sequence 播放。
5. interrupt 到来时，前端清空音频队列，后端取消未完成 TTS 任务。

验收：

1. 即使 TTS provider 不支持真正流式，也能实现分段播放。
2. 用户能更早听到角色回复。
3. 打断时未播放的 TTS 队列能被清理。

## 3. 推荐执行顺序

1. 先做 M1，用 fake provider 验证 VAD 事件模型。
2. 再做 M2，把事件接入 WebSocket，但暂不接真实前端。
3. 再做 M3，让前端能发送音频并响应 interrupt。
4. 再做 M4，把 speech_end 接到 ASR 和聊天。
5. 再做 M5，补齐 LLM task 取消和历史策略。
6. 最后做 M6 的测试和文档收尾。
7. M7 不进入第一版必做范围。

这个顺序能保证每一步都有独立可验收结果，避免一开始同时改 VAD、ASR、TTS、LLM 和前端播放器。

## 4. 配置计划

建议新增或扩展 VAD 配置，字段保持 provider 无关。

建议配置项：

1. `enabled`：是否启用 VAD。
2. `provider`：选择 VAD provider。
3. `sample_rate`：后端 VAD 使用的目标采样率。
4. `chunk_ms`：前端音频片段长度。
5. `speech_threshold`：语音概率阈值。
6. `silence_ms`：判定说话结束所需静音时长。
7. `min_speech_ms`：最短有效语音长度。
8. `interrupt_on_speech_start`：是否在 speech_start 立即触发打断。
9. `auto_submit_after_speech_end`：speech_end 后是否自动 ASR 并提交对话。

配置原则：

1. 所有阈值都应可调。
2. 模型实现细节不写死在业务代码。
3. 关闭 VAD 后不加载重型模型。

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
