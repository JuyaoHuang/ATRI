# ATRI VAD 实时打断开发文档

> 历史开发稿说明：
> 当前正式入口请优先阅读 [../../features/2026-06-vad-realtime-interrupt/README.zh-CN.md](../../features/2026-06-vad-realtime-interrupt/README.zh-CN.md)、[../../modules/vad/README.zh-CN.md](../../modules/vad/README.zh-CN.md) 和 [../development-blogs/2026-07-08-vad-realtime-interrupt.zh-CN.md](../development-blogs/2026-07-08-vad-realtime-interrupt.zh-CN.md)。
> 本文档保留为历史实施来源与迁移参考。

文档职责：本文件记录具体开发说明、协议解释和模块边界；M0-M7 的职责划分与验收以 `docs/developments/wiki/VAD/vad-implementation-plan.md` 为准，开发过程流水记录写入 `docs/developments/wiki/VAD/development.md`。

## 1. 当前没有阻塞性疑惑

本阶段可以先进入开发文档与计划书准备。以下是后续实现时采用的工作假设，不影响先行设计：

1. 第一版目标不是把所有语音都改成流式 TTS，而是先实现“用户开口即可打断”的核心体验。
2. 麦克风输入链路需要走 WebSocket，由后端持续接收音频片段并运行 VAD。
3. TTS 在第一版仍可保持当前 REST 合成完整音频的模式，前端收到后端打断控制信号时停止本地播放。
4. LLM 文字回复需要支持后端取消正在进行的生成任务，否则只能停止前端播放，不能真正停止后端继续产出文字。
5. VAD 要以插件式模块接入，形式参考当前 ASR、TTS 的 provider/factory/service 风格，避免硬编码到聊天、ASR 或 TTS 业务流程里。
6. 默认优先使用 Silero VAD 作为第一个 provider，但接口要允许后续替换为 WebRTC VAD、云厂商 VAD 或前端 VAD。

## 2. 目标

为 ATRI 增加 VAD 语音实时打断能力，使用户在角色正在回复或播放语音时直接开口说话，系统能够识别“用户开始说话”这一事件，并立即触发打断。

目标效果分为两层：

1. 播放层打断：前端正在播放 TTS 音频时，用户开口后立即停止当前音频和待播放队列。
2. 对话层打断：后端正在生成 LLM 回复时，用户开口后取消当前回复任务，避免继续输出已经被用户打断的内容。

这两层都需要 VAD 事件，但处理对象不同：

1. 播放层处理的是浏览器里的 audio 播放器。
2. 对话层处理的是后端当前会话中的 LLM 生成任务和后续 TTS 调用。

## 3. 当前 ATRI 语音链路

ATRI 当前可以理解为三条相对独立的链路。

### 3.1 文字聊天链路

前端通过 WebSocket 把用户文本发送给后端。后端调用 Agent/LLM，并通过 WebSocket 把文本 chunk 持续推回前端。前端收到完整回复后，再决定是否进入自动朗读。

这一链路已经具备“文本流式返回”的基础，但目前没有明确的“打断当前生成任务”的控制协议。

### 3.2 ASR 语音输入链路

前端通过按钮或录音控件采集一段完整音频，然后通过 REST API 提交给后端 ASR。后端转写成文本后返回给前端，前端再把文本作为用户输入提交给聊天链路。

这条链路的特点是：

1. 音频通常是录完后一次性提交。
2. 后端看不到用户“正在说话”的实时过程。
3. 因此它不能天然承担“用户刚开口就打断”的职责。

### 3.3 TTS 播放链路

前端在收到完整文本回复后，请求后端 TTS REST API。后端调用 TTS provider 合成完整音频 payload 后返回。前端拿到完整音频后在浏览器中播放。

这条链路的特点是：

1. TTS 音频是完整合成后返回，不是后端逐片推流。
2. 当前停止播放主要依靠前端 stop button 或播放器控制。
3. 后端通常不知道浏览器当前播放到哪里。
4. 即使停止前端播放，后端已经完成的 TTS 请求也不会被“撤销”。

所以 ATRI 当前缺少的是一条“持续监听用户是否开口”的实时控制链路。

## 4. OLV 的实现思路

Open-LLM-VTuber 的关键设计不是简单增加一个 VAD API，而是把 VAD 放在实时 WebSocket 语音通道中。

概念链路如下：

1. 前端持续把麦克风音频片段通过 WebSocket 发给后端。
2. 后端按会话维护 VAD 状态。
3. VAD 对连续音频片段进行判断，识别用户是否开始说话、是否仍在说话、是否说完。
4. 一旦检测到用户开始说话，后端立即向前端发送 interrupt 控制事件。
5. 前端收到 interrupt 后立刻停止当前音频播放。
6. 后端同时取消当前会话里的 LLM/TTS 任务。
7. 当 VAD 判断用户说完后，后端把收集到的语音片段交给 ASR。
8. ASR 得到文本后，再进入正常的对话生成流程。
9. 角色回复文本被切分成较小单元，TTS 按单元生成音频，再通过 WebSocket 下发给前端播放。

OLV 的核心不只是 VAD 模型，而是“VAD 事件驱动会话状态”。VAD 判断出的不是一个孤立结果，而是控制整个对话链路的事件：

1. 用户开始说话：打断当前回复和播放。
2. 用户持续说话：收集音频。
3. 用户停止说话：交给 ASR。
4. ASR 得到文本：触发新一轮对话。

## 5. ATRI 仿照 OLV 的可行架构

ATRI 不必第一步完全改成 OLV 的全 WebSocket TTS 架构。更稳妥的做法是分层引入。

### 5.1 第一版保留 REST TTS

第一版新增一条实时语音控制链路：

1. 前端打开麦克风。
2. 前端把小块音频持续通过 WebSocket 发给后端。
3. 后端 VADService 判断用户是否开始说话。
4. 如果用户开始说话，后端通过 WebSocket 发出 `control:interrupt`。
5. 前端收到后调用现有 audio player 的 stop 能力，停止当前 TTS 播放和队列。
6. 后端取消当前 LLM 回复任务。
7. VAD 判断用户说完后，把本轮音频交给现有 ASR service。
8. ASR 得到文本后，进入现有聊天 WebSocket 链路。
9. LLM 回复完成后，仍按当前方式调用 REST TTS 合成完整音频并播放。

这个方案的优点是改动集中，能优先实现“实时打断”价值，不要求一次性重写 TTS 播放架构。

### 5.2 第二版增强 LLM 打断语义

第一版如果只停止前端音频，用户会感觉播放被打断了，但后端可能仍在生成上一轮回复。第二版需要补齐后端会话控制：

1. 每个 WebSocket 会话保存当前 LLM 生成任务。
2. 收到 VAD interrupt 后，取消当前生成任务。
3. 被取消的半截回复可以写入 `chat_history`，但必须标记 `interrupted=true`。
4. 被取消的半截回复不作为普通完整 AI 回复进入短期记忆压缩或长期记忆写入。
5. 新的 ASR 文本到来后，作为新一轮用户输入继续对话。

这一层决定“角色是否真的被打断”，不是只有播放器被暂停。

### 5.3 第三版可选迁移 TTS WebSocket

如果后续希望体验更接近 OLV，可以把 TTS 输出从 REST 完整音频改为 WebSocket 音频 payload。

迁移后的链路是：

1. LLM 文本 chunk 被聚合成句子或短段。
2. 每个句子交给 TTS provider 合成。
3. 后端把每段音频通过 WebSocket 下发。
4. 前端按 sequence 顺序播放。
5. VAD interrupt 到来时，后端停止后续 TTS 任务，前端清空音频队列。

注意：即使 TTS provider 不支持真正流式生成，也可以按“句子级完整合成 + WebSocket 分段下发”实现接近流式的体验。OLV 对许多 API 版本 TTS 也是这种思路。

## 6. 插件式 VAD 模块边界

VAD 不应直接写死在聊天 route、ASR service 或 TTS service 里。建议新增独立模块：

1. VADProvider：具体模型或服务的适配层，例如 Silero。
2. VADService：统一管理音频 chunk 输入、状态判断和事件输出。
3. VADSession：每个用户连接或会话的 VAD 状态。
4. VADConfig：从配置文件读取 provider、采样率、阈值、静音时长等参数。

对外暴露的概念事件可以保持稳定：

1. `speech_start`：用户开始说话。
2. `speech_chunk`：用户正在说话，可继续缓存音频。
3. `speech_end`：用户说话结束，可以提交 ASR。
4. `silence`：当前没有有效语音。
5. `error`：VAD 处理异常。

这样后续替换 VAD provider 不会影响 ASR、TTS 和聊天主流程。

## 7. WebSocket 控制协议方向

现有聊天 WebSocket 已经承担文本输入和文本输出。新增 VAD 后，建议扩展为同一连接上的多类型消息，而不是另起一套完全分离的连接。

概念消息类型：

1. 前端到后端：音频 chunk。
2. 前端到后端：麦克风停止。
3. 前端到后端：用户手动中断。
4. 后端到前端：控制事件 interrupt。
5. 后端到前端：ASR 转写结果。
6. 后端到前端：聊天文本 chunk。
7. 后端到前端：聊天完成。
8. 后端到前端：错误事件。

ATRI 已确认采用以下 WebSocket 命名风格：

1. `input:audio:chunk`：前端发送实时麦克风音频片段。
2. `input:audio:end`：前端通知本轮音频输入结束。
3. `control:interrupt`：后端通知前端用户已开始说话，前端应立即停止当前播放；如果本次事件实际打断了正在生成的 LLM 回复，则同时处理旧 `generation_id`。
4. `output:asr:transcript`：后端返回 ASR 转写文本。
5. `control:listen-state`：后端返回监听状态，例如 `speech_start`、`speech_end`、`silence`、`error`。

其中 `output:asr:transcript` 在 M2 只定义和预留协议形态，真实 ASR 转写与触发在 M4 接入。

`control:interrupt` 的 `reason` 字段优先使用 `speech_start`。也就是说，只要后端 VAD 判断用户开始说话，就不等待 ASR 结果，立即触发控制事件。

`control:interrupt` 的 `generation_id` 是条件字段：如果 `speech_start` 发生时后端正在跟踪某一轮 LLM generation，并且本次事件实际使该 generation 失效，则必须携带被打断的 `generation_id`。如果用户只是开始说话，但当前没有正在生成的 LLM 回复，则该事件可以不携带 `generation_id`，此时它只表示“停止当前播放/进入用户说话状态”，不表示有旧 generation 需要屏蔽。

ATRI 不直接复用 OLV 的外部消息名，例如 `raw-audio-data`、`mic-audio-end`。这些名称能说明 OLV 的机制，但和 ATRI 当前 `input:*`、`output:*`、`control:*` 风格不一致。

这样做的好处是同一个会话里可以统一管理：

1. 当前用户是谁。
2. 当前是否正在生成回复。
3. 当前是否正在播放或等待播放 TTS。
4. 当前麦克风输入属于哪一轮用户发言。
5. 当前打断应该作用到哪一个任务。

## 8. 打断语义

VAD 的打断不应简单等同于“用户说话了”。建议定义清楚三种打断：

### 8.1 播放打断

触发条件：检测到 `speech_start`，并且前端正在播放或排队播放 TTS。

处理动作：

1. 后端发送 interrupt 控制事件。
2. 前端停止播放器。
3. 前端清空待播放队列。

### 8.2 生成打断

触发条件：检测到 `speech_start`，并且后端正在生成 LLM 回复。

处理动作：

1. 后端取消当前 LLM task。
2. 停止继续向前端推送上一轮文本。
3. 标记上一轮回复为 `interrupted=true`。
4. 将半截回复写入 `chat_history` 时，必须保留 interrupted 元数据。
5. 不把该半截回复当作完整 AI 回复进入短期记忆压缩或长期记忆写入。

### 8.3 输入接管

触发条件：检测到 `speech_end`，且本轮音频长度满足 ASR 最小要求。

处理动作：

1. 后端把缓存的音频交给 ASR。
2. ASR 返回文本后，作为用户新输入进入聊天链路。
3. 前端显示转写文本，用户可以看到自己刚说了什么。

## 9. 第一版验收标准

第一版完成后，应满足以下概念验收：

1. 用户打开实时语音模式后，不需要按住录音按钮即可被后端持续监听。
2. 角色 TTS 正在播放时，用户开口能在可感知时间内停止播放。
3. 角色 LLM 正在输出文字时，用户开口能停止上一轮继续输出。
4. 用户说完后，系统能把该段语音交给 ASR 并继续对话。
5. VAD provider 可通过配置切换或关闭。
6. VAD 关闭时，现有文字聊天、REST ASR、REST TTS 不受影响。

## 10. OLV 经验复用边界

OLV 的经验可以解决 ATRI M2 以后大部分链路问题，但不应直接搬运全部实现。

可以复用的部分：

1. 后端 VAD 状态机思路：`IDLE`、`ACTIVE`、`INACTIVE`。
2. `required_hits` 防误触发机制。
3. `required_misses` 判断说话结束机制。
4. `pre_buffer` 保留用户开口前的短音频，避免吞掉句首。
5. `speech_start` 立即触发 interrupt，不等待 ASR。
6. `speech_end` 后把完整语音片段交给 ASR。
7. WebSocket 会话保存当前 LLM task，并在 interrupt 时取消。

不直接复用的部分：

1. 不复用 OLV 的 WebSocket 消息名。
2. 不把 `b"<|PAUSE|>"`、`b"<|RESUME|>"` 作为 VAD 模块外部协议。
3. 不在第一版迁移 OLV 的 TTS task manager。
4. 不搬运 OLV 的 `web_tool` 前端代码。
5. 不把 Web Speech API 当成 VAD model。

ATRI 应该复用 OLV 的机制，而不是复用 OLV 的协议外壳。

配置归属上，`required_hits` / `required_misses` 不能再视为全局 VAD 参数。fake 是开发联调用的能量阈值 provider，它的 `speech_threshold`、`required_hits`、`required_misses` 只描述 fake provider。Silero 是真实模型 provider，它的 `prob_threshold`、`db_threshold`、`required_hits`、`required_misses`、`smoothing_window` 按 OLV 的 512-sample 小窗口状态机理解。

## 11. M2 以后已确认决策

### 11.1 音频输入格式

实时 VAD 主路径使用 16 kHz、mono、PCM float 数组。前端优先通过 AudioContext 或 AudioWorklet 获取音频，并在发送前完成必要重采样。

MediaRecorder 适合按钮式录音和 REST ASR，不作为实时 VAD 主路径。

### 11.2 VAD 事件模型

VADService 对外输出语义事件，而不是特殊 bytes。

核心事件：

1. `speech_start`：用户开始说话。
2. `speech_end`：用户说话结束。
3. `silence`：当前没有有效语音。
4. `error`：VAD 处理失败。

`speech_start` 在同一轮连续说话期间只触发一次 interrupt。防重复逻辑由 VADSession 状态机负责。

### 11.3 打断历史策略

被打断的半截 AI 回复可以写入 `chat_history`，但必须标记：

```json
{
  "interrupted": true
}
```

这条历史记录用于让用户理解“上一轮为什么断了”。它不能被当作普通完整 AI 回复参与记忆压缩和长期记忆写入。

### 11.4 Web Speech API 定位

Web Speech API 是浏览器侧 ASR 或降级事件源，不是 VAD model。ATRI 的实时打断主线以后端 VAD 为准。

## 12. 非目标

第一版不做以下内容：

1. 不要求 TTS provider 必须支持真实流式音频。
2. 不要求所有现有 TTS provider 立即改成 WebSocket 输出。
3. 不把 VAD 做成一次性 `/api/vad/detect` REST API 作为主路径。
4. 不把模型参数硬编码到 route 或前端组件。
5. 不强制废弃现有 stop button；手动停止仍应保留。

## 13. 关键风险

1. 浏览器音频格式和后端 VAD 采样率不一致，需要明确转换策略。
2. Silero 依赖通过 `silero-vad` 包安装，包内模型由 `load_silero_vad()` 懒加载；它会增加安装体积，但不需要手动网页下载模型文件。
3. VAD 过敏会误打断，阈值、连续命中次数和静音时长必须可配置。
4. VAD 不敏感会导致打断迟钝，需要保留可调参数。
5. LLM 取消后历史写入需要严格保留 `interrupted=true`，避免半截回复污染记忆。
6. 移动端浏览器和 VPN 网络环境可能导致 WebSocket 音频 chunk 延迟，需要在前端显示清晰的连接状态。
