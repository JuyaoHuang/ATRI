---
status: active
owner: vision
created: 2026-07-10
updated: 2026-07-11
related_code:
  - src/agent/chat_agent.py
  - src/llm/interface.py
  - src/llm/providers/openai_compatible.py
  - src/llm/providers/siliconflow.py
  - src/llm/providers/xiaomi.py
  - src/memory/manager.py
  - src/routes/chat_ws.py
  - frontend/src/components/chat/InputBox.vue
  - frontend/src/components/chat/MessageList.vue
  - frontend/src/components/chat/MessageItem.vue
  - frontend/src/components/live2d/StageChatHistory.vue
  - frontend/src/composables/useChat.ts
  - frontend/src/composables/useWebSocket.ts
  - frontend/src/stores/chat.ts
  - frontend/src/utils/websocketSessionController.ts
---

# ATRI 屏幕视觉理解功能设计

## 1. 文档定位

本文是 ATRI 首版视觉理解功能的实现依据，描述本次 feature 的目标、边界、数据模型、前后端协议、generation 生命周期、失败语义、持久化规则和安全约束。

首版范围已经明确收敛为：

> 用户主动开启屏幕共享流后，每当一轮最终输入文本即将发送给 LLM 时，从当前屏幕共享流截取一张静态图片，并将该图片与本轮文本共同发送给支持多模态输入的 LLM。

首版不实现摄像头输入，也不实现用户手动选择静态图片上传。数据模型保留后续扩展空间，但当前协议只接受 `source=screen`。

本文属于 feature 过程设计文档。功能完成后，长期有效的结论需要同步沉淀到 Agent、LLM、Memory、Routes、Frontend 和 WebSocket API 模块文档。

## 2. 决策摘要

本次设计采用以下结论：

1. 视觉理解依赖当前 LLM Provider 和模型自身的多模态能力，不引入 OCR、图像识别服务或独立视觉模型。
2. 视觉流只在浏览器本地持续存在，不持续上传视频，也不持续分析画面。
3. 每轮最终 `InputText` 产生后，最多截取并附带一张当前屏幕静态图像。
4. 文本和图片共同组成 `InputInform`；图片不是文本的一部分，也不会拼接到文本字符串中。
5. 图片使用 Canvas 缩放并编码为 JPEG，再以 Base64 字符串放入现有 WebSocket JSON 文本帧。
6. Base64 只允许存在于浏览器到后端的临时传输边界和后端到 Provider 的临时请求边界。
7. 图片、Base64、图片字节和图片元数据均不进入聊天归档、短期记忆、长期记忆或压缩块。
8. `MemoryManager` 仍然只使用 `InputText` 做长期记忆检索和上下文组装。
9. 只有最终的当前 user 消息在 Provider 调用边界被升级为多模态消息。
10. 本地截图、编码、校验或等待失败时，本轮自动降级为纯文本，并且 `InputText` 只发送一次。
11. LLM 请求失败时，本轮不进入 ChatStorage 或 Memory，只在当前前端页面显示瞬态错误气泡。
12. 模型通过 HTTP 200 正常生成“我看不到图片”等自然语言拒绝时，仍视为成功回复并正常归档。
13. 错误事件必须携带 `generation_id`，并与 VAD interrupt 使用同一套 generation 失效和迟到结果丢弃规则。
14. 通用协议错误与 generation 失败事件分离，避免无关错误误终止当前聊天。
15. 首版不使用二进制 WebSocket 帧、不建立通用 TurnAssembler，也不自动把失败的多模态请求重试为纯文本请求。

## 3. 背景与当前问题

ATRI 目前已经有三种最终文本输入来源：

- 键盘输入；
- 普通单次 ASR 最终转写；
- 后端 VAD + ASR 最终转写。

前两者最终汇聚到前端 `useChat.sendMessage()`，后者由后端在 ASR 完成后直接进入聊天生成。视觉功能必须覆盖这三种来源，同时保持现有文本、VAD、TTS、Live2D、聊天归档和 Memory 行为不发生无关变化。

当前还存在一个与视觉功能直接相关的错误路径缺陷：

1. LLM Provider 抛出 `LLMError`。
2. `ChatAgent.chat()` 捕获异常并生成 `[LLM call failed: ...]` 文本。
3. 该文本被作为普通 AI chunk 继续返回。
4. WebSocket 编排层将其视为成功回复。
5. 用户输入和错误文本可能被写入聊天归档、Memory、近期消息和压缩流程。
6. 前端把错误文本当作 AI 回复渲染，并可能暴露给 TTS 或 Live2D 链路。

该行为与本次要求冲突。本 feature 包含对这条错误路径的修复，但不扩展成完整的全局错误系统重构。

## 4. 目标

### 4.1 功能目标

- 用户可以显式开启和关闭屏幕共享视觉流。
- 视觉流开启后，键盘文本和普通 ASR 文本发送前自动截取当前屏幕的一帧。
- VAD + ASR 得到最终文本后，后端请求浏览器截取当前屏幕的一帧。
- 截图成功时，文本和图片作为同一轮输入交给 LLM。
- 截图失败时，当前文本按纯文本继续发送，不阻塞对话。
- 视觉流关闭时，现有文本聊天路径保持不变。

### 4.2 架构目标

- `InputText`、`InputImage` 和执行上下文边界清晰。
- Memory 不感知图片和 Base64。
- Provider 负责最终多模态协议序列化。
- VAD 截图等待不阻塞 WebSocket 接收循环。
- generation complete、interrupt 和 failure 具有一致且可验证的终态竞争规则。
- generation 失败不会伪装成 AI 消息。

### 4.3 安全目标

- 不在日志、异常文本、测试输出或快照中打印 Base64。
- 不持久化屏幕截图及其元数据。
- 屏幕共享必须由用户主动触发，浏览器刷新后不自动恢复权限。
- 对传输大小、MIME、Base64 语法和解码后字节数进行限制。

## 5. 非目标

首版明确不实现：

- 摄像头输入；
- 用户手动选择静态图片上传；
- 同一轮附带多张图片；
- 同时附带屏幕和摄像头画面；
- 连续视频上传；
- 后台持续截图或持续分析；
- 没有用户输入时主动观察或发言；
- OCR 服务、图像 embedding、图片摘要或图片记忆；
- 图片或图片元数据持久化；
- 二进制 WebSocket 帧；
- REST 附件上传和文件存储服务；
- 通用多附件 TurnAssembler；
- Provider 能力探测或维护模型视觉能力白名单；
- 新增 `LLMRequestError` 异常层级；
- 根据自然语言判断模型是否拒绝看图；
- 远端多模态请求失败后自动重试纯文本请求；
- 自动删除首次请求失败后形成的 `message_count=0` 空聊天；
- 持久化前端瞬态错误历史。

## 6. 术语与数据模型

### 6.1 InputText

`InputText` 是本轮最终文本输入的统一名称，来源包括：

- 键盘文本；
- 普通前端 ASR 最终转写；
- 后端 VAD + ASR 最终转写。

图片不会插入或拼接进 `InputText.content`。

### 6.2 InputImage

`InputImage` 是本轮从当前活动屏幕共享 MediaStream 中截取的一张静态 JPEG 图片。

首版稳定字段为：

```python
@dataclass(frozen=True, slots=True)
class InputImage:
    source: Literal["screen"]
    media_type: Literal["image/jpeg"]
    encoding: Literal["base64"]
    data: str = field(repr=False)
```

约束：

- `data` 必须使用 `repr=False` 或等效的安全表示；
- 每轮最多一个 `InputImage`；
- 图片不可用时使用 `None`；
- 该对象只在当前请求生命周期内存在。

### 6.3 InputInform

`InputInform` 是发送给 LLM 理解的本轮完整信息：

```python
@dataclass(frozen=True, slots=True)
class InputInform:
    input_text: InputText
    image: InputImage | None = None
```

### 6.4 ChatTurnContext

以下字段属于路由和执行上下文，不属于 LLM 需要理解的 `InputInform`：

- `chat_id`；
- `character_id`；
- `user_id`；
- `generation_id`；
- `client_context`；
- WebSocket send lock；
- TTS manager；
- 当前页面和连接状态。

这些字段不应混入 `InputText` 或图片内容。

## 7. 核心数据边界

```text
InputInform
     │
     ├── InputText ───────────────> MemoryManager
     │                              ├── 长期记忆检索
     │                              ├── 历史上下文
     │                              ├── runtime context
     │                              └── 当前最终 user 文本消息
     │
     └── InputImage? ─────────────────────────┐
                                               ▼
                                    Provider 调用边界
                                    仅升级当前最终 user 消息
                                               │
                                               ▼
                                              LLM
```

必须保持以下不变量：

1. `MemoryManager.build_llm_context()` 只接收 `InputText.content`。
2. 长期记忆查询只使用 `InputText`。
3. `recent_messages`、`active_blocks`、`meta_blocks` 和压缩块只保存文本。
4. `on_round_complete()` 只接收文本 user/AI 消息。
5. ChatStorage 只保存文本，不保存图片或图片元数据。
6. Provider 调用前复制消息列表，不把多模态结构回写到 Memory 状态。
7. `image=None` 时保持现有字符串 `content` 形态，不改变纯文本请求。

## 8. 模块职责

### 8.1 前端 Vision Runtime

前端视觉运行时负责：

- 通过用户手势调用 `getDisplayMedia()`；
- 持有当前屏幕共享 `MediaStream`；
- 维护 `disabled / starting / active / error` 等运行时状态；
- 从活动流截取一帧；
- Canvas 缩放和 JPEG 编码；
- 在发送前执行大小检查；
- 响应后端的 VAD 截图请求；
- 在用户停止共享或页面卸载时释放 tracks。

MediaStream 可以由专用 service/composable 持有，但 Base64 帧不得存入 Pinia、localStorage、IndexedDB、OPFS 或 Vue devtools 可持久状态。

### 8.2 前端 Vision Store

Pinia 只保存轻量运行时投影：

- 模块是否可用；
- 当前是否已开启屏幕共享；
- 当前状态；
- 最近一次安全错误描述；
- 配置中的压缩和大小限制。

Pinia 不保存：

- MediaStream 的图片帧；
- Canvas 内容；
- Blob；
- ArrayBuffer；
- Base64；
- data URL。

### 8.3 VisionCaptureCoordinator

后端每条 WebSocket 连接持有一个轻量 `VisionCaptureCoordinator`，职责是：

- 按 `generation_id` 注册一个 pending Future；
- 发送截图请求前先完成 Future 注册；
- 收到截图结果时解析并 resolve 对应 Future；
- 处理失败、超时、取消、断开和重复响应；
- 对迟到或未知 generation 的结果直接丢弃。

它不负责：

- 组装完整聊天历史；
- 管理多个附件；
- 决定 Memory 提交；
- 运行 LLM。

### 8.4 ChatAgent

`ChatAgent` 负责：

- 使用 `InputText` 调用 `MemoryManager.build_llm_context()`；
- 把可选 `InputImage` 传给 LLM 调用边界；
- 流式返回成功的文本 chunk；
- 让 `LLMError` 保持异常控制流，不转换成文本。

### 8.5 LLM Provider

Provider 负责：

- 把可选 `InputImage` 序列化为自身协议支持的多模态内容；
- 只修改当前最后一条 user 消息；
- 将 SDK 异常映射为现有 `LLMError` 家族；
- 不记录完整 request params 或 messages。

## 9. 屏幕共享生命周期

### 9.1 开启

开启屏幕共享必须由用户点击视觉控制按钮触发：

```ts
navigator.mediaDevices.getDisplayMedia({
  video: true,
  audio: false
})
```

浏览器负责让用户选择共享整个屏幕、窗口或标签页。ATRI 不绕过浏览器权限选择器，也不自动选择共享目标。

只有满足以下条件时才标记视觉流为 `active`：

- 存在 live video track；
- video 元数据已经可用；
- 当前帧尺寸大于零；
- track 未结束、未静音失效。

### 9.2 关闭

以下情况必须关闭视觉流并停止所有 tracks：

- 用户点击关闭；
- 浏览器共享指示器中点击停止共享；
- video track 触发 `ended`；
- 页面卸载；
- 视觉运行时显式销毁。

关闭后立即同步 `input:vision:state(enabled=false)`，后续输入走纯文本路径。

### 9.3 刷新与重连

- 页面刷新后视觉流默认为关闭；
- 不持久化“已授权”假象；
- WebSocket 重连时，若当前 MediaStream 仍然有效，则重新同步当前状态；
- 如果流已失效，则同步关闭状态。

## 10. 截图与编码

### 10.1 截图步骤

```text
读取当前 video frame
  -> 按最大长边等比缩放
  -> 绘制到临时 Canvas
  -> canvas.toBlob(image/jpeg, quality)
  -> 检查 Blob 字节数
  -> 转为 Base64
  -> 构造 InputImage
  -> 立即发送并释放局部引用
```

### 10.2 建议首版默认值

所有值必须来自统一配置，不得散落在组件和路由中：

| 配置项 | 建议默认值 | 说明 |
|---|---:|---|
| `enabled` | `false` | 模块默认不主动共享屏幕。 |
| `media_type` | `image/jpeg` | 首版唯一允许格式。 |
| `jpeg_quality` | `0.82` | 在屏幕文字可读性与体积之间折中。 |
| `max_long_edge` | `1920` | 保留常见桌面文字可读性。 |
| `max_decoded_bytes` | `4194304` | 单张图最大 4 MiB。 |
| `capture_timeout_ms` | `1500` | VAD 等待截图的最大时间。 |
| `provider_detail` | `auto` | OpenAI 兼容图片 detail。 |
| `websocket_max_message_bytes` | `8388608` | 整个 JSON 文本帧最大 8 MiB。 |

这些值允许在实现和真实模型验证后调整，但只能通过配置调整。

### 10.3 超限处理

前端在发送前检查 Blob 和 Base64 长度：

- 首次编码超限时允许进行有界的再次缩放和编码；
- 不允许无限压缩循环；
- 仍然超限时放弃图片并走纯文本；
- 不把超限 Base64 传给 WebSocket 层。

后端仍必须独立执行同样的安全校验，不能信任浏览器客户端。

## 11. 三种 InputText 链路

### 11.1 键盘输入

```text
InputBox.handleSend
  -> 获取 submission gate
  -> 确认或创建 chat_id
  -> 若屏幕视觉流 active，截取一帧
  -> capture 成功：InputInform(text, image)
  -> capture 失败：InputInform(text, image=None)
  -> chatStore.beginStreaming()
  -> WebSocketSessionController.sendText()
  -> 后端共享聊天执行链路
```

由于截图和 JPEG 编码包含异步步骤，前端需要一个 submission gate：

```text
connectionBusy = submissionPending || activeStream != null
```

该 gate 必须在第一次 `await` 之前建立，防止快速双击或连续 Enter 导致同一文本发送两次。

### 11.2 普通单次 ASR

普通 ASR 的最终 transcript 会写回 `InputBox`，然后复用 `handleSend()` 和 `useChat.sendMessage()`。

因此它与键盘输入共享：

- submission gate；
- 屏幕截图时机；
- `input:text` 协议；
- 本地失败降级；
- generation 接收和前端渲染。

不为普通 ASR 创建第二套截图实现。

### 11.3 后端 VAD + ASR

```text
input:audio:chunk
  -> VAD speech_end
  -> 后端 ASR 最终 transcript
  -> 分配 generation_id
  -> output:asr:transcript
  -> 启动 tracked generation task
       -> 视觉流关闭：image=None
       -> 视觉流开启：请求浏览器截图并等待结果
       -> 构造 InputInform
       -> 执行共享聊天链路
```

VAD 路径中的截图时机是：

> 最终 ASR 文本已经确定之后，LLM 请求开始之前。

## 12. WebSocket 协议

### 12.1 同步视觉流状态

客户端开启视觉流：

```json
{
  "type": "input:vision:state",
  "data": {
    "enabled": true,
    "source": "screen"
  }
}
```

客户端关闭或失去视觉流：

```json
{
  "type": "input:vision:state",
  "data": {
    "enabled": false
  }
}
```

规则：

- 该状态只属于当前 WebSocket 连接；
- 旧客户端从未发送该事件时，后端默认视觉流关闭；
- 状态中不包含图像；
- 状态不持久化。

### 12.2 键盘和普通 ASR 的 `input:text`

现有 `input:text` 增加可选 `image` 字段：

```json
{
  "type": "input:text",
  "data": {
    "text": "请看看我现在的屏幕",
    "chat_id": "chat_xxx",
    "character_id": "atri",
    "client_context": {},
    "image": {
      "source": "screen",
      "media_type": "image/jpeg",
      "encoding": "base64",
      "data": "<opaque-base64>"
    }
  }
}
```

兼容规则：

- 无图片时完全省略 `image`；
- 旧客户端的纯文本 payload 保持有效；
- 后端图片校验失败只丢弃图片，不拒绝合法文本；
- `image.data` 不允许出现在日志和错误响应中。

### 12.3 VAD 截图请求

后端请求当前 generation 的屏幕帧：

```json
{
  "type": "control:vision:capture-request",
  "data": {
    "generation_id": "gen_xxx",
    "chat_id": "chat_xxx",
    "character_id": "atri",
    "source": "screen"
  }
}
```

### 12.4 VAD 截图成功结果

```json
{
  "type": "input:vision:capture-result",
  "data": {
    "generation_id": "gen_xxx",
    "status": "captured",
    "image": {
      "source": "screen",
      "media_type": "image/jpeg",
      "encoding": "base64",
      "data": "<opaque-base64>"
    }
  }
}
```

### 12.5 VAD 截图失败结果

```json
{
  "type": "input:vision:capture-result",
  "data": {
    "generation_id": "gen_xxx",
    "status": "unavailable"
  }
}
```

允许状态：

- `captured`：存在合法 `image`；
- `unavailable`：视觉流不存在、已停止或当前帧不可用；
- `failed`：截图或编码失败。

非 `captured` 状态统一解析为 `image=None`，随后走纯文本。

### 12.6 generation 失败事件

generation 在成功提交前失败时发送：

```json
{
  "type": "output:chat:error",
  "data": {
    "message": "本轮回复生成失败。当前模型或服务可能不支持视觉输入。",
    "chat_id": "chat_xxx",
    "character_id": "atri",
    "generation_id": "gen_xxx"
  }
}
```

规则：

- `chat_id`、`character_id`、`generation_id` 必填；
- `message` 必须是安全、可展示且不包含原始 Provider request 的文案；
- 该事件固定表示当前页面瞬态失败，不需要额外 `transient=true`；
- 该事件不表示 WebSocket 连接失败。

### 12.7 通用 `error`

顶层 `error` 保留给未绑定 generation 的协议或输入错误，例如：

- 非法 JSON；
- 缺少 `type`；
- 未知消息类型；
- 无法关联 generation 的字段错误。

前端必须将其映射为 `protocol:error` 或等价事件，不能调用 generation 失败 action。

## 13. VAD 截图异步协调

### 13.1 禁止在接收循环内直接等待

WebSocket 主循环当前按顺序执行 `receive_text()` 和消息 handler。如果在 `input:audio:chunk` 的 speech-end handler 内发送截图请求后直接等待截图 Future，会形成死锁：

```text
handler 等待 capture-result
  +
接收循环尚未返回 receive_text()
  =
后端无法接收 capture-result
```

### 13.2 正确执行模型

```text
WebSocket 接收循环
  -> speech_end
  -> 完成 ASR
  -> 发送 output:asr:transcript
  -> _start_tracked_chat_task(capture_then_chat)
  -> handler 返回
  -> 继续 receive_text()

tracked generation task
  -> coordinator.register(generation_id)
  -> 发送 capture-request
  -> await Future / timeout
  -> 构造 InputInform
  -> 运行 LLM

WebSocket 接收循环
  -> 收到 capture-result
  -> coordinator.resolve(generation_id)
```

必须在发送 capture request 之前注册 Future，避免浏览器快速响应造成结果先到、Future 后建的竞态。

### 13.3 清理规则

Coordinator 在以下情况删除 pending entry：

- 成功解析；
- `unavailable` 或 `failed`；
- 超时；
- generation 被 interrupt；
- tracked task 被取消；
- WebSocket 断开；
- payload 校验失败。

迟到、重复或未知 generation 的响应直接丢弃，不产生聊天错误气泡。

## 14. 后端图片校验

后端校验顺序必须固定：

1. `image` 是对象；
2. `source == "screen"`；
3. `media_type == "image/jpeg"`；
4. `encoding == "base64"`；
5. `data` 是非空字符串；
6. 解码前检查 encoded length；
7. 使用 strict Base64 解码；
8. 检查 decoded byte length；
9. 检查 JPEG 基本签名；
10. 构造安全的 `InputImage`。

任一步失败：

```text
记录安全 warning
  -> image=None
  -> InputText 继续一次
```

禁止把校验异常对象的完整 repr 返回前端，因为某些验证库会把原始 input 值包含在错误文本中。

## 15. LLM 多模态序列化

### 15.1 接口边界

建议在 `LLMInterface.chat_completion_stream()` 增加仅关键字可选参数：

```python
def chat_completion_stream(
    self,
    messages: list[dict[str, Any]],
    system: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    *,
    input_image: InputImage | None = None,
) -> AsyncIterator[str]:
    ...
```

标题生成、Memory 压缩等调用不传 `input_image`，行为不变。

### 15.2 OpenAI 兼容表示

有图片时，Provider 复制最后一条当前 user 消息，并转换为：

```json
{
  "role": "user",
  "content": [
    {
      "type": "text",
      "text": "<InputText，包括当轮 runtime context>"
    },
    {
      "type": "image_url",
      "image_url": {
        "url": "data:image/jpeg;base64,<opaque-base64>",
        "detail": "auto"
      }
    }
  ]
}
```

无图片时保持：

```json
{
  "role": "user",
  "content": "<InputText>"
}
```

### 15.3 Provider 支持语义

- ATRI 不预判当前模型是否支持视觉；
- `OpenAICompatibleLLM`、`SiliconFlowLLM` 和 `XiaomiLLM` 负责按其协议提交；
- 模型支持时正常返回；
- Provider 拒绝请求时抛出现有 `LLMError`；
- 不新增能力注册表或 Provider 能力字段。

## 16. 失败策略

### 16.1 本地图片准备失败

包括：

- 用户没有开启屏幕共享；
- 用户停止共享；
- MediaStream 或 video frame 不可用；
- Canvas 绘制失败；
- JPEG 编码失败；
- 图片超出大小预算；
- Base64 转换失败；
- 后端图片校验失败；
- VAD 截图等待超时。

统一行为：

```text
image=None
  -> InputText 发送一次
  -> 若纯文本 LLM 调用成功，正常归档和提交 Memory
```

本地失败不产生 `output:chat:error`，因为聊天仍可继续。

### 16.2 远端 LLM 失败

任何 Provider `LLMError` 都结束本 generation：

```text
LLMError
  -> 不再生成 AI 文本 chunk
  -> 中断并丢弃该 generation 的 TTS
  -> 发送 output:chat:error
  -> 不写 ChatStorage
  -> 不写 Memory archive
  -> 不调用 append_system_note()
  -> 不调用 on_round_complete()
  -> 不更新 recent_messages / total_rounds
  -> 不触发压缩或长期记忆
```

如果错误前已经发送过部分 chunk：

- 前端清空 `streamingText`；
- 已排队或正在播放的该 generation 音频被丢弃；
- partial reply 不作为普通或 interrupted 消息归档；
- 当前页面只保留用户 InputText 和错误气泡。

### 16.3 HTTP 200 自然语言拒绝

如果模型成功返回：

```text
抱歉，我无法查看图片。
```

该响应仍然属于成功 LLM 回复：

- 正常显示；
- 正常归档；
- 正常进入 Memory；
- 可正常触发 TTS 和 Live2D；
- 不做自然语言拒绝检测。

### 16.4 不自动重试

远端多模态请求失败后不自动去掉图片重试，原因包括：

- 无法可靠判断请求在 Provider 侧是否已经产生费用或副作用；
- 自动重试可能造成重复回复；
- 失败原因不一定是模型不支持图片；
- 用户已经要求失败轮次不进入历史。

## 17. generation 终态与 VAD 竞争

同一个 generation 只有三个有效终态：

- complete；
- interrupted；
- failed。

规则是：

> 第一个在 WebSocket send lock 内成功提交的终态获胜，后续终态全部丢弃。

### 17.1 generation-aware 错误发送

错误发送必须在 send lock 内执行：

```text
acquire send_lock
  -> is_generation_active(generation_id)
  -> false: return ignored
  -> true: send output:chat:error
  -> invalidate generation
release send_lock
  -> interrupt TTS generation
```

不能继续使用先无条件 `_send_error()`、再在锁外 invalidate 的顺序。

### 17.2 Error 先于 VAD interrupt

```text
Error(A) 先获得锁
  -> 前端显示 Error(A)
  -> A 失效
  -> 后续 VAD interrupt 不再把 A 作为 active generation
```

已经显示的错误气泡保留到页面刷新或聊天重新加载。

### 17.3 VAD interrupt 先于 Error

```text
VAD interrupt(A) 先获得锁
  -> A 失效
  -> control:interrupt(A)
  -> 后续 Error(A) 检查失败并被丢弃
```

如果 generation B 已经开始，迟到的 Error(A) 不能终止 B，也不能显示到 B 所属聊天中。

## 18. 现有 ChatAgent 错误路径修复

本 feature 要把 `ChatAgent` 从“错误文本生成者”恢复为组合层：

### 当前行为

```text
LLMError
  -> yield [LLM call failed: ...]
  -> append_system_note()
  -> 路由误判为成功
```

### 目标行为

```text
LLMError
  -> 直接向 WebSocket 编排层传播
  -> 编排层在成功持久化之前处理
  -> generation-aware failure event
```

实现约束：

- 删除错误 sentinel chunk；
- 删除该路径的 `append_system_note()`；
- 修正 ChatAgent docstring 和长期模块文档；
- LLM stream 完整成功后才进入成功归档路径；
- 不能在已经完成成功持久化后再把辅助模块异常重新标记成“LLM generation 失败”。

## 19. 前端瞬态失败设计

### 19.1 不能伪造 AI Message

当前 `Message` 只有 `human | ai` role，`MessageItem` 还会为 AI 消息提供 TTS 能力。因此错误不能使用：

```ts
role: 'ai'
```

也不应扩展成 `role: 'error'`，因为 error 不是对话作者。

### 19.2 时间线联合类型

```ts
interface ChatMessageItem extends Message {
  kind: 'message'
}

interface ChatNoticeItem {
  kind: 'notice'
  id: string
  chat_id: string
  generation_id: string
  level: 'error'
  content: string
  timestamp: string
}

type ChatTimelineItem = ChatMessageItem | ChatNoticeItem
```

`chatStore.messages` 应升级为语义更准确的 `timelineItems`，或提供等价的统一时间线状态。

### 19.3 通用失败 action

不使用 UI 耦合名称：

```ts
failActiveGenerationWithErrorBubble(...)
```

推荐使用：

```ts
type GenerationApplyResult = 'ignored' | 'hidden' | 'visible'

failActiveGeneration(payload: {
  chatId: string
  characterId: string
  generationId: string
  failure: {
    message: string
  }
}): GenerationApplyResult
```

action 职责：

1. 严格匹配当前 `activeStream` 的 chat、character 和 generation；
2. 当前尚未绑定后端 generation 时，允许由第一条完整关联事件绑定；
3. 不匹配 `pendingInterruptedStream`；
4. stale generation 返回 `ignored`；
5. 匹配成功后清空 `activeStream` 和 `streamingText`；
6. 当前聊天可见时追加 `ChatNoticeItem`；
7. 当前聊天不可见时结束状态但不追加通知；
8. 返回结果供 WebSocket handler 决定是否丢弃音频。

Store 不负责：

- 构造 Vue 组件；
- 控制 TTS 播放器；
- 控制 Live2D；
- 设置 WebSocket 连接错误。

### 19.4 handler 副作用

`output:chat:error` 的默认 handler 只负责：

```text
chatStore.failActiveGeneration()
  -> ignored: 不做任何事
  -> visible/hidden: discardGenerationAudio(generation_id)
```

不调用：

- `enqueueAutoSpeech()`；
- `live2dStore.requestExpression()`；
- `wsStore.setError()`。

### 19.5 渲染组件

普通聊天的 `MessageList` 和 Stage 模式的 `StageChatHistory` 应共用一个时间线分发组件：

```text
ChatTimelineItem
  ├── kind=message -> MessageItem
  └── kind=notice  -> ChatErrorBubble
```

`ChatErrorBubble` 必须：

- 使用消息气泡形式；
- 明确区别于 AI 回复；
- 支持 default 和 stage 两种 variant；
- 支持亮色和暗色主题；
- 不显示角色头像或 TTS 按钮；
- 使用可访问的错误语义，但不抢夺键盘焦点；
- 不写入任何本地持久化。

实际开发 `ChatErrorBubble` 时，按项目要求调用 `design-taste-frontend` 和 `ui-ux-pro-max` 完成视觉设计与可访问性检查。本文不冻结具体颜色和样式。

## 20. 前端历史与刷新语义

ATRI 当前存在三层相互独立的历史：

| 层 | 当前机制 | LLM 失败轮次 |
|---|---|---|
| 前端页面时间线 | Pinia runtime state | 保留失败的用户文本和错误气泡。 |
| 聊天归档 | ChatStorage + `GET /api/chats/{id}` | 不保存失败轮次。 |
| Memory 历史 | chat history、recent、blocks、long-term | 不保存失败轮次。 |

刷新或重新加载聊天时：

```text
Pinia 重置
  -> loadHistory(chat_id)
  -> REST 返回归档 human/AI 消息
  -> timelineItems 被整体替换
  -> 瞬态用户文本和错误气泡消失
```

切换到其他聊天后再切回并重新加载时，行为相同。

首次发送失败时，后端可能已经创建一个标题和 `message_count=0` 的空 chat。该既有行为不在本 feature 中清理。

## 21. Base64 与日志安全

### 21.1 禁止输出的内容

任何环境都不得输出：

- 图片 Base64；
- data URL；
- 原始图片字节；
- 完整 `InputInform`；
- 完整 WebSocket 图片 payload；
- 完整 Provider messages；
- 完整 request params；
- 包含图片值的 Pydantic/校验异常 repr；
- 可能回显请求体的原始 Provider exception 字符串。

### 21.2 允许记录的字段

允许记录：

- `generation_id`；
- `chat_id`；
- `source=screen`；
- MIME；
- encoded/decoded length 整数；
- capture/encode/provider duration；
- validation status；
- Provider 和模型名；
- 安全状态码或 request ID；
- 异常类型名；
- success/failure boolean。

### 21.3 Provider 异常

Provider SDK 异常可能回显请求体，因此：

- 前端不显示原始 `str(exc)`；
- 路由不使用 `logger.error(f"...{exc}")` 记录多模态请求异常；
- 不使用会展开含图片局部变量的诊断日志；
- 前端只收到固定安全文案；
- 无需为此新增异常类。

### 21.4 测试约束

测试必须：

- 使用很小的合成 JPEG fixture；
- 把 Base64 当作 opaque 字段；
- 用长度、摘要或局部字段断言；
- 避免整包 equality assertion；
- 避免失败 diff 展开 Base64；
- 不读取或打印真实屏幕截图 Base64；
- 不把真实屏幕截图写入 snapshot 或测试产物。

## 22. 配置设计

新增视觉配置应统一放在：

```text
config/vision_config.yaml
```

建议结构：

```yaml
vision:
  enabled: false
  source: screen
  capture:
    media_type: image/jpeg
    jpeg_quality: 0.82
    max_long_edge: 1920
    max_decoded_bytes: 4194304
    timeout_ms: 1500
  provider:
    detail: auto
  transport:
    websocket_max_message_bytes: 8388608
```

配置职责：

- YAML 定义模块能力和限制；
- REST 配置接口向前端提供必要值；
- 前端运行时的“当前是否正在共享”不写回 YAML；
- 敏感信息不进入该配置。

## 23. 兼容性

### 23.1 旧客户端

- `input:text.image` 可选；
- 未发送 `input:vision:state` 时后端默认关闭视觉；
- 现有纯文本客户端继续工作；
- 旧客户端不会收到无意义的截图请求。

### 23.2 纯文本模型

- 视觉流关闭时完全保持现有行为；
- 视觉流开启时，纯文本模型可能由 Provider 拒绝请求；
- 拒绝进入 generation failure 路径；
- 不通过模型白名单提前阻止。

### 23.3 现有 VAD/TTS

- `generation_id` 继续作为文本、音频和 interrupt 的统一边界；
- 截图等待属于 tracked generation task；
- VAD speech_start 可以取消截图等待；
- 失败 generation 的 TTS 音频必须被后端中断、前端丢弃；
- TTS 单段失败仍使用 `output:audio:error`，不显示 ChatErrorBubble。

## 24. 取舍与被拒绝方案

### 24.1 Base64 JSON 与二进制 WebSocket

选择 Base64 JSON，因为：

- 与当前单一 JSON 文本帧协议兼容；
- 不需要设计二进制帧和文本元数据的配对协议；
- 首版每轮只有一张图，复杂度收益不足。

代价是约 33% 体积膨胀，因此必须限制图片尺寸并禁止日志输出。

### 24.2 LLM 多模态与独立 OCR

选择直接交给多模态 LLM，因为：

- 需求是通用画面理解，不只是文字识别；
- 避免新增 OCR 部署、配置和数据融合链路；
- 当前 LLM Provider 已经使用可承载图片的兼容协议。

### 24.3 截图按轮触发与持续视觉分析

选择按轮截图，因为：

- 用户明确要求在输入文本发送时携带当前画面；
- 降低隐私风险、带宽和 LLM 成本；
- 保持聊天仍由用户输入驱动。

### 24.4 VisionCaptureCoordinator 与 TurnAssembler

选择 generation-keyed Future coordinator，因为：

- VAD 路径只有一个额外的可选截图结果；
- 最终 transcript 已经先确定；
- 不需要通用 `transcript_ready && visual_ready` 状态机。

### 24.5 瞬态 Notice 与 AI 错误文本

选择独立 notice，因为：

- operational failure 不是 AI 回复；
- 防止错误进入 TTS、Live2D、ChatStorage 和 Memory；
- 刷新后自然由归档重建并消失。

## 25. 验收标准

### 25.1 屏幕流

- [ ] 用户必须通过明确操作开启屏幕共享。
- [ ] 视觉流关闭时现有纯文本链路不变。
- [ ] 用户停止浏览器共享后前端立即进入 disabled 状态。
- [ ] 页面刷新后不自动恢复屏幕共享。

### 25.2 输入链路

- [ ] 键盘 InputText 在视觉开启时附带一张当前屏幕图。
- [ ] 普通 ASR 最终文本复用键盘发送和截图链路。
- [ ] VAD + ASR 最终文本通过 generation 请求一张浏览器截图。
- [ ] VAD 截图等待不阻塞 WebSocket 接收循环。
- [ ] 每轮最多一张图片。
- [ ] submission gate 防止截图期间重复发送。

### 25.3 降级

- [ ] 截图、编码、超限、校验和超时失败均降级纯文本。
- [ ] 降级时 InputText 恰好发送一次。
- [ ] 图片校验失败不会把合法文本请求整体拒绝。

### 25.4 Memory 与持久化

- [ ] Memory 检索只接收 InputText。
- [ ] 只有最终当前 user 消息在 Provider 边界多模态化。
- [ ] ChatStorage 不包含图片、Base64 或图片元数据。
- [ ] recent messages、压缩块和长期记忆不包含图片。
- [ ] 成功轮次仍只以文本进入归档和 Memory。

### 25.5 LLM 失败

- [ ] `ChatAgent` 不再 yield 错误 sentinel。
- [ ] `LLMError` 不调用 `append_system_note()`。
- [ ] 失败轮次不写 ChatStorage。
- [ ] 失败轮次不调用 `on_round_complete()`。
- [ ] 失败轮次不更新 recent、round count、压缩和长期记忆。
- [ ] 后端发送 generation-aware `output:chat:error`。
- [ ] 前端以 ChatErrorBubble 显示瞬态 notice。
- [ ] 错误 notice 不触发 TTS 或 Live2D。
- [ ] 失败 generation 的部分文本和音频被清理。
- [ ] HTTP 200 自然语言拒绝仍走正常成功路径。

### 25.6 generation 竞争

- [ ] VAD interrupt 先完成时，迟到 Error 被丢弃。
- [ ] Error 先显示时，后续新 generation 不删除已显示错误。
- [ ] generation B 活跃时，Error(A) 不影响 B。
- [ ] complete、interrupt、failure 只有第一个终态生效。

### 25.7 页面生命周期

- [ ] 当前页面保留失败用户文本和错误气泡。
- [ ] 刷新页面后两者消失。
- [ ] 重新加载聊天后两者消失。
- [ ] 不写 localStorage、IndexedDB 或其他浏览器持久化。
- [ ] 空聊天清理行为保持不变。

### 25.8 安全

- [ ] 后端日志不出现图片 Base64、data URL 或原始字节。
- [ ] 前端控制台不打印图片 payload。
- [ ] Provider 异常不回显图片请求内容。
- [ ] 测试失败 diff 和 snapshot 不展开 Base64。
- [ ] WebSocket 和应用层均有大小限制。

## 26. 文档落地后的同步要求

实现完成后，需要更新以下长期文档：

- `docs/developments/modules/agent/chat-agent.zh-CN.md`
  - 删除“LLM 错误进入 memory archive”的旧语义；
  - 记录 `InputInform` 和异常传播边界。
- `docs/developments/modules/llm/call-layer.zh-CN.md`
  - 补充可选图片输入和 Provider 多模态序列化。
- `docs/developments/modules/memory/context-assembly.zh-CN.md`
  - 明确图片永远不进入 Memory 上下文存储。
- `docs/developments/modules/frontend/state-management.zh-CN.md`
  - 补充 vision runtime、timeline notice 和 generation failure action。
- `docs/developments/modules/frontend/chat-voice-runtime.zh-CN.md`
  - 补充截图触发、VAD capture handshake 和错误渲染。
- `docs/developments/modules/routes/design.zh-CN.md`
  - 补充 VisionCaptureCoordinator 和 generation failure 终态。
- `docs/developments/api/websocket.zh-CN.md`
  - 补充视觉状态、截图请求/结果和 `output:chat:error` 时序。
- `docs/developments/api/events.zh-CN.md`
  - 补充新增事件字段字典，并把顶层 `error` 收敛为通用协议错误。

## 27. 相关资料

- `README.md` 的“添加视觉理解能力”开发路线。
- `docs/developments/features/2026-06-vad-realtime-interrupt/README.zh-CN.md`。
- `docs/developments/features/2026-07-frontend-websocket-session-refactor/README.zh-CN.md`。
- `docs/developments/modules/agent/chat-agent.zh-CN.md`。
- `docs/developments/modules/llm/call-layer.zh-CN.md`。
- `docs/developments/modules/memory/context-assembly.zh-CN.md`。
- `docs/developments/modules/frontend/state-management.zh-CN.md`。
- `docs/developments/modules/frontend/chat-voice-runtime.zh-CN.md`。
- `docs/developments/api/websocket.zh-CN.md`。
- 参考项目：`D:\Coding\GitHub_Resuorse\emotion-robot\refer-projects\Open-LLM-VTuber`。

Open-LLM-VTuber 提供了“浏览器截图 + JPEG data URL + 多模态 LLM”的参考实现。本设计只借鉴其图片输入方式；ATRI 额外保留自身的 Memory、generation、VAD interrupt、TTS 和聊天归档边界。
