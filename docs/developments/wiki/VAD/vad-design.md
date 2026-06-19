# ATRI VAD 实时打断设计说明

## 1. 这份文档要解决什么问题

atri 当前已经有 ASR 和 TTS，但它们不是一个统一的实时语音对话链路。

现在的 atri 更接近：

```text
用户按按钮录音/识别
  -> 得到文字
  -> 发送给 LLM
  -> 等 LLM 完整回复
  -> 调 TTS API 合成完整音频
  -> 前端播放
```

而 OLV 更接近：

```text
用户麦克风一直在传音频
  -> 后端 VAD 实时判断用户是否开始说话
  -> 用户一开口，立即打断当前 AI 输出
  -> 用户说完后，自动 ASR
  -> 自动进入下一轮 LLM + TTS
```

所以 VAD 在这里不是一个简单的“检测这段音频里有没有人声”的工具。  
它是整个语音对话链路的“实时控制模块”。

## 2. atri 当前语音链路

### 2.1 当前 ASR 链路

atri 当前的 ASR 更像“语音输入按钮”。

概念链路是：

```text
用户点击麦克风按钮
  -> 前端开始录音或调用浏览器 Web Speech
  -> 用户手动停止，或浏览器识别出一句话
  -> 得到 transcript 文本
  -> 填入输入框
  -> 根据设置手动发送或自动发送
```

如果使用后端 ASR provider，则链路是：

```text
前端 MediaRecorder 录完整段音频
  -> HTTP 上传到 /api/asr/transcribe
  -> 后端 ASR 返回文字
  -> 前端把文字放入输入框
  -> 再发送给聊天 WebSocket
```

这条链路的特点：

- 它不是实时连续监听。
- 后端没有持续收到麦克风音频流。
- 后端无法在“用户刚开口”时立刻做动作。
- ASR 和聊天 WebSocket 是分开的。
- 它适合“按住/点击录音”，不适合“自然说话打断 AI”。

### 2.2 当前 LLM 文本链路

atri 当前的聊天 WebSocket 主要负责 LLM 文本流。

概念链路是：

```text
前端发送 input:text
  -> 后端 ChatAgent 调用 LLM
  -> 后端把 LLM 回复 chunk 持续发给前端
  -> 前端显示流式文字
  -> 后端发 output:chat:complete
  -> 前端认为本轮文本回复完成
```

这条链路目前没有“取消当前回复”的统一协议。  
也就是说，当前 atri 可以显示 LLM 流式文字，但没有一个明确的“用户打断了，请停止生成”的语音控制入口。

### 2.3 当前 TTS 链路

atri 当前的 TTS 是“完整文本合成完整音频”模式。

概念链路是：

```text
LLM 完整回复完成
  -> 前端拿到完整回复文本
  -> 前端调用 TTS API
  -> 后端 TTS provider 合成完整音频
  -> HTTP 返回完整 audio blob
  -> 前端创建音频 URL
  -> HTMLAudioElement 播放
```

当前暂停/停止播放依赖前端播放器控制：

```text
用户点击 stop button
  -> 前端停止 HTMLAudioElement
  -> 清空当前播放项
  -> 清空播放队列
```

这条链路的特点：

- TTS 不在聊天 WebSocket 内。
- TTS 音频不是从后端 WebSocket 推给前端。
- 后端合成完成前，前端拿不到音频。
- 前端可以停止已经开始播放的音频。
- 如果 TTS API 请求还在进行中，当前设计更像“等待请求返回”，还没有和 VAD/打断机制绑定。

### 2.4 atri 当前的关键结论

当前 atri 实际上有三条相对独立的链路：

```text
ASR 链路：前端录音/识别 -> 文字
LLM 链路：WebSocket 文本输入 -> 文本输出
TTS 链路：完整文本 -> HTTP TTS -> 完整音频 -> 前端播放
```

它们可以配合工作，但还不是 OLV 那种统一的实时语音对话链路。

## 3. OLV 的语音链路实现思路

OLV 的核心设计不是“ASR、TTS、VAD 各自独立运行”，而是把它们放进一条 WebSocket 驱动的对话链路里。

### 3.1 OLV 的整体语音链路

概念链路是：

```text
前端持续采集麦克风 PCM 音频
  -> WebSocket 持续发送 raw audio chunk
  -> 后端 VAD 实时检测

如果检测到用户开始说话：
  -> 后端立即发送 interrupt 控制事件
  -> 前端立即停止当前 AI 音频播放
  -> 后端取消当前对话任务
  -> Agent 记录“被用户打断”

如果检测到用户说完：
  -> VAD 输出完整用户语音片段
  -> 后端把这段语音交给 ASR
  -> ASR 得到用户文字
  -> 用户文字进入 Agent/LLM
  -> LLM 生成回复
  -> 回复被切成句子或片段
  -> TTS 合成音频
  -> 后端通过 WebSocket 把音频 payload 发给前端
  -> 前端播放
```

### 3.2 OLV 的 VAD 做了什么

OLV 的 VAD 不只是返回 true/false。

它在持续音频流里识别三个关键时刻：

```text
1. 用户还没说话
2. 用户开始说话
3. 用户说完了
```

因此它能产出两类控制意义：

```text
用户开始说话
  -> 发出 interrupt

用户说完一整句话
  -> 输出完整语音片段
  -> 交给 ASR
```

这就是 VAD 可以打断 TTS 的原因：  
它不需要等 ASR 出文字。只要判断“用户开始说话”，就可以立即打断。

### 3.3 OLV 的 ASR 怎么接上

OLV 中，ASR 不负责实时判断“什么时候开始/结束说话”。  
这件事交给 VAD。

ASR 只负责：

```text
拿到 VAD 收集好的一整段用户语音
  -> 转成文字
```

所以 OLV 的职责分工是：

```text
VAD：决定什么时候开始听、什么时候结束听、什么时候打断
ASR：把已经切好的用户语音片段转成文字
```

这点很重要。  
如果没有 VAD，ASR 往往只能处理“录好的一段音频”。  
有了 VAD，系统才知道什么时候该自动开始和自动结束一个语音回合。

### 3.4 OLV 的 TTS 怎么接上

OLV 的 TTS 位于 LLM 回复之后。

概念链路是：

```text
LLM 输出文本
  -> 系统按句子或片段切分
  -> 每个片段进入 TTS 任务
  -> TTS 生成音频文件
  -> 后端把音频包装成 WebSocket audio payload
  -> 前端播放
```

注意：OLV 的很多 API TTS provider 也不是“真正边生成边播放”。

例如 GPT-SoVITS、SiliconFlow、OpenAI-compatible、Fish API 这类 provider，OLV 上层通常仍然拿到的是：

```text
一段文本 -> 一个生成完成的音频文件
```

OLV 的“流式感”主要来自：

```text
把 LLM 回复拆成多个片段
  -> 多个 TTS 片段任务可以并发或排队生成
  -> 每个片段生成完就通过 WebSocket 发给前端
  -> 前端按顺序播放
```

所以 OLV 的 TTS 更准确叫：

```text
分段合成 + WebSocket 音频下发 + 有序播放
```

不一定是 provider 层面的真流式 TTS。

### 3.5 OLV 的打断为什么能同时影响 LLM 和 TTS

OLV 的打断不是只停播放器。

它同时做几件事：

```text
1. 前端停止当前音频播放
2. 后端取消当前对话任务
3. 后端清理还没发出的 TTS 音频任务
4. Agent/记忆里记录“这次回复被用户打断”
```

所以 OLV 的打断是“对话级打断”，不是单纯的“暂停音乐”。

## 4. atri 仿照 OLV 的可行方案

### 4.1 总体判断

atri 可以仿照 OLV 加入 VAD 实时打断。

但不建议一步到位把所有链路都改成 OLV 模式。  
更稳妥的做法是分阶段演进：

```text
第一阶段：VAD + ASR 走 WebSocket，TTS 继续 REST
第二阶段：加入对话任务取消，打断 LLM 文字回复
第三阶段：可选，把 TTS 音频也迁入 WebSocket，形成 OLV 式统一语音链路
```

### 4.2 第一阶段：VAD + ASR 走 WebSocket

第一阶段要新增的是“麦克风实时上行链路”。

概念链路：

```text
前端持续采集麦克风 PCM 音频
  -> WebSocket 发送 input:audio:chunk
  -> 后端 VADService 检测
```

当 VAD 检测到用户开始说话：

```text
后端发送 control:interrupt
  -> 前端收到
  -> 调用当前播放器 stop
  -> 当前 TTS 播放立即停止
```

当 VAD 检测到用户说完：

```text
后端聚合完整语音片段
  -> 交给现有 ASRService
  -> 得到 transcript
  -> transcript 进入现有聊天链路
```

这个阶段已经能做到：

```text
用户一开口，ATRI 停止说话；
用户说完，ATRI 自动识别并回复。
```

这个阶段不要求 TTS 走 WebSocket。  
因为打断当前播放只需要前端执行 stop。

### 4.3 第二阶段：打断 LLM 文字回复

如果只做第一阶段，用户开口时可以停止 TTS 播放，但后端可能还在继续生成 LLM 文本。

要实现“实时打断 LLM 文字回复”，atri 需要把当前聊天回复变成可取消任务。

概念上需要增加：

```text
每个 WebSocket 会话记录当前正在生成的回复任务
```

当 VAD 触发 interrupt：

```text
后端找到当前会话的回复任务
  -> 取消 LLM 文本流
  -> 停止继续发送 output:chat:chunk
  -> 标记本轮回复被用户打断
```

这会让打断从“播放级”升级到“对话级”。

对用户的体感区别是：

```text
播放级打断：
  ATRI 停止出声，但后端可能还在生成原回复。

对话级打断：
  ATRI 停止出声，同时停止继续思考/输出原回复。
```

### 4.4 第三阶段：TTS 也迁入 WebSocket

如果要更像 OLV，可以把 TTS 从 REST API 播放模式迁到 WebSocket 音频 payload 模式。

目标链路：

```text
LLM 输出文本片段
  -> 后端按句子切分
  -> 后端创建 TTS 任务
  -> TTS provider 生成音频
  -> 后端通过 WebSocket 发 output:audio
  -> 前端按顺序播放
```

这样做之后，后端可以统一管理：

```text
LLM 文字生成任务
TTS 合成任务
TTS 音频发送队列
前端播放状态
VAD 打断状态
```

这更接近 OLV。

但这不是第一阶段必须做的。  
原因是 atri 当前 REST TTS 已经能工作，VAD 打断播放也可以先通过 WebSocket control 事件触发前端 stop。

### 4.5 如果 TTS provider 不支持流式怎么办

这不阻碍实现 VAD 实时打断。

OLV 里的很多 API TTS provider 也不是 provider 级真流式。  
它们通常是：

```text
一段文本
  -> API 返回完整音频
  -> 后端包装成 WebSocket audio payload
  -> 前端播放
```

如果 provider 不支持流式，仍然可以做：

```text
LLM 回复按句子切分
  -> 每句单独调用 TTS API
  -> 每句生成一个完整音频
  -> 生成完一句就发给前端
```

这叫“分段合成”，不是“真流式合成”。  
它的优点是实现难度低，能显著减少等待时间。  
它的缺点是 TTS 请求次数更多，队列和取消逻辑更复杂。

### 4.6 推荐的 atri 目标链路

推荐 atri 最终形成这条链路：

```text
前端麦克风
  -> WebSocket audio chunk
  -> 后端 VAD

VAD 检测到用户开始说话
  -> 后端 control:interrupt
  -> 前端停止当前 TTS 播放
  -> 后端取消当前 LLM 回复任务
  -> 后端标记当前回复被用户打断

VAD 检测到用户说完
  -> 后端得到完整语音片段
  -> ASR 转文字
  -> 文字进入 ChatAgent
  -> LLM 生成回复
  -> 前端显示文字流
  -> TTS 合成并播放
```

第一版可以保持：

```text
TTS 仍然 REST API 返回完整音频
```

后续再升级为：

```text
TTS 分段合成，WebSocket 下发音频 payload
```

## 5. 插件式模块设计原则

VAD 不应该硬编码进 ASR、TTS 或聊天路由里。

更合适的概念结构是：

```text
VADService
  -> 读取 VAD 配置
  -> 管理当前 VAD provider
  -> 接收音频 chunk
  -> 输出语音事件

VADProvider
  -> silero_vad
  -> 未来可扩展 webrtc_vad / sherpa_onnx_vad / browser_vad 等
```

VAD 对外只暴露语义事件：

```text
speech_start
speech_end
speech_chunk
silence
```

> Silero 是一组开源语音 AI 模型。这里说的 Silero VAD，就是其中的“语音活动检测”模型。

聊天 WebSocket 不需要知道 Silero 的细节。  
ASR 也不需要知道 Silero 的细节。  
TTS 也不需要知道 Silero 的细节。

它们只需要响应 VAD 产生的事件：

```text
speech_start -> 打断当前输出
speech_end   -> 把完整语音送去 ASR
```

这样才符合 atri 现有模块风格。

## 6. atri 中两条语音链路的关系

atri 加入 VAD 后，可以理解为两条链路：

### 6.1 输入链路：ASR + VAD

这条链路应该走 WebSocket，由后端控制。

```text
前端麦克风实时音频
  -> WebSocket
  -> 后端 VAD 判断开始/结束
  -> 后端 ASR 转文字
  -> 后端进入聊天链路
```

原因：

- VAD 要实时。
- 打断要实时。
- 后端需要知道什么时候取消 LLM。
- 前端不应该只在录完后才把音频交给后端。

### 6.2 输出链路：LLM + TTS

这条链路有两种可选形态。

当前 atri 形态：

```text
LLM 完整回复
  -> 前端调用 REST TTS
  -> 后端返回完整音频
  -> 前端播放
```

OLV 形态：

```text
LLM 片段回复
  -> 后端 TTS 任务
  -> 后端 WebSocket 下发 audio payload
  -> 前端播放
```

为了实现 VAD 打断，不必第一步就把 TTS 改成 OLV 形态。  
但如果要实现更完整的 OLV 体验，最终应该让 TTS 也纳入 WebSocket 对话控制。

## 7. 分阶段落地建议

### 7.1 MVP：实时停止播放

目标：

```text
用户一开口，ATRI 停止当前 TTS 播放。
```

需要：

- 前端麦克风音频通过 WebSocket 上行。
- 后端 VAD 实时检测 speech_start。
- 后端发 interrupt 控制事件。
- 前端收到后调用现有 stop 播放逻辑。

不需要：

- TTS WebSocket 化。
- 真流式 TTS。
- 复杂的 TTS 队列重构。

### 7.2 第二步：实时打断 LLM 文字回复

目标：

```text
用户一开口，ATRI 不仅停止说话，也停止继续生成原来的文字回复。
```

需要：

- 后端把当前 LLM 回复流作为可取消任务管理。
- interrupt 事件触发任务取消。
- 前端停止继续接受/展示旧回复，或把旧回复标记为被打断。
- 记忆系统能记录“本轮回复被用户打断”。

### 7.3 第三步：OLV 式 TTS WebSocket 化

目标：

```text
后端统一管理 LLM、TTS、VAD、播放控制。
```

需要：

- 后端按句子或片段创建 TTS 任务。
- TTS 音频通过 WebSocket 发给前端。
- 前端播放后回传播放完成状态。
- interrupt 时后端清理未播放的 TTS 队列。

这一步收益高，但改动最大，建议等 VAD MVP 稳定后再做。

## 8. 最终结论

atri 要实现 OLV 相近的 VAD 实时打断，不是简单新增一个 `/api/vad/detect`。

真正需要的是一条实时控制链路：

```text
麦克风音频 WebSocket 上行
  -> 后端 VAD
  -> speech_start 触发 interrupt
  -> 停止 TTS 播放
  -> 取消 LLM 输出
  -> speech_end 触发 ASR
  -> 自动进入下一轮对话
```

TTS 是否立刻改成 WebSocket 音频下发，是另一个层级的问题。

推荐决策：

```text
第一版：
  VAD + ASR 走 WebSocket
  TTS 继续 REST
  实现实时停止播放 + 自动语音输入

第二版：
  加入 LLM 回复任务取消
  实现真正对话级打断

第三版：
  TTS 迁入 WebSocket audio payload
  实现更接近 OLV 的统一语音链路
```

这样既能复用 OLV 的正确设计思想，又不会一次性重构 atri 当前已经可用的 TTS 播放体系。
