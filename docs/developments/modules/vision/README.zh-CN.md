---
status: active
owner: vision
created: 2026-07-11
updated: 2026-07-11
related_code:
  - config/vision_config.yaml
  - src/vision/
  - src/models/vision.py
  - src/routes/vision.py
  - src/routes/chat_ws.py
  - src/agent/chat_agent.py
  - src/llm/multimodal.py
  - frontend/src/stores/vision.ts
  - frontend/src/composables/useVision.ts
  - frontend/src/utils/visionSessionController.ts
  - frontend/src/utils/screenCapture.ts
---

# Vision 模块长期设计

Vision 模块为 ATRI 提供短生命周期的屏幕视觉输入。首版只支持从浏览器屏幕共享流中截取一张 JPEG，并把它与同一轮用户文本一起交给具备视觉能力的 LLM。

该模块不做 OCR、目标检测或持续视频分析。视觉理解由当前聊天模型完成，ATRI 只负责屏幕采集、传输、校验和调用边界。

## 模块边界

Vision 模块负责：

- 持久化视觉模块是否可用；
- 管理视觉配置的安全读取与白名单写入；
- 定义 `InputText`、`InputImage` 和 `InputInform`；
- 校验单张 JPEG 的信封、Base64、大小和基本文件签名；
- 协调 VAD 对话轮次与浏览器截图结果；
- 限制 WebSocket 文本帧大小。

浏览器前端负责：

- 由明确的用户点击调用 `getDisplayMedia()`；
- 持有当前标签页的 `MediaStream`；
- 每轮需要视觉输入时，从活动视频轨道截取一帧；
- 缩放、JPEG 编码并通过 WebSocket 发送短生命周期图片；
- 在浏览器原生停止共享后清理运行时状态。

LLM 模块负责：

- 把可选图片挂到最终的当前 `user` 消息；
- 按 Provider 协议序列化多模态消息；
- 把 SDK 失败映射为 `LLMError`。

Vision 模块不负责：

- 摄像头、文件上传、多图或图片预览；
- 判断当前模型是否真正支持视觉理解；
- 保存图片、生成图片摘要或把图片写入 Memory；
- 决定远端生成失败在前端如何展示。

## 双层开关

视觉功能有两个语义不同的控制面：

| 控制面 | 所有者 | 持久化 | 作用 |
| --- | --- | --- | --- |
| `vision.enabled` | 后端 `vision_config.yaml` | 是 | 决定 ATRI 是否允许视觉输入。 |
| 主页 `VisionInput` | 当前浏览器标签页 | 否 | 决定是否持有活动的屏幕共享 `MediaStream`。 |

有效视觉流必须同时满足：

```text
vision.enabled == true
AND
当前 WebSocket 连接报告 input:vision:state(enabled=true)
AND
浏览器视频轨道仍为 live
```

设置页开关不会创建 `MediaStream`。启用模块后，用户仍需回到聊天主页点击 VAD 麦克风右侧的视觉按钮，并在浏览器选择共享目标。

设置页禁用模块成功后，前端立即停止全部 tracks，并发送 `input:vision:state(enabled=false)`。若 PUT 失败，前端保留服务端最后确认的状态，也不会停止当前共享流。

## 配置

配置文件是 `config/vision_config.yaml`：

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `enabled` | `false` | 持久化模块开关。首版唯一可由前端写入的字段。 |
| `source` | `screen` | 首版固定为屏幕共享。 |
| `capture.media_type` | `image/jpeg` | 首版固定图片类型。 |
| `capture.jpeg_quality` | `0.82` | 浏览器 JPEG 编码质量。 |
| `capture.max_long_edge` | `1920` | 截图最长边上限。 |
| `capture.max_decoded_bytes` | `4194304` | 后端允许的解码后图片字节上限。 |
| `capture.timeout_ms` | `1500` | VAD 截图握手等待上限。 |
| `provider.detail` | `auto` | OpenAI 兼容 `image_url.detail`。 |
| `transport.websocket_max_message_bytes` | `8388608` | 应用层 WebSocket 文本帧 UTF-8 大小上限。 |

`GET /api/vision/config` 返回完整安全配置。`PUT /api/vision/config` 只接受一个严格布尔字段：

```json
{
  "enabled": true
}
```

PUT 在进程内串行执行。YAML 先写入同目录临时文件并原子 replace，只有落盘成功后才发布新的内存配置；写失败时前端、进程内状态和正式 YAML 都保留最后确认值。

缺少 `enabled`、类型不是布尔值或出现额外字段时，后端返回 `400`。

## 一轮输入的数据边界

后端使用三个领域对象表达一轮输入：

```text
InputInform
├── input_text: InputText
└── image: InputImage | None
```

`InputImage` 首版固定为：

```json
{
  "source": "screen",
  "media_type": "image/jpeg",
  "encoding": "base64",
  "data": "<opaque-base64>"
}
```

重要边界：

- `input_text.content` 进入长期记忆检索、历史上下文和成功轮次提交；
- `image` 只进入本轮 LLM 调用；
- 图片不会进入 ChatStorage、Memory archive、短期记忆、长期记忆或上下文压缩；
- 图片为可选字段。没有活动视觉流时，原有纯文本行为不变。

## 三种输入来源

### 键盘文本

`useChat.sendMessage()` 在发送前尝试从活动视频轨道截取一帧。成功时把 `text + image` 放进同一个 `input:text`；失败、超限或无活动流时，只发送文本一次。

### 普通单次 ASR

单次 ASR 的最终转写回填到 `InputBox`，随后复用 `useChat.sendMessage()`。因此它与键盘文本使用同一截图时机、同一 submission gate 和同一降级路径。

### VAD + 后端 ASR

VAD 的最终转写由后端直接启动聊天，前端不会补发 `input:text`。后端为该 generation 建立截图 Future，再发送：

```text
control:vision:capture-request
  -> 浏览器截取当前一帧
  -> input:vision:capture-result
  -> Future 按 generation_id 解析
  -> InputInform(text, image?)
```

截图等待在后台聊天任务中进行，不阻塞 WebSocket receive loop。这样同一连接仍能及时接收截图结果、VAD interrupt 和其他控制消息。

## 截图与传输

浏览器截图流程：

1. 从单例 controller 持有的隐藏 video 读取当前帧；
2. 按 `max_long_edge` 等比缩放；
3. 编码为 JPEG Blob；
4. 检查 Blob 大小；
5. 超限时最多再做一次有界缩放/压缩；
6. 在局部变量中转为 Base64；
7. 在发送边界计算完整 JSON 帧的 UTF-8 字节数；
8. 立即通过 JSON WebSocket 消息发送。

首版选择 Base64 + JSON，而不是二进制 WebSocket 帧。这样可复用现有消息信封和 generation 协议。代价是编码体积增加，因此同时存在解码后图片上限、JSON 信封余量和整帧 UTF-8 大小上限。有图 `input:text` 超限时移除图片并发送一次文本；VAD 回传超限时改发 `failed`。

## 后端校验顺序

`validate_input_image()` 按固定顺序校验：

1. payload 是对象；
2. `source == screen`；
3. `media_type == image/jpeg`；
4. `encoding == base64`；
5. `data` 是非空字符串；
6. Base64 编码长度未超过理论上限；
7. 严格 Base64 解码成功；
8. 解码字节未超过上限；
9. 具有基本 JPEG 起止签名。

失败结果只暴露短错误码与整数长度。领域对象和验证结果都避免在 `repr` 中显示图片数据。

## LLM 多模态边界

`ChatAgent` 先只用 `InputText` 调用 `MemoryManager.build_llm_context()`。随后它把 `InputImage | None` 作为独立关键字参数交给 `LLMInterface.chat_completion_stream()`。

`build_multimodal_messages()` 只复制并修改最后一条当前 `user` 消息：

```json
{
  "role": "user",
  "content": [
    { "type": "text", "text": "..." },
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

历史消息保持纯文本，调用方传入的列表也不会被原地修改。`OpenAICompatibleLLM`、`SiliconFlowLLM` 和 `XiaomiLLM` 当前都实现这一单图边界。

Provider 能序列化图片不等于具体模型具备视觉能力。模型以 HTTP 200 正常生成“无法查看图片”等自然语言时，仍属于成功回复；只有 SDK/Provider 调用失败才进入 generation failure。Provider 映射出的项目异常使用固定安全文本，不保留可能回显 data URL 的 SDK 原始字符串或 cause/context。

## 生命周期与失败

`visionSessionController` 是跨路由单例，持有：

- `MediaStream`；
- 当前视频轨道；
- 隐藏 video 元素；
- `starting / active / disabled / error` 运行时状态。

路由组件和 `VisionInput` 卸载不会停止 tracks。tracks 只在以下场景释放：

- 用户点击视觉按钮停止；
- 设置页成功禁用模块；
- 浏览器原生“停止共享”触发 track `ended`；
- 页面卸载或 controller 显式销毁；
- 授权请求返回时发现本次启动已被取消。

controller 只有在 video track 为 live 且隐藏 video 已提供非零 `videoWidth/videoHeight` 时才发布 `active`；否则释放资源并进入安全 error，避免显示“正在共享”但持续无法截图。

WebSocket 重连后，如果同一页面的共享流仍有效，前端重新发送 `input:vision:state(enabled=true)`。页面刷新不会恢复旧流。

失败语义：

- 本地无帧、Canvas 编码失败、图片超限或 VAD 截图 timeout：静默降级为纯文本；
- 无效图片信封：后端丢弃图片并继续文本；
- Provider 或 pre-success generation 失败：发送 `output:chat:error`，不提交失败轮次；
- VAD interrupt、complete 和 generation error 竞争：send lock 内首个终态获胜；LLM 流耗尽后先认领 `committing`，该阶段只允许 VAD 停音频，不允许重复 interrupted 归档；
- 迟到截图和未知 generation 结果直接丢弃。

## 安全护栏

图片 Base64、data URL 和原始字节不得进入：

- 后端日志或浏览器 console；
- Pinia、Vue Devtools 可观察状态；
- localStorage、IndexedDB、localforage；
- ChatStorage、Memory archive、短期/长期记忆；
- 测试快照、异常消息或完整请求参数输出。

允许观测的内容限于 source、MIME、encoded/decoded length、耗时、安全状态码、Provider/model 和 request ID。

## 相关文档

- [视觉理解 feature 设计](../../features/2026-07-10-visual-understanding/design-docs.md)
- [视觉理解实施计划](../../features/2026-07-10-visual-understanding/visual-implement.md)
- [WebSocket 协议](../../api/websocket.zh-CN.md)
- [WebSocket 事件字典](../../api/events.zh-CN.md)
- [LLM 调用层](../llm/call-layer.zh-CN.md)
- [Frontend 聊天运行时](../frontend/chat-voice-runtime.zh-CN.md)
