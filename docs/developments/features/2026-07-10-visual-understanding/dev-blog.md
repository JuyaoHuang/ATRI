---
status: in-progress
feature: visual-understanding
created: 2026-07-10
updated: 2026-07-11
backend_branch: feat/visual-understanding
frontend_branch: feat/visual-understanding
---

# 视觉理解开发日志

本文记录 `2026-07-10-visual-understanding` 的实际实施结果、验证证据和剩余验收项。长期稳定结论已经同步到 `docs/developments/modules/vision/` 与 `docs/developments/api/`；完整设计与执行顺序分别见 `design-docs.md` 和 `visual-implement.md`。

## 交付范围

首版交付：

- 只支持浏览器屏幕共享流；
- 每轮最多截取一张 JPEG；
- 键盘、普通 ASR、VAD + ASR 三种 InputText 来源都能携带可选图片；
- 使用当前 LLM Provider/model 的多模态能力，不引入 OCR 或外部视觉服务；
- 设置页持久化模块开关，主页按钮控制当前标签页 MediaStream；
- Provider/pre-success generation failure 只显示当前页面瞬态错误气泡。

首版不交付：

- 摄像头；
- 文件上传；
- 多图；
- 持续视频推理；
- 图片预览、缩略图或附件徽标；
- 图片归档、Memory 或上下文压缩。

## 分支

| 仓库 | 分支 | 说明 |
| --- | --- | --- |
| `atri` | `feat/visual-understanding` | 后端、协议、长期文档与前端子模块指针。 |
| `atri/frontend` | `feat/visual-understanding` | 浏览器采集、视觉 UI、瞬态错误时间线与 Vitest。 |

## 实施进度

| Step | 状态 | 结果 |
| --- | --- | --- |
| Step 0 | 完成 | 设计、实施计划和 SiliconFlow 独立 Provider。 |
| Step 1 | 完成 | 视觉配置、领域模型、REST、校验和 capture coordinator。 |
| Step 2 | 完成 | LLM 单图接口、Provider 序列化与 `image_detail`。 |
| Step 3 | 完成 | `InputInform` 数据边界和 LLM 异常传播。 |
| Step 4 | 完成 | WebSocket 截图协议、VAD 协调和 generation failure 终态。 |
| Step 5 | 完成 | 前端 MediaStream controller、截图编码和文本发送接入。 |
| Step 6 | 完成 | 联合时间线与瞬态 generation error bubble。 |
| Step 7 | 完成 | 视觉设置页、主页运行时按钮和 UI 状态测试。 |
| Step 8 | 进行中 | 长期文档、真实浏览器、真实 Provider 和综合审查。 |

## 后端实施记录

### Step 0：方案与 Provider 边界

- `1ab5fe2 docs(visual-understanding/step 0): add implementation plan`
- `92107cf refactor(visual-understanding/step 0): extract siliconflow provider`
- `cf6df3e docs(visual-understanding/step 0): implement visual doc`

SiliconFlow 从通用 `openai_compatible.py` 的别名注册中抽离为独立 Provider 类，同时继续继承 OpenAI 兼容协议实现。这为视觉差异保留专用扩展位置，现有配置仍使用 `provider: siliconflow`。

### Step 1：视觉领域与配置

- `86b6332 feat(visual-understanding/step 1): add vision config and input models`
- `56afa2b feat(visual-understanding/step 1): add image validation and capture coordination`
- `e0384e9 test(visual-understanding/step 1): cover vision config and validation`

新增：

- `config/vision_config.yaml`；
- `InputText`、`InputImage`、`InputInform`；
- 完整安全配置 GET 与只写 `enabled` 的 PUT；
- JPEG/Base64/大小校验；
- generation-keyed `VisionCaptureCoordinator`；
- 应用层 WebSocket 文本帧大小检查。

图片字段使用 `repr=False`，验证失败只返回短状态码和整数长度。

### Step 2：LLM 多模态调用

- `90b7dc4 feat(visual-understanding/step 2): extend llm providers with image input`
- `3e43ccc test(visual-understanding/step 2): cover multimodal provider serialization`

`LLMInterface` 增加可选 `input_image`。共享 helper 只把最终当前 user 消息转为 `text + image_url`，不修改历史消息或调用方列表。

当前支持该调用形态的 Provider：

- OpenAI compatible；
- SiliconFlow；
- Xiaomi。

具体模型是否支持视觉仍由运行配置决定。HTTP 200 的自然语言拒绝继续按成功回复处理。

### Step 3：Agent 与 Memory 边界

- `012aa9a fix(visual-understanding/step 3): propagate chat agent llm failures`
- `846fc8e test(visual-understanding/step 3): cover input boundaries and failure propagation`

`ChatAgent` 接受 `str | InputInform`：

- InputText 进入 Memory 上下文、成功提交和长期检索；
- InputImage 只进入本轮 LLM 调用；
- LLM 失败保持异常控制流，不再转成正常 AI 文本或 system note。

### Step 4：WebSocket 与 generation failure

- `26676d1 feat(visual-understanding/step 4): add websocket vision capture protocol`
- `c75b0c0 fix(visual-understanding/step 4): add generation-aware chat failures`
- `ad841bc test(visual-understanding/step 4): cover capture and terminal-state races`

新增协议：

- `input:vision:state`；
- `input:vision:capture-result`；
- `control:vision:capture-request`；
- `input:text.data.image`；
- `output:chat:error`。

键盘/普通 ASR 直接携带可选图片。VAD + ASR 在后台 generation task 等待截图 Future，主 receive loop 保持可接收 capture result 和 interrupt。

generation complete、failure 与 interrupt 都在 send lock 内提交首个终态。pre-success failure 不进入 ChatStorage、Memory、recent、compression 或 long-term；durable success 开始后的辅助失败不会被误标为 generation failure。

## 前端实施记录

### Step 5：屏幕采集与发送

- `bc3bdd6 feat(visual-understanding/step 5): add screen capture runtime`
- `e689931 feat(visual-understanding/step 5): connect screen capture to chat turns`
- `98bb06a test(visual-understanding/step 5): add vitest vision coverage`

`visionSessionController` 跨路由持有 MediaStream、video 与 track。Pinia 只保存安全配置和轻量状态。

截图流程支持最长边缩放、JPEG 编码、Blob 大小检查和最多一次有界二次压缩。Base64 只作为局部返回值直接发送，不进入 Pinia、localStorage、IndexedDB 或 console。

`useChat.sendMessage()` 使用 submission gate 包住截图与发送。无帧、编码失败和超限都静默降级为文本，用户文本只发送一次。

### Step 6：瞬态错误时间线

- `91df7a4 refactor(visual-understanding/step 6): introduce chat timeline items`
- `e6c6a09 feat(visual-understanding/step 6): render transient generation failures`
- `f8a25b2 test(visual-understanding/step 6): cover generation failure state`

聊天显示状态升级为：

```text
ChatTimelineItem = ChatMessageItem | ChatNoticeItem
```

通用 `failActiveGeneration()` 严格匹配 chat、character 和 generation。stale failure 不影响新 generation。错误 notice 使用消息气泡样式，但不具备 AI role、角色头像、TTS 或 Live2D 副作用。

历史重载会用持久化消息整体替换运行时时间线，因此失败用户文本和错误气泡都会消失。

### Step 7：设置页与运行时按钮

- `52ae639 feat(visual-understanding/step 7): add persistent vision setting`
- `9dff564 feat(visual-understanding/step 7): add vision runtime control`
- `a7e5fea test(visual-understanding/step 7): cover vision controls`

`/settings/modules/vision` 只有一个开关：是否启用视觉模块。页面加载 GET，切换时 PUT `{enabled}`。禁用成功后停止 controller；失败时保留服务端最后确认状态与活动流。

主页 `VisionInput` 放在 `RealtimeVoiceInput` 右侧。默认聊天与 Stage 共用同一个 `InputBox`，因此两种布局自动保持一致。

UI 已覆盖：

- 模块不可用；
- 可用未共享；
- 请求权限中；
- 正在共享；
- 权限拒绝；
- 浏览器不支持。

组件卸载不停止 stream。浏览器 track `ended` 只关闭运行时，后端 YAML 开关保持开启。

## 综合审查硬化

首次综合审查没有发现 Critical 问题，但确认了 4 个合并前必须修复的一致性边界，并给出若干安全/运行时建议。复核又发现 VAD speech-end 会无界等待旧 generation commit；该问题也已完成修复：

后端：

- `f302d89 fix(visual-understanding/step 4): prevent duplicate durable turn commits`
- `967899c fix(visual-understanding/step 1): reserve websocket envelope headroom`
- `f750c39 fix(visual-understanding/step 4): correlate rejected text requests`
- `960aa78 fix(visual-understanding/step 1): make config updates transactional`
- `5277250 fix(visual-understanding/step 2): sanitize provider exceptions`
- `cb6966b fix(visual-understanding/step 4): clarify committing interrupt state`
- `fdfdb74 fix(visual-understanding/step 4): bound commit handoff wait`

前端：

- `4b8c179 fix(visual-understanding/step 6): preserve committing chat generation`
- `fe34a4e fix(visual-understanding/step 5): downgrade oversized vision frames`
- `2ae4138 fix(visual-understanding/step 6): recover rejected pending submissions`
- `847214a fix(visual-understanding/step 5): require a usable shared frame`
- `1ebde04 fix(visual-understanding/step 5): reject oversized text frames locally`
- `ad3f9ba test(visual-understanding/step 5): update submission transport fixture`

最终语义：

- LLM 流正常耗尽后先在 send lock 内认领 `committing`。此时 VAD 仍停止音频，但不取消聊天任务、不重复写 interrupted round；
- 图片传输预算以完整 JSON UTF-8 帧为准。有图文本超限时移除图片并发送一次文本，降级后仍超限则不写 socket 并回滚 pending；VAD 图片回传超限时改发 `failed`；
- `input:text.request_id` 只关联 generation 建立前的明确拒绝，stale request 或 streaming generation 不受顶层 `error` 影响；
- Vision PUT 串行、原子落盘，写成功后才发布内存状态；
- Provider 项目异常不保留 SDK 原始文本/cause/context；
- controller 只有拿到 live track 和非零视频帧尺寸后才进入 active；
- 新一轮 speech-end 最多等待旧 `committing` task 5 秒；超时不取消旧任务、不调用 ASR，并返回 receive loop。

## 自动化验证

### 后端最终检查（2026-07-11）

```text
mypy: Success: no issues found in 108 source files
ruff: All checks passed
pytest tests/routes/test_chat_ws.py -q: 61 passed
pytest tests/ -v（联调配置快照）: 547 passed, 3 failed, 4 deselected
```

完整 pytest 的三条失败均为根 YAML 默认值耦合断言：一条固定期望特定 VAD Provider，另两条固定期望视觉模块关闭。它们会在本地联调配置选择其他合法值时失败；本轮没有为迁就断言而修改用户配置。视觉、Provider、Agent、WebSocket 和前端行为测试均通过。后续应把这些根配置测试改为隔离配置，而不是依赖用户工作区 YAML。

### 前端最终检查（2026-07-11）

```text
Vitest: 12 test files passed, 42 tests passed
type-check: passed
build: passed
lint: 0 errors
```

lint 保留两条既有 warning：

- `src/components/airi-ui/TransitionVertical.vue:74`
- `src/components/airi-ui/TransitionVertical.vue:75`

两条均为本 feature 之前已经存在的 `no-explicit-any` warning，未顺手修改。

## 安全检查

当前实现遵守：

- 不打印图片 Base64、data URL、完整 `InputInform` 或完整 Provider request params；
- 不把图片写入聊天、Memory 或前端持久化；
- 测试只把图片编码当作小型 opaque fixture；
- Provider 原始错误不返回前端；
- unrelated TTS/VAD 配置不纳入本 feature 提交。

浏览器和 Provider 验收完成后再次检查临时日志，敏感图片模式命中数为 `0`。Playwright 快照、页面截图和 Provider 临时 JPEG 均已删除，没有进入工作区提交内容。

## 浏览器验收（2026-07-11）

使用 Microsoft Edge + Playwright CLI 验证：

- `/settings/modules/vision` 只渲染一个 switch；
- GET 能还原后端状态；
- PUT 开启时，`vision_config.yaml` 只有 `enabled: false -> true`；
- PUT 关闭后配置恢复，主页按钮立即变为 disabled；
- 默认聊天工具栏顺序为单次语音、VAD、视觉；
- Stage 复用同一 InputBox，视觉按钮仍位于 VAD 右侧；
- 视觉按钮点击会触发 Edge 原生屏幕共享选择器，并进入 `starting` 状态；
- 1440×900 亮色、强制暗色和 390×844 移动端布局均无溢出或遮挡；
- 浏览器 console 当前检查为 `0 errors / 0 warnings`。

自动化不能可靠操作 Edge 原生共享选择器，因此以下项目不伪造通过：

- 在原生选择器中成功选定屏幕/窗口；
- 使用浏览器原生“停止共享”；
- 真实 track `ended` 后的 UI 回落；
- 活动 stream 跨设置页/主页路由切换。

这些生命周期边界已有 controller/Vitest 覆盖，但仍保留为人工浏览器验收项。

## 真实 SiliconFlow 验收（2026-07-11）

该次验收只在内存中覆盖 chat role model，未写入 YAML：

```text
provider=SiliconFlowLLM
model=Pro/moonshotai/Kimi-K2.6
decoded_bytes=102727
encoded_chars=136972
image_detail=high
latency_ms=4164
request_success=true
expected_visual_marker=true
reply_chars=15
```

测试图片是 ATRI 视觉设置页的临时 JPEG。模型正确判断“白色主背景 + 一个可见开关”，证明单图通过 SiliconFlow 多模态请求到达并被模型理解。

额外做了小号中文 UI 文本识别探针。请求成功，但模型没有可靠识别“视觉功能”四个字，因此不把它记录为 OCR 通过。这不影响首版验收：本 feature 依赖模型通用视觉能力，未承诺 OCR 服务或 OCR 准确率。

该次验收的收尾快照中：

- `config/llm_config.yaml` 没有改动；
- `config/vision_config.yaml` 已恢复 `enabled: false`；
- Provider 临时 JPEG 和 Playwright 产物已删除；
- 日志未出现 Base64 或 data URL。

## Chrome 自窗口共享兼容性缺陷调查（2026-07-11）

### 现象与复现边界

人工联调发现：在 Live2D 模式下开启视觉流，并在浏览器原生选择器中把正在显示 ATRI 的 Chrome 窗口自身选为共享来源后，窗口会闪烁，Live2D 模型消失，背景变为白色。普通 DOM、WebSocket 和消息发送仍可继续，但滚动聊天记录、切换会话和 Live2D 渲染明显降帧。

停止共享不能恢复原有帧率。刷新页面可以重新创建 Live2D，但新实例仍明显低帧；只有完整退出该 Chrome 浏览器进程树并重新启动，才可能恢复硬件渲染。

故障在选择共享来源后、发送 `InputInform` 前已经发生。键盘输入和 VAD + ASR 最终都会进入同一轮聊天发送链路，因此两种输入方式都会观察到故障，但它们不是触发源。真实 LLM、TTS 和截图上传也不是复现该白屏的必要条件。

稳定复现所用的手工浏览器环境为：

| 项目 | 取值 |
| --- | --- |
| Chrome 可执行文件 | `E:\Google\Chrome-bin\chrome.exe` |
| Chrome 版本 | `121.0.6167.185` |
| 页面 | `http://localhost:5200/`，Live2D 模式 |
| 集成显卡 | AMD Radeon 780M |
| AMD 驱动 | `31.0.14005.22001` |
| 显示模式 | `2560 x 1600 @ 165 Hz` |
| 共享来源 | 当前正在显示 ATRI 的 Chrome 窗口自身 |

用户同时确认该 Chrome 长期提示“当前无法自动更新 Chrome，请重新下载 Chrome 安装”，因此版本停留在 2024 年初发布的 Chrome 121。该异常更新状态是本次兼容性判断的重要环境因素。

### 进程级证据

复现前在 `2026-07-11 23:42:27.680 +08:00` 记录进程快照；开启共享后保持页面、流和浏览器进程不变，再记录同一进程树。结果如下：

| 角色 | 复现前 | 复现后 | 结论 |
| --- | --- | --- | --- |
| Chrome browser | PID `287780` | 仍存活 | 浏览器主进程没有整体退出。 |
| GPU process | PID `285612`，硬件 ANGLE 路径 | 原进程退出；新 PID `287800` | Chrome 重建了 GPU 子进程。 |
| 新 GPU 参数 | 不使用 SwiftShader | `--use-gl=angle --use-angle=swiftshader-webgl` | 新进程已经回退到 SwiftShader 软件 WebGL。 |
| ATRI 主 renderer | PID `288984`，5 秒 CPU `0.328 s` | PID 保持不变，5 秒 CPU `0.016 s` | renderer 没有重建，但 Live2D 渲染循环几乎停止。 |

故障链路为：

```text
Chrome 121 + AMD 780M 硬件 ANGLE + Live2D WebGL
  -> getDisplayMedia 选择当前 ATRI Chrome 窗口自身
  -> 原硬件 GPU process 退出
  -> renderer 中既有 Live2D WebGL context 失效
  -> Live2D 消失，背景白屏
  -> Chrome 创建新的 GPU process
  -> 新进程以 swiftshader-webgl 软件渲染运行
  -> DOM 与 WebSocket 仍可使用，但页面合成和 Live2D 持续低帧
```

停止共享后的验证中，GPU PID 仍为 `287800`，且仍带有 `--use-angle=swiftshader-webgl`。这说明停止 MediaStream 不会让当前 Chrome 会话重新启用硬件 GPU。刷新只能在 SwiftShader 上创建新的 WebGL context，因此可以解释“模型重新出现，但体感只有约 15 FPS”的现象。

Windows `System` 日志在复现窗口内没有显示驱动 TDR、Display、AMD 或 NVIDIA GPU reset 事件，`Application` 日志也没有 Event ID 1002 的 Application Hang。Windows Error Reporting 在 `23:45:32` 记录了一次 Chrome 121 `APPCRASH`：异常码 `0xc0000005`，故障程序路径同为 `E:\Google\Chrome-bin\chrome.exe`。该 WER 记录不能单独判定崩溃进程角色，但与浏览器侧子进程异常一致；它不支持“整个 Windows 显示驱动被重置”的解释。

因此，本次 Live2D 白屏与持续低帧的直接原因是手工 Chrome 会话的 GPU 进程失效和软件渲染回退。ATRI 的自窗口共享操作暴露了这一浏览器/ANGLE/驱动组合问题，但后端 LLM 调用不是直接根因。

### 对照与排除结果

受控复现使用独立浏览器会话和只记录耗时、长度、进程状态的安全探针；没有读取、打印或保存图片内容。对照结果如下：

| 对照项 | 结果 |
| --- | --- |
| Microsoft Edge 150 | 选择自身窗口、运行视觉流和完成请求后未复现白屏或持续掉帧。 |
| Playwright 隔离 Chrome | 同样操作未复现；问题稳定集中在用户手工启动的旧 Chrome 会话。 |
| 无视觉基线 | `requestAnimationFrame` 的 p95 约 `6.0 ms`，Long Task 为 `0`。 |
| 截图与编码 | 完整经过 `drawImage`、JPEG `toBlob`、`arrayBuffer` 和 Base64 编码；从提交开始到 WebSocket 边界约 `86.9 ms`，未造成卡死。 |
| WebSocket 文本帧 | 约 `112–119 KB` 的完整帧能够发送；测试只记录字节数，不读取图片编码。 |
| 等待与错误 UI | 本地回环模拟约 27 秒 Provider 等待并返回 generation error bubble，rAF p95 约 `6.0 ms`、最大帧间隔约 `11.9 ms`、Long Task 为 `0`。 |
| 真实模型 | `siliconflow + Pro/moonshotai/Kimi-K2.6` 的真实视觉请求完成并返回；后端日志也记录了后续 `Chat complete`，没有单独复现白屏。 |
| TTS 与 transient error | 正常 TTS、等待回复和错误气泡均未单独复现 GPU 进程切换。 |

这些对照说明 JPEG、Base64、JSON 序列化、WebSocket 帧、真实 Kimi 2.6 调用、TTS 和错误气泡均不是充分触发条件。当前源码调用 `getDisplayMedia({ video: true, audio: false })`，故障则发生在用户选中自身窗口时；所以键盘与 ASR/VAD 的共同表现来自它们共享了已经退化的浏览器渲染环境，而不是两条输入链路各自卡死。

### 独立发现：WebSocket cleanup 后聊天任务仍可运行

调查中另行确认了一条后端 task 生命周期竞态。它需要后续单独修复，但不是 Live2D 白屏根因。

当前 `websocket_endpoint()` cleanup 会释放视觉等待、停止 TTS，再调用 `WebSocketVADState.release()`。但是 `release()` 只清空 `current_chat_task` 引用并使 generation 失效，没有对仍在运行的 task 执行 `cancel()` 和 `await`。

后端日志给出了确定时间线：

```text
21:37:22.610  收到 input:text
21:37:29.466  WebSocket closed；cleanup complete
21:37:55.641  旧任务继续收到 Provider chunk，并因 generation stale 丢弃
```

也就是说，旧 Provider/ChatAgent task 在连接 cleanup 后仍运行约 26 秒。它可能造成旧任务跨越重连继续占用资源，但不能解释本次故障，因为 Live2D 白屏在浏览器选择自身窗口时已经发生，且受控浏览器在没有该竞态时仍能验证 GPU 路径差异。

### 当前恢复与规避方式

1. 不要把正在显示 ATRI 的 Chrome 窗口自身选为共享来源；优先选择整个屏幕或其他窗口。
2. 一旦进入 SwiftShader，停止共享或只刷新页面不足以恢复；应保存其他标签页内容并完整退出整个 Chrome 进程树后重启。
3. 从官方渠道重新安装或升级当前稳定版 Chrome，并在 `chrome://settings/help` 确认自动更新恢复正常。
4. 更新 AMD Radeon 780M 驱动；笔记本环境优先验证设备厂商提供的稳定驱动。
5. 更新后通过 `chrome://gpu` 确认 Compositing、WebGL 和 WebGL2 使用硬件加速，再重新验证自窗口共享。
6. 不把 `--disable-gpu` 或强制 SwiftShader 作为长期方案；它会让 Live2D 从启动开始就使用软件渲染。

### 尚未实现的 ATRI 防护候选

以下项目只记录为后续候选，本次调查没有修改源码，也不能标记为已交付：

- 监听 Live2D canvas 的 `webglcontextlost`，阻止默认销毁流程并把图形上下文丢失转换为明确运行时状态；
- context lost 后停止当前视觉流，并提示用户完整重启浏览器，而不是只刷新页面；
- 在视觉按钮或共享说明中提醒用户不要选择当前 ATRI 窗口自身；
- 对明显过旧或更新异常的 Chrome 显示兼容性警告；
- 评估 `selfBrowserSurface: "exclude"`。该字段最多是浏览器对“当前 browsing surface 是否出现在候选列表中”的提示性约束，不能可靠保证整个当前浏览器窗口都不可被选择；
- 增加安全诊断元数据，例如浏览器版本、`displaySurface` 和 `webglcontextlost` 次数，同时继续禁止记录截图、Base64 或完整请求体；
- 修复 WebSocket cleanup，使连接关闭时对仍在运行的 chat task 执行有界取消与等待，并补充断连/重连竞态测试。

## 剩余验收

- [x] 验证 Edge 能触发原生授权选择器；成功选屏、原生停止共享仍需人工操作。
- [ ] 人工验证活动 stream 跨设置页/主页路由切换不会停止。
- [x] 验证默认聊天与 Stage 的视觉按钮位置、明暗主题和移动端布局。
- [x] 使用 `siliconflow + Pro/moonshotai/Kimi-K2.6` 做真实视觉理解调用。
- [x] Provider 验收清理内存 override 和临时图片；用户配置变化不纳入 feature 提交。
- [ ] 执行最终前后端全量检查和综合代码审查。
- [ ] 更新父仓库前端子模块指针并完成 push/PR。
