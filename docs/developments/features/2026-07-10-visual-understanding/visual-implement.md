---
status: planned
owner: vision
created: 2026-07-11
updated: 2026-07-11
design_document: ./design-docs.md
backend_branch: feat/visual-understanding
frontend_branch: feat/visual-understanding
related_code:
  - config.yaml
  - config/vision_config.yaml
  - src/vision/
  - src/agent/chat_agent.py
  - src/llm/interface.py
  - src/llm/providers/openai_compatible.py
  - src/llm/providers/siliconflow.py
  - src/llm/providers/xiaomi.py
  - src/routes/chat_ws.py
  - frontend/src/stores/chat.ts
  - frontend/src/composables/useChat.ts
  - frontend/src/composables/useWebSocket.ts
  - frontend/src/utils/websocketSessionController.ts
  - frontend/src/components/chat/InputBox.vue
  - frontend/src/components/chat/MessageList.vue
  - frontend/src/components/live2d/StageChatHistory.vue
---

# ATRI 屏幕视觉理解功能实施计划

## 1. 文档定位

本文把 [`design-docs.md`](./design-docs.md) 中已经确定的视觉理解方案拆成可编码、可测试、可提交和可验收的实施步骤。

设计文档负责回答“为什么这样设计”和“系统边界是什么”；本文负责回答：

1. 前后端分别修改哪些文件；
2. 各步骤按什么依赖顺序实施；
3. 每个步骤以什么测试和结果作为完成条件；
4. 前端子模块与后端主仓库如何分别提交；
5. 哪些事项尚未拍板，最迟应在哪一步之前决定。

本文不重新讨论摄像头、OCR、连续视频分析或图片持久化。若实现中必须改变已经确定的架构边界，应先更新设计文档，再继续修改代码。

### 1.1 当前基线

| 仓库 | 路径 | 开发分支 | 基线提交 |
|---|---|---|---|
| 后端主仓库 | `atri` | `feat/visual-understanding` | `ee5919b` |
| 前端子模块 | `atri/frontend` | `feat/visual-understanding` | `5fbc967` |

当前后端工作区可能存在用户尚未提交、且与某个实施 point 无关的修改。每次编辑和提交前都必须重新检查工作区；不得覆盖、暂存或提交不属于当前 point 的 `AGENTS.md`、配置文件或其他用户改动。

### 1.2 实施状态

视觉理解的核心范围、数据流、图片传输、Memory 边界、generation 竞争规则和失败语义已经确定，可以开始实现。

D1 至 D6 已全部确认并写入本文“已确认决策”一节。设置页与主页运行时按钮、Vitest、静默图片交互、SiliconFlow 验收模型、GET + PUT 配置 API，以及通用 pre-success generation failure 都是本次交付的确定范围，不再作为实施中的可选项。

## 2. 首版交付边界

### 2.1 必须交付

首版必须完成以下能力：

1. 用户通过明确操作开启或关闭屏幕共享流；
2. 键盘文字发送前，从当前共享流截取一张静态屏幕图；
3. 普通前端 ASR 的最终文本复用同一发送和截图链路；
4. 后端 VAD + ASR 得到最终文本后，请求浏览器截取一张静态屏幕图；
5. 截图成功时，`InputText` 与可选 `InputImage` 组成同一轮 `InputInform`；
6. Memory、聊天归档、上下文压缩和长期记忆仍然只处理文本；
7. Provider 只在调用边界多模态化最后一条当前 user 消息；
8. 本地截图失败时，本轮自动降级为一次纯文本请求；
9. 远端 LLM 调用失败时，本轮不归档、不写 Memory，只显示当前页面瞬态错误气泡；
10. VAD interrupt、generation complete 和 generation failed 遵守同一终态竞争规则；
11. 页面刷新或聊天历史重新加载后，失败轮次的用户文本与错误气泡消失；
12. Base64、data URL 和原始图片字节不进入日志、状态持久化或测试输出；
13. `/settings/modules/vision` 提供持久化模块开关，主页 VAD 按钮右侧提供当前标签页的 `VisionInput` 运行时按钮；
14. 后端提供 `GET /api/vision/config` 和只允许修改 `enabled` 的 `PUT /api/vision/config`；
15. 前端建立 Vitest 测试基础设施并覆盖视觉与 generation failure 核心状态机。

### 2.2 明确不交付

本轮不实现：

- 摄像头输入；
- 手动静态图片上传；
- 单轮多图；
- 同时附带屏幕和摄像头；
- 连续视频上传或后台持续截图；
- 无用户输入时的主动视觉观察；
- OCR、图片 embedding、图片摘要或图片记忆；
- 图片及图片元数据持久化；
- 二进制 WebSocket frame；
- Provider 视觉能力白名单或预探测；
- 多模态失败后的自动纯文本重试；
- `message_count=0` 空聊天清理；
- 前端瞬态错误的浏览器持久化。
- 本轮附带图片的预览、缩略图、附件徽标、聊天消息或元数据显示；
- 本地截图失败 toast 或其他用户提示。

### 2.3 实施不变量

任何步骤都不得破坏以下不变量：

```text
InputInform
     │
     ├── InputText ───────────> MemoryManager
     │                           ├── long-term retrieval
     │                           ├── history/context
     │                           └── final current user text
     │
     └── InputImage? ──────────────────┐
                                       ▼
                            provider invocation boundary
                            multimodalize only the final
                            current user message
```

- `InputText` 必填，`InputImage` 可选；
- 视觉流关闭或图片不可用时，现有纯文本调用形态不变；
- 图片只能在当前请求的短生命周期内存在；
- 失败轮次不能伪装为成功 AI 回复；
- HTTP 200 下模型自然生成“无法查看图片”仍属于成功回复；
- 同一 generation 的第一个有效终态获胜；
- 任何日志都不得通过异常对象或对象 `repr` 间接泄露 Base64。

## 3. 跨仓库实施与交付顺序

### 3.1 依赖关系

```text
后端
  Vision 配置/领域模型
          │
          ▼
  LLM 多模态调用边界
          │
          ▼
  ChatAgent InputInform / LLMError 传播
          │
          ▼
  WebSocket 视觉握手 / generation failure
          │
          ├──────────────────────────────┐
          ▼                              ▼
前端 Vision Runtime              前端 generation failure
          │                              │
          ├───────────┬──────────────────┘
          ▼           ▼
     输入框控制    默认/Stage 时间线渲染
          │
          ▼
       端到端验收
```

后端步骤 1 至 4 应先建立稳定协议和失败语义。前端步骤 5 至 7 再接入运行时、传输和 UI。前端可以在后端协议类型确定后并行开发，但最终联调必须使用同一版协议。

### 3.2 兼容与部署顺序

协议按以下方式保持向后兼容：

- `input:text.image` 是可选字段；
- `input:text.request_id` 是可选字段，只用于新前端关联 pre-generation rejection；
- 未发送 `input:vision:state` 的旧客户端默认处于视觉关闭状态；
- 视觉关闭时，后端继续使用原有字符串 user content；
- 新增 `output:chat:error`，同时保留顶层 `error` 处理通用协议错误；
- 旧前端不会发送图片，也不会触发 VAD 截图握手。

若前后端不能同时部署，应先部署后端，再部署前端。新前端不应长期运行在旧后端上，因为旧后端不存在视觉配置接口和 `output:chat:error` 语义。

### 3.3 子模块提交规则

1. 前端代码只在 `atri/frontend` 的 `feat/visual-understanding` 分支提交；
2. 后端代码和 feature 文档只在 `atri` 的同名分支提交；
3. 前端完成并通过检查后，先形成前端 commit；
4. 主仓库最后单独提交 frontend 子模块指针；
5. 不把前端文件误提交到主仓库普通文件列表；
6. 不在任何提交中包含现有 `config/tts_config.yaml` 修改；
7. 验收完成前不 push、不创建 PR；
8. 每个 point 单独 commit，commit scope 使用 `visual-understanding/step N`。

## 4. 最终数据与协议合同

本节是实施时的最小协议清单。完整设计依据仍以设计文档为准。

### 4.1 后端领域对象

建议在 `src/vision/models.py` 定义不可变运行时对象：

```python
@dataclass(frozen=True, slots=True)
class InputText:
    content: str


@dataclass(frozen=True, slots=True)
class InputImage:
    source: Literal["screen"]
    media_type: Literal["image/jpeg"]
    encoding: Literal["base64"]
    data: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class InputInform:
    input_text: InputText
    image: InputImage | None = None
```

约束：

- `InputText.content` 经过现有文本输入校验后必须非空；
- `InputImage.data` 不得出现在 `repr`、日志或异常消息中；
- 每轮最多一个 `InputImage`；
- `InputInform` 不包含 `chat_id`、`character_id` 或 `generation_id`；
- 路由执行信息继续属于 `ChatTurnContext`，不传给 LLM 作为图片元数据。

### 4.2 `input:text` 扩展

键盘输入和普通前端 ASR 使用：

```json
{
  "type": "input:text",
  "data": {
    "text": "请告诉我当前屏幕显示了什么",
    "chat_id": "chat_xxx",
    "character_id": "atri",
    "request_id": "request_xxx",
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

`image` 缺失、为 `null` 或校验失败时，合法 `text` 仍按纯文本发送一次。

### 4.3 视觉状态同步

开启共享：

```json
{
  "type": "input:vision:state",
  "data": {
    "enabled": true,
    "source": "screen"
  }
}
```

关闭共享：

```json
{
  "type": "input:vision:state",
  "data": {
    "enabled": false,
    "source": "screen"
  }
}
```

该状态只属于当前 WebSocket 连接。刷新页面、连接关闭或浏览器停止共享后，状态回到关闭。

### 4.4 VAD 截图握手

后端请求：

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

前端成功响应：

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

前端失败响应：

```json
{
  "type": "input:vision:capture-result",
  "data": {
    "generation_id": "gen_xxx",
    "status": "unavailable"
  }
}
```

`status` 只允许：

- `captured`：携带合法 `image`；
- `unavailable`：没有活动共享流、track 已结束或当前帧不可用；
- `failed`：截图、编码或本地校验发生其他失败。

`unavailable` 和 `failed` 都解析为 `image=None`，继续纯文本调用。

### 4.5 generation 失败事件

```json
{
  "type": "output:chat:error",
  "data": {
    "message": "本轮回复生成失败，请稍后重试。",
    "chat_id": "chat_xxx",
    "character_id": "atri",
    "generation_id": "gen_xxx"
  }
}
```

要求：

- `message` 使用安全、稳定的公共文案；
- 不把 Provider 原始异常传给前端；
- 事件必须携带完整 generation 关联字段；
- 发送与 generation 失效在同一个 send lock 临界区完成；
- 失败后中断后端 TTS，并由前端丢弃该 generation 的音频；
- 顶层 `error` 不再被当作 generation 终态。

### 4.6 图片校验顺序

后端必须按有界顺序校验，不能先无条件解码任意长度字符串：

1. 检查 WebSocket 文本帧总字节数；
2. 检查 `source`、`media_type` 和 `encoding` 白名单；
3. 检查 `data` 类型、非空和编码长度上限；
4. 使用严格 Base64 校验；
5. 检查解码后字节数不超过配置上限；
6. 检查 JPEG 基本签名；
7. 构造 `repr=False` 的 `InputImage`；
8. 立即释放仅用于校验的 decoded bytes。

图片失败不应把 Pydantic 或 Python 的原始校验异常直接写入日志。日志只记录安全状态码、长度整数和 generation 标识。

## 5. 分步实施计划

## Step 1：后端视觉领域、配置与校验

### 目标

建立视觉模块的领域对象、统一配置、图片安全校验和 VAD 截图协调器，为后续 Provider 与 WebSocket 接入提供稳定基础。

### 计划修改

新增：

- `config/vision_config.yaml`
- `src/vision/__init__.py`
- `src/vision/models.py`
- `src/vision/config.py`
- `src/vision/service.py`
- `src/vision/validation.py`
- `src/vision/capture_coordinator.py`
- `src/models/vision.py`
- `src/routes/vision.py`
- `tests/vision/test_models.py`
- `tests/vision/test_config.py`
- `tests/vision/test_validation.py`
- `tests/vision/test_capture_coordinator.py`
- `tests/routes/test_vision.py`

修改：

- `config.yaml`
- `src/app.py`
- `src/main.py`

### 实施要点

1. 在 `config.yaml` 增加：

   ```yaml
   vision_config: config/vision_config.yaml
   ```

2. `vision_config.yaml` 文件本身不再包一层 `vision:`。现有配置加载器会自动把 `vision_config` 映射为 `config["vision"]`。文件内容应为：

   ```yaml
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

3. 明确 `vision.enabled` 是模块可用开关，不是浏览器“当前正在共享”的持久化状态。即使配置为启用，页面加载后也必须等待用户手势才能调用 `getDisplayMedia()`。
4. `VisionConfigStore` 负责默认值、类型范围和 YAML 读取；`VisionService` 提供安全配置视图。
5. `GET /api/vision/config` 返回前端启动视觉模块所需的完整安全配置。
6. `PUT /api/vision/config` 幂等更新现有单例配置资源，首版请求体只允许 `{ "enabled": boolean }`。
7. 使用显式 allowlist `VISION_CONFIG_WRITE_FIELDS = {"enabled"}`；任何写入其他配置字段的请求返回 HTTP 400。
8. REST API 只管理后端 YAML。当前浏览器 MediaStream 和连接级视觉状态都不得通过 PUT 持久化。
9. `InputImage.data` 使用 `repr=False`。任何 Pydantic API 模型也不得在错误文本中展开 `data`。
10. `validate_input_image()` 接收原始映射并返回 `InputImage | None` 或受控校验结果，不把 Base64 写入异常文案。
11. 编码长度检查必须先于 `base64.b64decode(..., validate=True)`。
12. `VisionCaptureCoordinator` 以 `generation_id` 保存 pending Future，并提供：

    - `register(generation_id)`；
    - `resolve(generation_id, image_or_none)`；
    - `cancel(generation_id)`；
    - `cancel_all()`；
    - 重复、未知和迟到结果的安全丢弃。

13. Future 必须先注册，再发送 capture request。
14. `src/main.py` 从视觉配置读取 `websocket_max_message_bytes` 并传给 Uvicorn 的 `ws_max_size`；路由仍保留应用层帧大小检查。
15. `src/app.py` 初始化视觉配置服务并注册 `vision_router`。

### 测试

- 默认配置加载正确；
- `vision_config.yaml` 不产生 `config["vision"]["vision"]` 双层结构；
- 非法 quality、尺寸、timeout、detail 和帧大小被拒绝；
- `InputImage` 和 `InputInform` 的 `repr` 不含 Base64；
- 合法小型合成 JPEG fixture 通过；
- 非法 MIME、source、encoding、padding、JPEG 签名和超限数据降级；
- 校验异常、pytest diff 和日志捕获中不出现完整 Base64；
- coordinator 正常 resolve；
- coordinator timeout/cancel/disconnect 后清理；
- 重复、未知和迟到 generation 不改变其他 Future；
- REST 配置返回不含运行时 MediaStream 状态。
- GET 返回完整安全配置；PUT 可以幂等切换 `enabled` 并持久化到 YAML；
- PUT 尝试修改 `source`、`capture`、`provider` 或 `transport` 时返回 HTTP 400；
- PUT 不接受或持久化当前浏览器共享状态。

### 完成条件

- 后端能够安全构造或拒绝 `InputImage`；
- 配置只从一个来源读取；
- coordinator 无 pending Future 泄漏；
- 不接入图片时，现有应用启动和纯文本测试不受影响。

## Step 2：LLM 多模态 Provider 调用边界

### 目标

让 LLM 接口可选接收一张图片，并由 Provider 在不修改 Memory 消息的前提下构造 OpenAI 兼容多模态请求。

### 计划修改

新增：

- `src/llm/multimodal.py`

修改：

- `src/llm/interface.py`
- `src/llm/factory.py`
- `src/llm/providers/openai_compatible.py`
- `src/llm/providers/siliconflow.py`
- `src/llm/providers/xiaomi.py`
- `src/service_context.py`
- `tests/llm/providers/test_openai_compatible.py`
- `tests/llm/providers/test_siliconflow.py`
- `tests/llm/providers/test_xiaomi.py`
- 对应 LLM interface/factory 测试

### 实施要点

1. 为 `LLMInterface.chat_completion_stream()` 增加仅关键字参数：

   ```python
   *,
   input_image: InputImage | None = None
   ```

2. `image=None` 时保持原有 messages 和字符串 `content` 形态，不做不必要的复制或重写。
3. 有图时复制 messages 列表、最后一条当前 user 消息及其 content；不得原地修改 Memory 返回对象。
4. 只把最后一条当前 user 消息转换为：

   ```json
   [
     {
       "type": "text",
       "text": "<current user text>"
     },
     {
       "type": "image_url",
       "image_url": {
         "url": "data:image/jpeg;base64,<opaque-base64>",
         "detail": "auto"
       }
     }
   ]
   ```

5. system、历史 user、历史 assistant、工具消息和 Memory block 保持原样。
6. OpenAI-compatible 与 Xiaomi Provider 复用同一个纯函数序列化器；
   SiliconFlow 通过独立 `SiliconFlowLLM` 继承通用序列化能力，并保留覆盖入口。
7. `vision.provider.detail` 不能散落为硬编码。建议实施方式：

   - Provider 构造器接收经过验证的 `image_detail`；
   - `create_from_role()` 支持内部运行时 provider override；
   - `ServiceContext` 只在创建 chat role Provider 时传入 `vision.provider.detail`；
   - 标题生成、L3/L4 压缩等其他 role 不接收图片，保持原状。

8. Provider SDK 异常继续映射到现有 `LLMError` 家族，不新增 `LLMRequestError`。
9. Provider 错误日志只记录异常类型、Provider、模型、安全状态码或 request ID，不记录原始 `str(exc)`、messages 或 request params。

### 测试

- 纯文本调用参数与修改前一致；
- 有图时仅最后一条 user 消息变为多模态列表；
- 原始 messages 深层结构未被修改；
- data URL 只在 Provider 调用参数中临时生成；
- `detail` 来自配置；
- OpenAI-compatible、SiliconFlow 和 Xiaomi 使用一致结构；
- system/tools 参数保持兼容；
- 标题生成和 Memory LLM 调用不传图片；
- SDK 失败抛出现有 `LLMError`；
- 测试只比较字段、长度或摘要，不输出完整 data URL。

### 完成条件

- 两个目标 Provider 都能生成正确的单图请求；
- 纯文本请求无协议回归；
- Memory 消息在调用前后完全不含图片结构；
- 错误路径不泄露请求体。

## Step 3：ChatAgent 接入 InputInform 并修复 LLM 失败语义

### 目标

让 ChatAgent 明确区分文本和可选图片，并停止把 `LLMError` 转换为“合法 AI 文本”。

### 计划修改

- `src/agent/chat_agent.py`
- `src/routes/chat_ws.py` 中最小的调用适配
- `tests/agent/test_chat_agent.py`
- `tests/agent/test_live_chat_agent.py` 的调用兼容或 helper
- 受接口变更影响的 route mock

### 实施要点

1. WebSocket 新路径构造 `InputInform`，ChatAgent 内部统一规范化输入。
2. 为保留现有内部调用和 live test 的可读性，可提供 `InputInform.text_only()` 或受控的字符串兼容入口；视觉路径必须显式传 `InputInform`。
3. `MemoryManager.build_llm_context()` 只接收 `input_inform.input_text.content`。
4. `runtime_context` 继续按现有方式加入最终当前 user 文本。
5. `llm.chat_completion_stream()` 单独接收 `input_inform.image`。
6. `commit_round=True` 时，`on_round_complete()` 仍只接收文本 user/AI 消息。
7. 删除以下错误路径：

   ```text
   LLMError
     -> yield "[LLM call failed: ...]"
     -> append_system_note(...)
     -> return
   ```

8. `LLMError` 必须原样向路由编排层传播。
9. 不删除 `append_system_note()` 本身，因为其他明确的系统记录用途可能仍依赖它；只删除 LLM 失败路径的调用。
10. 修正 ChatAgent 中描述旧 sentinel 行为的双语 docstring 和模块说明。
11. 短回复观察日志仍可保留，但不得扩展为打印包含图片的 InputInform。

### 测试

- 文本只用于 Memory 检索和 round commit；
- 图片只到达 LLM mock；
- `image=None` 保持旧行为；
- `LLMError` 从 async generator 传播；
- 失败时不 yield sentinel；
- 失败时不调用 `append_system_note()`；
- 失败时不调用 `on_round_complete()`；
- 成功时仍只提交一次 round；
- `chat_collect()` 的成功、失败和 `commit_round=False` 行为一致。

### 完成条件

- ChatAgent 不再生产伪 AI 错误消息；
- 成功路径和纯文本路径回归测试通过；
- 图片未进入 MemoryManager 的任何方法参数。

## Step 4：后端 WebSocket 视觉协议与 generation failure

### 目标

把键盘、普通 ASR 和 VAD + ASR 汇入共享聊天执行链路，完成图片解析、VAD 截图握手、终态竞争和无持久化失败处理。

### 计划修改

- `src/routes/chat_ws.py`
- `src/vision/capture_coordinator.py`
- `tests/routes/test_chat_ws.py`
- 必要的 WebSocket 测试 helper/fixture

### 实施要点

#### A. 连接级视觉状态

1. 每条 WebSocket 连接维护轻量视觉状态：

   - `enabled`；
   - `source=screen`；
   - 一个 `VisionCaptureCoordinator`。

2. 未收到视觉状态时默认为关闭。
3. 收到 `enabled=false`、连接关闭或 cleanup 时，取消该连接全部 pending capture。
4. 后端不能证明图片真实来自屏幕，但必须拒绝协议中非 `screen` 的 source。

#### B. 键盘与普通 ASR

1. `input:text` 先完成原有 text/chat/character 校验。
2. 只有连接视觉状态为 active 时才解析可选 `image`。
3. 图片缺失或校验失败时设置 `image=None`，文本只发送一次。
4. 路由构造 `InputInform` 后进入共享 chat execution。
5. 图片校验 warning 只记录 code、长度和 generation，不记录 payload。

#### C. VAD + ASR

必须使用以下顺序：

```text
speech_end
  -> backend ASR final transcript
  -> allocate generation_id
  -> output:asr:transcript
  -> start tracked background generation task
       -> if vision inactive: image=None
       -> if vision active:
            register Future first
            send control:vision:capture-request
            await Future with configured timeout
       -> image or text-only fallback
       -> shared chat execution
```

严禁在 WebSocket receive loop 内直接等待截图 Future。否则接收循环无法处理浏览器返回的 `input:vision:capture-result`。

#### D. capture result 分发

1. receive loop 只负责解析和 resolve coordinator；
2. `captured` 结果通过后端独立校验后 resolve `InputImage`；
3. `unavailable`、`failed` 和本地校验失败 resolve `None`；
4. 未知、重复或已经取消的 generation 直接丢弃；
5. stale result 不产生顶层错误，也不能影响当前 generation；
6. timeout、VAD interrupt、task cancellation 和 disconnect 都清理 Future。

#### E. generation 终态

为 complete、interrupted、failed 统一执行“首个终态获胜”：

```text
acquire send_lock
  -> verify generation is active
  -> commit one terminal event/state
  -> invalidate generation in the same critical section
release send_lock
  -> perform terminal-specific cleanup
```

新增 generation-aware failure sender：

```text
acquire send_lock
  -> active?
       no: return ignored
       yes:
         send output:chat:error
         invalidate generation
release send_lock
  -> interrupt backend TTS generation
```

现有 `output:chat:complete` 的发送与 generation 失效也应收敛到同一临界区，避免 send 后、invalidate 前被 interrupt 抢占。

#### F. pre-success generation failure 与持久化

LLM stream 正常耗尽后，必须先在 send lock 内把 active generation 原子标记为 `committing`，再开始 ChatStorage 与 Memory 写入。`committing` 已经认领 durable success：VAD speech_start 仍中断音频，但不得取消该聊天任务或重复持久化 interrupted round；`control:interrupt` 使用 `preserve_chat_generation=true` 让前端保留流式状态，随后由正常 complete 收口。ChatStorage 与 Memory 均为 best effort，`output:chat:complete` 只确认 generation 成功结束，不是二者均成功落盘的事务 ACK。

若新一轮 `speech_end` 到达时旧 generation 仍在 `committing`，后端最多等待 5 秒。上限内完成则继续 ASR；超时则发送 `control:listen-state` 的 `chat_commit_busy` 错误，不取消旧 commit task、不调用 ASR、不创建新 generation，并立即返回 WebSocket receive loop。该语音段由用户在旧 generation 收口后重试，不能用无限等待占住唯一消息接收循环。

所有发生在 durable success effects 开始之前、导致本 generation 无法完成的终态错误都走同一个 generation failure 分支，包括 `LLMError`、Provider 流式失败，以及成功持久化前不可恢复的 generation 编排失败。统一行为为：

- 丢弃已累积的 partial reply；
- 停止并丢弃该 generation 的 TTS；
- 不写 ChatStorage；
- 不调用 `on_round_complete()`；
- 不更新 recent messages、round count、压缩或长期记忆；
- 不调用 `append_system_note()`；
- 只尝试发送一次 `output:chat:error`；
- 若 generation 已被 VAD interrupt，迟到的错误直接丢弃。

本分支严格排除：

- 本地截图、编码、图片校验和等待超时；
- JSON/协议校验错误；
- TTS 单段失败；
- 成功持久化或其他 durable success effects 已经开始后的辅助错误。

这些错误继续使用各自既有的静默降级、顶层 `error`、`output:audio:error` 或成功后辅助错误路径。

Provider 返回 HTTP 200 且正常生成自然语言拒绝时，仍走 success 路径。

#### G. 通用协议错误

顶层 `error` 只处理：

- JSON 无效；
- 缺少 type；
- 未知 message type；
- 缺少必填协议字段；
- 与 generation 调用无关的连接级错误。

新前端为每个 `input:text` 附带短生命周期 `request_id`。后端在明确拒绝该输入时通过顶层 `error` 原样返回；前端只清理 `chatId + characterId + requestId` 匹配且仍为 pending 的 submission。已经 streaming 的 generation 和不相关顶层错误不得被该路径终止。

它不得无条件清理前端 active generation。前端事件映射必须与 `output:chat:error` 分开。

#### H. 安全日志

需要替换或约束会打印原始异常的路径，尤其是：

- tracked chat task done callback；
- `LLMError` catch；
- unexpected generation failure catch；
- WebSocket 总异常 handler；
- Provider request failure。

允许记录 `type(exc).__name__` 和安全字段；禁止直接格式化可能回显请求体的 `exc`。

### 测试

至少覆盖：

1. 视觉关闭的纯文本输入；
2. `input:text` 携带合法图片；
3. 非法图片降级且文本只调用一次；
4. 未同步视觉 active 时忽略图片；
5. VAD 视觉关闭直接聊天；
6. VAD 请求前已经注册 Future；
7. receive loop 在截图等待期间仍可接收 capture result；
8. captured/unavailable/failed 三种结果；
9. timeout 后纯文本继续；
10. duplicate/stale/unknown result 被丢弃；
11. disconnect 和 task cancellation 清空 coordinator；
12. `LLMError`、Provider 流失败和不可恢复编排失败都不写 ChatStorage；
13. pre-success generation failure 不写 Memory 或压缩；
14. pre-success generation failure 清理 partial reply 和 TTS；
15. interrupt 先获锁时，迟到 Error 被丢弃；
16. Error 先获锁时，后续 generation 不受影响；
17. generation B active 时，Error(A) 不影响 B；
18. complete/interrupted/failed 只有一个终态；
19. 通用顶层 `error` 不终止无关 generation；
20. 本地图片、协议、TTS 单段和 durable success 后错误不误用 `output:chat:error`；
21. 日志捕获中不含 Base64、data URL 或原始 Provider 请求。

### 完成条件

- 三种 InputText 来源都能进入同一 `InputInform -> ChatAgent` 链路；
- VAD 截图等待不阻塞 receive loop；
- 失败轮次无任何成功持久化副作用；
- generation 竞态测试稳定通过。

## Step 5：前端视觉运行时、截图与传输

### 目标

在浏览器安全持有屏幕共享流，按轮截取、缩放和编码一帧，并接入键盘、普通 ASR 与 VAD 协议。

### 计划新增

- `frontend/src/types/vision.ts`
- `frontend/src/api/vision.ts`
- `frontend/src/stores/vision.ts`
- `frontend/src/composables/useVision.ts`
- `frontend/src/utils/visionSessionController.ts`
- `frontend/src/utils/screenCapture.ts`
- `frontend/vitest.config.ts`
- 与 vision store、controller、screen capture 和 submission gate 对齐的 `*.spec.ts` 文件

### 计划修改

- `frontend/src/api/types.ts`
- `frontend/src/types/websocket.ts`
- `frontend/src/utils/websocketSessionController.ts`
- `frontend/src/composables/useWebSocket.ts`
- `frontend/src/composables/useChat.ts`
- `frontend/src/stores/chat.ts` 的 submission gate
- `frontend/src/components/chat/InputBox.vue` 的接线
- `frontend/package.json`
- `frontend/package-lock.json`

### 实施要点

#### A. 运行时所有权

1. `visionSessionController` 或等价单例持有 `MediaStream`、video element 和 track listeners。
2. Pinia 只保存：

   - 模块是否可用；
   - `disabled / starting / active / error` 状态；
   - 安全错误文案；
   - 截图配置投影。

3. Pinia 不保存：

   - MediaStream；
   - Canvas；
   - Blob；
   - ArrayBuffer；
   - Base64；
   - data URL。

4. 用户点击后才调用：

   ```ts
   navigator.mediaDevices.getDisplayMedia({
     video: true,
     audio: false
   })
   ```

5. 只有用户显式关闭、设置页禁用模块、浏览器原生“停止共享”导致 track `ended`、页面卸载或 controller 显式销毁时，才停止全部 tracks。
6. `vision.vue`、`VisionInput.vue`、`InputBox.vue` 等组件卸载和设置页到主页的路由切换不得停止 tracks；MediaStream 必须由跨路由单例持有。
7. Chrome/Edge 原生共享指示器及“停止共享”按钮不能由 ATRI 定制。controller 监听 `MediaStreamTrack.ended`，清理运行时并发送 `input:vision:state(enabled=false)`；后端 YAML 的 `enabled` 保持不变。
8. 刷新页面后不得自动恢复共享。
9. WebSocket 重连后，如果同一页面中的共享流仍 active，应重新发送 `input:vision:state(enabled=true)`。

#### B. 截图

每次调用 `captureCurrentFrame()`：

```text
assert active live video track
  -> read video dimensions
  -> scale longest edge to configured maximum
  -> draw into temporary Canvas
  -> canvas.toBlob(image/jpeg, jpeg_quality)
  -> check Blob bytes
  -> optionally perform one bounded smaller retry
  -> convert to Base64
  -> construct InputImage
  -> return directly to caller
  -> release local references
```

要求：

- 最多一次有界二次压缩，不写无限重试；
- 超限后返回不可用结果；
- 不把完整 data URL 留在状态中；
- 如果浏览器转换 API 返回 `null`，按本地截图失败处理；
- 不在 console 打印 capture result。

#### C. submission gate

截图发生在最终文本已确定、chat 已确保存在、WebSocket 真正发送之前。

`connectionBusy` 当前只覆盖 active generation，无法覆盖“正在截图但尚未发送”。需增加轻量 submission gate：

```text
idle
  -> reserving/submitting
  -> capture or fallback
  -> beginStreaming
  -> send input:text
  -> release submission gate
```

同一 gate 必须阻止按钮、Enter 和自动 ASR 在截图等待期间重复提交。它不能存储图片。

#### D. 键盘与普通 ASR

1. `useChat.sendMessage()` 完成 chat ensure/create；
2. 视觉 active 时调用一次截图；
3. 截图成功，把 `image` 作为 `sendText()` 的可选字段；
4. 截图失败，`sendText()` 只发送 text；
5. 普通 ASR 已把最终 transcript 写入 InputBox，因此继续复用 `sendMessage()`，不新增第二条聊天实现。

本地截图、编码、校验或等待失败必须完全静默：不显示 toast、`ChatErrorBubble` 或图片状态消息。首版也不显示截图预览、缩略图、附件徽标或图片元数据。

#### E. VAD capture request

1. `websocketSessionController` 把 `control:vision:capture-request` 分发为独立事件；
2. handler 异步调用 `captureCurrentFrame()`；
3. 成功发送 `captured + image`；
4. 无 active stream 发送 `unavailable`；
5. 其他安全失败发送 `failed`；
6. 响应原样带回请求的 `generation_id`；
7. 截图结束前发生 VAD interrupt 时可以仍发送迟到结果，后端负责 generation 丢弃；前端不得因此修改新 generation。

### 测试与检查

本 feature 必须建立 Vitest 基础设施，并至少增加：

- screen capture 纯函数的尺寸计算测试；
- 单次有界重压缩测试；
- vision store 生命周期测试；
- `visionSessionController` 启停、track `ended`、路由组件卸载不销毁测试；
- submission gate 防重复测试；
- capture request/result generation 关联测试；
- Base64 不进入 store 的断言。

必须通过：

```bash
npm run test
npm run type-check
npm run lint
npm run build
```

并手工验证 Chrome/Edge 的授权、取消授权、停止共享和 track ended。

### 完成条件

- 用户手势可以稳定开启和关闭共享；
- 键盘与普通 ASR 每轮最多附带一张图；
- VAD 请求可得到 generation 对应结果；
- 本地失败只降级，不重复发送文本；
- Pinia、console 和浏览器持久化中无 Base64。

## Step 6：前端 generation failure 状态机与错误气泡

### 目标

把 generation 失败建模为瞬态时间线 notice，而不是 AI Message，并在默认聊天与 Stage 模式中以消息气泡形式显示。

### 强制设计流程

实际开始开发 `ChatErrorBubble` 时，必须调用：

- `design-taste-frontend`；
- `ui-ux-pro-max`。

这两个 skill 用于该组件的视觉层级、主题适配、可访问性和 default/stage 变体设计。它们不要求在编写本文或实施其他非 UI 步骤时提前调用。

### 计划新增

- `frontend/src/components/chat/ChatErrorBubble.vue`
- `frontend/src/components/chat/ChatTimelineItem.vue` 或等价共享 dispatcher

### 计划修改

- `frontend/src/types/message.ts`
- `frontend/src/types/websocket.ts`
- `frontend/src/stores/chat.ts`
- `frontend/src/composables/useChat.ts`
- `frontend/src/composables/useWebSocket.ts`
- `frontend/src/utils/websocketSessionController.ts`
- `frontend/src/components/chat/MessageList.vue`
- `frontend/src/components/live2d/StageChatHistory.vue`

### 实施要点

#### A. 时间线类型

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

建议把 Pinia 主渲染状态迁移为 `timelineItems`，并为只消费正常消息的旧逻辑提供过滤 getter。历史 REST 响应只转换为 `kind=message`。

#### B. 通用 store action

使用通用动作：

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

不要使用 `failActiveGenerationWithErrorBubble` 等 UI 耦合名称。

action 必须：

1. 严格匹配 active stream 的 chat、character 和 generation；
2. 保留当前已有的“首个完整 generation 事件可绑定未绑定 stream”规则；
3. 永远不匹配 `pendingInterruptedStream`；
4. stale generation 返回 `ignored`；
5. 匹配后清空 `activeStream` 与 `streamingText`；
6. 当前聊天可见时追加 `ChatNoticeItem` 并返回 `visible`；
7. 当前聊天不可见时不追加 notice，返回 `hidden`；
8. 不控制音频、TTS、Live2D 或 WebSocket 全局错误状态。

#### C. WebSocket handler

`output:chat:error` handler 只执行：

```text
result = chatStore.failActiveGeneration(...)
  -> ignored: no-op
  -> visible/hidden: discardGenerationAudio(generation_id)
```

不得调用：

- `enqueueAutoSpeech()`；
- Live2D expression 请求；
- `wsStore.setError()`；
- 普通 AI complete handler。

顶层 `error` 继续进入通用协议/连接错误路径，不调用 `failActiveGeneration()`。

#### D. 渲染

`MessageList` 与 `StageChatHistory` 共用：

```text
ChatTimelineItem
  ├── kind=message -> MessageItem
  └── kind=notice  -> ChatErrorBubble
```

`ChatErrorBubble` 必须：

- 使用消息气泡布局；
- 与 AI 消息有明确但不过度突兀的区别；
- 不显示角色头像；
- 不显示 TTS 按钮；
- 不触发 Live2D；
- 支持 default 和 stage 变体；
- 支持亮色和暗色主题；
- 使用可访问的错误语义；
- 不抢夺键盘焦点；
- 不写入任何浏览器持久化。

#### E. 历史重建

`loadHistory(chat_id)` 用后端归档消息整体替换前端时间线，因此：

- 当前页失败用户文本与错误气泡会消失；
- 刷新页面后两者会消失；
- 切换聊天并重新加载后两者会消失；
- 成功历史不受影响。

### 测试与检查

Vitest 必须覆盖：

- generation 严格匹配；
- 首事件绑定；
- `pendingInterruptedStream` 不被错误匹配；
- stale Error(A) 不影响 generation B；
- visible/hidden/ignored 三种返回值；
- failure 清空 partial streaming text；
- notice 不进入历史重建结果；
- output error 不触发 TTS/Live2D；
- 顶层 protocol error 不终止 active stream。

视觉检查至少覆盖：

- 默认聊天宽屏和窄屏；
- Stage 模式；
- 明暗主题；
- 长错误文案换行；
- 键盘导航和屏幕阅读语义。

### 完成条件

- 失败信息以独立错误气泡显示；
- 它不是 AI 消息，也不触发任何 AI 消费链；
- generation race 不误伤新回复；
- 刷新或历史重载后瞬态内容消失。

## Step 7：视觉设置页与主页运行时控制

### 目标

完成已经确认的双层控制：设置页持久化视觉模块是否可用，主页按钮控制当前浏览器标签页是否建立 MediaStream。两者语义、所有权和生命周期必须明确分离。

### 强制设计流程

实际开始开发设置页与 `VisionInput` 时，必须调用：

- `design-taste-frontend`；
- `ui-ux-pro-max`。

这两个 skill 用于贴合现有设置页、按钮工具栏、明暗主题和可访问性。编写本文以及实施非 UI 步骤时不提前调用。

### A. 设置页持久化模块开关

新增和修改：

- `frontend/src/pages/settings/modules/vision.vue`；
- `frontend/src/router/index.ts`，把 `/settings/modules/vision` placeholder 替换为真实页面；
- 设置导航保持“设置 -> 机体模块 -> 视觉功能”。

页面首版只有一个开关：是否启用视觉模块。页面加载时调用 `GET /api/vision/config`，切换时调用 `PUT /api/vision/config`，且 PUT 只提交：

```json
{
  "enabled": true
}
```

该开关写入 `vision_config.yaml` 的顶层 `enabled` 字段，不创建 MediaStream，也不把浏览器当前共享状态写回 YAML。页面不展示可编辑的截图参数，不提供摄像头、文件上传、多图或其他未来能力占位开关。

如果用户在 MediaStream active 时关闭模块：

```text
PUT enabled=false succeeds
  -> visionSessionController stops all tracks
  -> send input:vision:state(enabled=false)
  -> disable home VisionInput
```

只有 PUT 成功后才提交本地模块禁用状态；请求失败时保留服务器确认过的状态，并显示设置页既有风格的安全操作失败反馈。

### B. 主页 `VisionInput` 运行时按钮

新增：

- `frontend/src/components/chat/VisionInput.vue`。

修改 `frontend/src/components/chat/InputBox.vue`，让输入工具栏顺序明确为：

```vue
<VoiceInput />
<RealtimeVoiceInput />
<VisionInput />
```

`VisionInput` 在默认聊天和 Live2D Stage 模式都必须显示，并位于对应 VAD 麦克风按钮右侧。`InputBox` 和 `VisionInput` 只负责 UI 与调用单例 controller，不持有 MediaStream。

状态优先级：

```text
backend vision.enabled=false
  -> VisionInput disabled

backend vision.enabled=true + no active MediaStream
  -> VisionInput available and inactive

backend vision.enabled=true + active MediaStream
  -> VisionInput active
```

用户点击开启时调用 `navigator.mediaDevices.getDisplayMedia()` 并由浏览器显示共享目标选择器；成功后同步 `input:vision:state(enabled=true)`。用户点击关闭时停止全部 tracks 并同步 `input:vision:state(enabled=false)`。

按钮至少表现以下状态：

- 模块不可用；
- 可用但未共享；
- 正在请求浏览器权限；
- 正在共享；
- 用户拒绝；
- 浏览器终止共享；
- 当前浏览器不支持 `getDisplayMedia()`。

Chrome/Edge 的“停止共享”按钮属于浏览器原生界面，ATRI 不能定制。监听 video track `ended` 后只清理运行时并发送连接状态关闭；YAML 中的模块开关保持开启，因此主页按钮仍可重新启动共享。

要求：

- 开启必须来自用户点击；
- 活动状态清晰可见；
- 路由切换和相关 Vue 组件卸载不停止有效 tracks；
- 页面刷新后按钮回到未共享；
- 不显示截图预览、缩略图、附件徽标或本轮图片元数据；
- 不显示本地截图失败 toast 或 `ChatErrorBubble`；
- 不暗示摄像头已经支持。

### 完成条件

- 设置开关只持久化 `enabled`，并能在关闭时终止现有运行时；
- 模块开关关闭时主页按钮不可用，开启时主页按钮可用但不会自动共享；
- 默认聊天和 Stage 均在 VAD 右侧显示独立 `VisionInput`；
- 用户能理解当前是否正在共享；
- 权限拒绝、浏览器停止共享和路由切换后的状态正确；
- 运行时状态、连接状态与持久化配置没有混淆；
- UI 未暴露首版非目标。

## Step 8：集成、文档与验收

### 目标

完成前后端联合验证、安全审计、长期文档同步和 PR 前检查。

### 后端检查

每个后端 point 完成后运行目标测试。feature 收尾时运行：

```bash
uv run python -m mypy src/ --ignore-missing-imports
uv run ruff format .
uv run ruff check . --fix
uv run pytest tests/ -v
```

先运行视觉、LLM、Agent、WebSocket 定向测试，再运行完整测试，便于快速定位回归。

### 前端检查

在 `frontend` 中运行：

```bash
npm run test
npm run type-check
npm run lint
npm run build
```

`npm run test` 使用本 feature 新增的 Vitest 配置。它必须在 type-check、lint 和 build 之外独立通过；真实浏览器的 `getDisplayMedia()` 行为继续按手工验收项检查。

### 真实 Provider 验证

从 `.env` 读取现有凭据，继续使用当前 `provider: siliconflow`。`deepseek-ai/DeepSeek-V4-Flash` 不支持视觉理解；真实视觉验收时，只临时把 chat role 模型改为：

```yaml
model: Pro/moonshotai/Kimi-K2.6
```

不得修改 provider、base URL、API key、`compress_light` 或 `title_gen`。该模型切换是本地验收 override，验收后恢复用户原配置，除非用户另行要求，否则不得把它作为默认配置提交。

验证时只记录：

- Provider/model 名称；
- 请求是否成功；
- 图片 encoded/decoded length；
- 延迟；
- 安全状态码或 request ID。

不得打印图片 Base64、data URL、完整 messages、完整 request params 或真实屏幕内容。

### 长期文档同步

实现与测试稳定后，更新：

- `docs/developments/modules/agent/chat-agent.zh-CN.md`
- `docs/developments/modules/llm/call-layer.zh-CN.md`
- `docs/developments/modules/memory/context-assembly.zh-CN.md`
- `docs/developments/modules/frontend/state-management.zh-CN.md`
- `docs/developments/modules/frontend/chat-voice-runtime.zh-CN.md`
- `docs/developments/modules/routes/design.zh-CN.md`
- `docs/developments/api/websocket.zh-CN.md`
- `docs/developments/api/events.zh-CN.md`
- 本 feature 的开发日志与验收记录

README 开发路线只在功能验收完成后更新状态。

### 综合审查硬化项

综合审查必须使用可控 Event/Future 覆盖 durable persistence 窗口，而不只检查 sender 函数。合并前还需验证：

1. `committing` 期间的 VAD interrupt 不重复写 human/AI 或 Memory；
2. 完整图片 JSON 帧超限时，键盘/普通 ASR 降级为一次文本，VAD 回传 `failed`；
3. 顶层 input rejection 只通过 `request_id` 清理匹配的 pending submission；
4. Vision PUT 写失败不发布内存值，并发 PUT 不同时写 YAML；
5. Provider 映射异常不保留可能含 data URL 的 SDK 原始文本；
6. controller 只有在共享视频帧尺寸有效时进入 active。
7. `committing` handoff 超时后旧 task 不被取消，本次 speech-end 不调用 ASR，receive loop 能继续处理消息。

### PR 前

1. 检查后端和前端工作区；
2. 确认无 Base64、data URL 或真实截图进入 git；
3. 确认 `config/tts_config.yaml` 未进入本 feature commit；
4. 检查前端子模块指针只指向已提交的前端 commit；
5. 按项目要求执行综合代码审查；
6. 修复阻塞问题并重跑对应检查；
7. 验收通过后再 push 两个仓库并创建 PR。

## 6. 文件级变更矩阵

### 6.1 后端主仓库

| 文件/目录 | 变更 | 责任 |
|---|---|---|
| `config.yaml` | 修改 | 引用视觉子配置 |
| `config/vision_config.yaml` | 新增 | 视觉能力、截图、Provider 与传输限制 |
| `src/vision/models.py` | 新增 | `InputText`、`InputImage`、`InputInform` |
| `src/vision/config.py` | 新增 | 默认值、加载、校验和 `enabled` 持久化 |
| `src/vision/service.py` | 新增 | 配置服务与安全投影 |
| `src/vision/validation.py` | 新增 | 图片 envelope/Base64/JPEG/尺寸校验 |
| `src/vision/capture_coordinator.py` | 新增 | generation-keyed pending Future |
| `src/models/vision.py` | 新增 | REST 配置响应/更新模型 |
| `src/routes/vision.py` | 新增 | `GET + PUT /api/vision/config`，PUT 只写 `enabled` |
| `src/app.py` | 修改 | 初始化视觉服务、注册路由 |
| `src/main.py` | 修改 | 应用 WebSocket message size |
| `src/llm/interface.py` | 修改 | 可选 `input_image` 参数 |
| `src/llm/multimodal.py` | 新增 | 无副作用的 Provider 序列化 helper |
| `src/llm/factory.py` | 修改 | chat Provider 的 image detail override |
| `src/llm/providers/openai_compatible.py` | 修改 | OpenAI 兼容单图请求 |
| `src/llm/providers/siliconflow.py` | 修改 | SiliconFlow 单图请求与专用扩展边界 |
| `src/llm/providers/xiaomi.py` | 修改 | Xiaomi 单图请求 |
| `src/service_context.py` | 修改 | 把视觉 Provider 配置注入 chat role |
| `src/agent/chat_agent.py` | 修改 | InputInform、文本 Memory 边界、异常传播 |
| `src/routes/chat_ws.py` | 修改 | 协议、截图协调、终态与失败编排 |
| `tests/vision/` | 新增 | 视觉领域、校验、配置和 coordinator 测试 |
| `tests/llm/providers/` | 修改 | 多模态 Provider 测试 |
| `tests/agent/test_chat_agent.py` | 修改 | InputInform 和错误传播测试 |
| `tests/routes/test_chat_ws.py` | 修改 | 协议、竞态、持久化和日志测试 |

### 6.2 前端子模块

| 文件/目录 | 变更 | 责任 |
|---|---|---|
| `src/types/vision.ts` | 新增 | 视觉配置、运行时和图片类型 |
| `src/api/vision.ts` | 新增 | 视觉配置 API |
| `src/stores/vision.ts` | 新增 | 轻量可序列化状态 |
| `src/composables/useVision.ts` | 新增 | UI/运行时 facade |
| `src/utils/visionSessionController.ts` | 新增 | MediaStream 生命周期 |
| `src/utils/screenCapture.ts` | 新增 | Canvas/JPEG/Base64 一次截图 |
| `vitest.config.ts` | 新增 | 前端单元测试运行环境与覆盖范围 |
| `package.json`、`package-lock.json` | 修改 | 引入 Vitest 并增加 `npm run test` |
| `src/types/websocket.ts` | 修改 | 新增视觉和 generation error payload |
| `src/utils/websocketSessionController.ts` | 修改 | 发送图片、分发新事件 |
| `src/composables/useWebSocket.ts` | 修改 | 截图请求与失败 handler |
| `src/composables/useChat.ts` | 修改 | submission gate 与自动截图 |
| `src/stores/chat.ts` | 修改 | timeline union、通用 failure action |
| `src/types/message.ts` | 修改 | timeline message/notice 类型 |
| `src/components/chat/InputBox.vue` | 修改 | 在 VAD 右侧放置 `VisionInput` 并接入发送 gate |
| `src/components/chat/VisionInput.vue` | 新增 | 当前标签页 MediaStream 运行时控制 |
| `src/components/chat/ChatErrorBubble.vue` | 新增 | 瞬态错误气泡 |
| `src/components/chat/ChatTimelineItem.vue` | 新增 | 统一时间线 dispatcher |
| `src/components/chat/MessageList.vue` | 修改 | 渲染联合时间线 |
| `src/components/live2d/StageChatHistory.vue` | 修改 | Stage 联合时间线 |
| `src/pages/settings/modules/vision.vue` | 新增 | 只编辑后端 `vision.enabled` 的视觉设置页 |
| `src/router/index.ts` | 修改 | 替换视觉 placeholder |
| vision/chat 相关 `*.spec.ts` | 新增 | store、controller、capture、gate 和 failure 状态机测试 |

## 7. 测试策略

### 7.1 测试分层

| 层级 | 重点 | 是否调用真实 LLM |
|---|---|---|
| 领域单元测试 | 配置、模型、Base64 校验、coordinator | 否 |
| Provider 单元测试 | 多模态 messages 序列化与错误映射 | 否，mock SDK |
| Agent 单元测试 | Memory 边界、成功 commit、错误传播 | 否，mock LLM/Memory |
| WebSocket 集成测试 | 三种输入、VAD 握手、终态竞态、无持久化 | 否，mock Agent/Provider |
| 前端状态测试 | capture、submission、generation failure | 否 |
| 浏览器手工测试 | getDisplayMedia、track ended、default/stage UI | 否或 mock 后端 |
| 真实端到端测试 | 当前屏幕图 + 文本交给多模态模型 | 是，仅验收阶段 |

### 7.2 核心场景矩阵

| 视觉 | 输入来源 | 截图 | LLM | 预期 |
|---|---|---|---|---|
| 关 | 键盘 | 不触发 | 成功 | 现有纯文本成功 |
| 开 | 键盘 | 成功 | 成功 | 一张图 + 文本，成功归档文本 |
| 开 | 普通 ASR | 成功 | 成功 | 复用键盘发送路径 |
| 开 | VAD+ASR | 成功 | 成功 | generation 握手后多模态成功 |
| 开 | 任意 | unavailable | 成功 | 纯文本发送一次 |
| 开 | 任意 | 编码失败 | 成功 | 纯文本发送一次 |
| 开 | VAD+ASR | timeout | 成功 | 超时后纯文本发送一次 |
| 开 | 任意 | 成功 | `LLMError` | 瞬态错误，无归档/Memory |
| 开 | 任意 | 成功 | HTTP 200 自然拒绝 | 正常 AI 回复并归档 |
| 开 | VAD+ASR | 等待中 | VAD interrupt | 取消等待，迟到图丢弃 |
| 开 | 任意 | 成功 | Error 与 interrupt 竞争 | 首个终态获胜 |

### 7.3 Base64 测试规范

所有测试必须：

- 使用很小的合成 JPEG fixture；
- 把 Base64 当成 opaque 字段；
- 优先断言长度、摘要、MIME、前后固定字段；
- 避免整包 equality diff；
- 禁止 snapshot 完整 payload；
- 禁止读取或打印真实屏幕截图 Base64；
- 禁止在失败消息中拼接 fixture 内容；
- 日志测试显式断言不会出现 fixture 的完整编码。

### 7.4 generation 竞态测试

竞态测试应使用可控 Event/Future，而不是依赖随机 sleep：

1. 挂起 LLM；
2. 精确控制 Error 或 interrupt 哪一方先获得 send lock；
3. 断言只发出一个终态；
4. 断言 state invalidation 与 send 在同一临界区；
5. 启动 generation B；
6. 释放 Error(A)；
7. 断言 B 的 stream、TTS 和 UI 状态不变。

## 8. 日志与安全护栏

### 8.1 永不输出

任何环境都不得输出：

- 图片 Base64；
- data URL；
- 原始图片字节；
- Canvas/Blob 内容；
- 完整 `InputInform`；
- 完整 WebSocket image payload；
- 完整 Provider messages；
- 完整 request params；
- 可能包含输入值的原始校验异常 `repr`；
- 可能回显请求体的原始 Provider `str(exc)`。

### 8.2 可以输出

允许记录：

- `generation_id`；
- `chat_id`；
- `source=screen`；
- MIME；
- encoded/decoded length 整数；
- capture/encode/provider duration；
- validation status code；
- Provider/model；
- 安全 HTTP 状态码或 request ID；
- 异常类型名；
- success/failure boolean。

### 8.3 前端限制

- 不在 `console.log/error/warn` 中传入 image payload；
- 不把 Base64 放入 Pinia、localStorage、IndexedDB 或 localforage；
- 不把 Base64 放进 toast/error 文案；
- Vue devtools 可观察状态中不得出现图片内容；
- capture result 发出后立即释放局部引用。

## 9. 建议提交计划

以下是建议的 point 划分。实施中可以根据实际耦合微调，但不得把不相关改动塞进同一 commit。

### 9.1 后端主仓库

1. `docs(visual-understanding/step 0): add implementation plan`
2. `feat(visual-understanding/step 1): add vision config and input models`
3. `feat(visual-understanding/step 1): add safe image validation and capture coordination`
4. `test(visual-understanding/step 1): cover vision config and validation`
5. `feat(visual-understanding/step 2): extend llm providers with image input`
6. `test(visual-understanding/step 2): cover multimodal provider serialization`
7. `fix(visual-understanding/step 3): propagate chat agent llm failures`
8. `test(visual-understanding/step 3): cover input boundaries and failure propagation`
9. `feat(visual-understanding/step 4): add websocket vision capture protocol`
10. `fix(visual-understanding/step 4): add generation-aware chat failures`
11. `test(visual-understanding/step 4): cover capture and terminal-state races`
12. `docs(visual-understanding/step 8): document visual runtime and protocol`
13. `chore(visual-understanding/frontend): update frontend submodule`

### 9.2 前端子模块

1. `feat(visual-understanding/step 5): add screen capture runtime`
2. `feat(visual-understanding/step 5): attach screen frames to text submissions`
3. `feat(visual-understanding/step 5): answer vad capture requests`
4. `refactor(visual-understanding/step 6): introduce chat timeline items`
5. `feat(visual-understanding/step 6): render transient generation failures`
6. `feat(visual-understanding/step 7): add vision settings and runtime controls`
7. `test(visual-understanding/step 5): add vitest vision coverage`
8. `test(visual-understanding/step 6): cover generation failure state`
9. `docs(visual-understanding/step 8): document frontend visual runtime`

每次提交前只暂存本 point 的文件，并执行与改动范围匹配的 basic check。

## 10. 端到端验收顺序

建议按以下顺序执行，失败时容易定位所属层：

1. 启动后端，确认视觉配置加载且日志不含敏感内容；
2. 通过设置页 GET + PUT 开关模块，确认只持久化 `enabled`，其他字段写入被拒绝；
3. 模块关闭时，确认主页 `VisionInput` 不可用，键盘、普通 ASR 和 VAD+ASR 纯文本行为无回归；
4. 模块开启后，确认默认聊天和 Stage 的 VAD 右侧都出现可用但未激活的 `VisionInput`；
5. 用户点击运行时按钮并在浏览器选择屏幕/窗口；
6. 在设置页和主页之间切换，确认路由组件卸载不会停止共享流；
7. 键盘发送，确认一轮只截一张图，聊天框不显示图片预览、徽标或元数据；
8. 普通 ASR 自动/手动发送，确认复用同一路径；
9. VAD+ASR 发送，确认 receive loop 能接收 capture result；
10. 浏览器原生停止共享，确认立即回到纯文本，但模块开关仍开启且按钮可重新启动；
11. 共享 active 时从设置页关闭模块，确认 tracks 被停止、连接状态关闭且主页按钮不可用；
12. 模拟截图失败、超限和 timeout，确认文本只发送一次且没有 toast 或 `ChatErrorBubble`；
13. 临时使用 SiliconFlow `Pro/moonshotai/Kimi-K2.6` 验证真实视觉理解，且不改动其他 role/model；
14. 模拟 Provider 非成功响应、流式失败和 pre-success 编排失败，确认统一发送 `output:chat:error`；
15. 验证失败轮次不进入 ChatStorage、Memory、recent、compression 和 long-term；
16. 模拟 HTTP 200 自然语言拒绝，确认仍正常归档；
17. 确认本地图片失败、协议错误、TTS 单段失败和 durable success 后错误不误用 `output:chat:error`；
18. 在截图等待时触发 VAD interrupt，确认迟到结果丢弃；
19. 在 generation 即将失败时触发 VAD interrupt，分别验证两种锁顺序；
20. 确认失败 generation 音频被丢弃；
21. 确认错误气泡在默认聊天和 Stage 中正确显示；
22. 刷新页面和重新加载聊天，确认瞬态用户文本/错误气泡消失；
23. 审查后端日志、浏览器 console、Pinia 和测试输出；
24. 运行前后端完整检查，并在验收后恢复用户的本地模型配置。

## 11. 回滚与故障隔离

### 11.1 运行时关闭

`vision.enabled=false` 应完全关闭视觉入口。旧文本、ASR、VAD、TTS、Live2D 和历史链路继续工作。

### 11.2 前端故障

如果屏幕共享 API、Canvas 或编码失败：

- 释放临时资源；
- 当前合法 InputText 仍发送一次；
- 截图/编码级失败完全静默，不显示 toast、ChatErrorBubble 或图片提示；
- 只有影响 MediaStream 启停的权限拒绝、不支持和 track ended 才反映在运行时按钮状态；
- 不需要清理任何持久化图片，因为图片从未持久化。

### 11.3 后端图片故障

如果图片 envelope 无效、超限或解码失败：

- 丢弃图片；
- 记录安全 warning；
- 当前文本继续；
- 不向前端发送 generation failure。

### 11.4 远端生成故障

如果 LLM、Provider stream 或 generation 编排在 durable success effects 开始前发生不可恢复的终态失败：

- generation 进入 failed；
- 不做成功持久化；
- 发送瞬态错误；
- 清理 partial reply 和 TTS。

若错误发生在 durable success effects 已经开始之后，不得再把它泛化为“LLM generation failed”。这类情况应保留真实成功状态，并按对应辅助模块或持久化故障处理。

### 11.5 协议回滚

新字段均为可选或新增 message type，因此后端可通过关闭视觉配置回退到纯文本。不需要数据库迁移，也不存在图片数据清理任务。

## 12. 已确认决策（2026-07-11）

D1 至 D6 已全部确认。以下内容是实施约束，不再保留备选分支。

### D1：完整设置页与主页运行时按钮均交付

- `/settings/modules/vision` 实现真实设置页，导航位于“设置 -> 机体模块 -> 视觉功能”；
- 页面首版只有一个持久化模块开关，只写 `vision_config.yaml.enabled`；
- 主页新增独立 `VisionInput.vue`，在 VAD `RealtimeVoiceInput` 右侧控制当前标签页 MediaStream；
- 默认聊天和 Live2D Stage 都显示该按钮；
- 模块关闭时按钮不可用，模块开启时按钮可用但不会自动请求共享权限；
- 设置页关闭模块时停止当前流并同步连接状态；
- 浏览器原生停止共享只关闭运行时，YAML 开关保持开启；
- `visionSessionController` 跨路由持有流，组件卸载不停止 tracks。

实际开发设置页、`VisionInput` 和 `ChatErrorBubble` 时再调用 `design-taste-frontend` 与 `ui-ux-pro-max`，文档阶段不调用。

### D2：建立 Vitest 测试基础设施

当前 frontend 尚无单元测试 runner。本 feature 引入 Vitest、增加 `npm run test`，并覆盖：

- vision store；
- `visionSessionController`；
- 截图缩放与有界压缩 helper；
- `VisionInput` 状态；
- submission gate；
- VAD capture request/result 的 generation 关联；
- `failActiveGeneration()` 与 stale generation；
- 瞬态 history reload；
- Base64 不进入 Pinia。

Vitest 不替代 Chrome/Edge 对真实 `getDisplayMedia()` 权限和 track `ended` 的手工验收。

### D3：首版不显示图片，图片失败静默降级

沿用 OLV 的首版行为：聊天框不显示截图预览、缩略图、附件徽标、图片消息或元数据。截图、编码、校验或等待失败时，静默降级为恰好一次纯文本发送；不显示 toast、`ChatErrorBubble` 或其他提示。

图片可见性和审计交互属于未来独立前端扩展。远端 generation failure 的错误气泡不受此决策影响。

### D4：SiliconFlow + Kimi K2.6 做真实验收

Provider 保持 `siliconflow`。当前 `deepseek-ai/DeepSeek-V4-Flash` 不支持视觉理解，真实验收时只临时把 chat role 模型改为 `Pro/moonshotai/Kimi-K2.6`。

不修改 provider、base URL、API key、`compress_light` 或 `title_gen`。Kimi 模型修改是本地验收 override，除非用户另行要求，否则不作为默认配置提交。

### D5：配置 API 使用 GET + PUT

后端拥有：

```http
GET /api/vision/config
PUT /api/vision/config
```

前端只提供 API client wrapper。GET 返回完整安全配置；PUT 幂等更新现有单例资源，首版通过 `VISION_CONFIG_WRITE_FIELDS = {"enabled"}` 只允许 `{ "enabled": boolean }`，其他字段写入返回 HTTP 400。

PUT 的实现必须串行化同一进程内的并发更新，并以同目录临时文件 + 原子 replace 落盘。只有写入成功后才能发布新的内存配置和成功响应；写入失败时，磁盘与内存都保留最后确认值。

三个状态层必须保持独立：

| 层 | 所有者 | 持久化 | 协议 |
|---|---|---|---|
| `vision_config.yaml.enabled` | 后端 | YAML | GET/PUT |
| active browser MediaStream | 前端标签页 | 仅运行时 | `getDisplayMedia()` |
| connection vision state | 后端 WebSocket 连接 | 仅连接期 | `input:vision:state` |

有效视觉输入条件是 `config.enabled AND connection state enabled AND active/valid image`。POST 不用于创建 MediaStream。

### D6：`output:chat:error` 覆盖所有 pre-success 终态 generation failure

`output:chat:error` 覆盖所有发生在 durable success effects 开始前、会导致本 generation 无法完成的终态错误，包括 `LLMError`、Provider stream failure 和不可恢复的 generation 编排失败。

它不覆盖本地图片准备失败、JSON/协议校验错误、TTS 单段失败，以及 durable success effects 开始后的辅助错误。事件必须携带 `generation_id`，并遵守 send lock 内“第一个终态获胜”。前端统一调用通用 `failActiveGeneration()`，不得把 action 命名或实现耦合到 `ChatErrorBubble`。

## 13. 实施就绪结论

首版视觉理解的关键设计已经闭合：

- 输入范围闭合；
- 图片格式与传输闭合；
- 三种 InputText 链路闭合；
- Memory 与持久化边界闭合；
- Provider 多模态边界闭合；
- VAD 异步截图协调闭合；
- 本地降级与远端失败语义闭合；
- generation 竞争闭合；
- 前端瞬态时间线闭合；
- Base64 日志与测试约束闭合。

D1 至 D6 均已确认，没有剩余的产品或工程阻塞决策。因此可以从 Step 1 开始实施；实现中如果发现需要改变上述边界，必须先更新设计文档再修改代码。
