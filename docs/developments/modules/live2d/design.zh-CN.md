---
status: active
owner: live2d
created: 2026-07-09
updated: 2026-07-13
source:
  - ../../module-design/CN/Live-2d设计文档.md
  - src/routes/live2d.py
  - src/storage/live2d_storage.py
  - frontend/src/stores/live2d.ts
  - frontend/src/components/live2d/Live2DCanvas.vue
related_code:
  - src/routes/live2d.py
  - src/storage/live2d_storage.py
  - frontend/src/stores/live2d.ts
  - frontend/src/components/live2d/Live2DCanvas.vue
  - frontend/src/components/live2d/ModelSettingsPreviewStage.vue
---

# Live2D 模块总设计

本文把 `live2d` 模块的整体边界接起来。现有子文档分别讲了后端存储/API、前端运行时和表情控制，但还需要一页说明：

1. 当前仓库里的 Live2D 到底已经实现到哪一层。
2. 前后端职责为什么这样划分。
3. 旧设计文档里哪些内容已经不再是当前事实。

## 模块定位

当前 Live2D 不是一个“服务端驱动角色引擎”，而是一个边界清晰的双端模块：

- 服务器管理员通过文件系统安装和移除模型；
- 后端只读发现、校验模型目录，并暴露模型摘要和静态资源；
- 前端负责模型选择、渲染、模型原生动作、点击交互、表情和浏览器本地偏好。

这意味着 Live2D 在系统中的位置更接近：

```text
管理员：data/live2d/models/ 目录维护
后端：实时模型目录 + 只读 API + 静态文件服务
前端：模型选择/关闭 + 舞台运行时 + 自动动作交互 + 用户偏好 + 消息驱动表情
```

## 设计目标

结合旧设计文档、当前代码和近期 git log，当前长期目标可以概括为 4 条：

1. 把服务器模型安装和普通前端用户的舞台运行时明确拆开。
2. 让前端可以在不依赖服务端会话状态的情况下独立管理当前模型与舞台参数。
3. 让 Cubism 2 `.model.json` 与 Cubism 3/4 `.model3.json` 标准目录无需 ZIP、UUID 包装层或 ATRI `metadata.json` 即可被发现和渲染。
4. 表情保持名称级控制；动作由模型运行时和画布内部交互控制，不向普通用户提供动作选择。

## 模块组成

当前 Live2D 模块可以稳定拆成三块：

| 子系统 | 代码 | 职责 |
| --- | --- | --- |
| 后端目录与 API | `src/storage/live2d_storage.py` `src/routes/live2d.py` | 直接子目录实时扫描、最低加载校验、默认模型标记、资源 URL 输出 |
| 前端舞台运行时 | `frontend/src/stores/live2d.ts` `frontend/src/components/live2d/Live2DCanvas.vue` | 当前模型、位置、缩放、默认表情、自动动作交互和 Cubism 2/3/4 统一渲染 |
| 消息驱动表情 | `frontend/src/utils/live2dExpression.ts` + `useWebSocket()` | 从聊天文本中解析 `[expression:...]` 并发出表情请求 |

## 前后端职责划分

### 后端拥有的真相

后端当前拥有这些目录派生事实：

- 有哪些模型
- 模型目录名对应的 ID 和名称
- 设置文件路径
- 缩略图路径
- 表情名称列表
- 哪个有效目录匹配统一默认模型配置

这些值都从当前文件系统和后端配置生成，不写入每模型元数据文件。

### 前端拥有的真相

前端当前拥有这些本地偏好和运行时事实：

- 是否开启舞台模式
- 当前使用哪个模型
- 模型位置、缩放、渲染精度、FPS
- 保存的默认表情与当前临时表情请求
- 哪些表情向 LLM 暴露

### 当前刻意不做的事

系统当前没有服务端维护的：

- 全局 active model
- 服务端表情切换 API
- 服务端动作播放 API
- 口型同步链路
- 成熟的 LLM 工具调用表情系统
- 模型 ZIP 上传、远程重命名或远程删除能力

## 数据流

当前 Live2D 的稳定数据流是：

```text
administrator copies data/live2d/models/<model_name>/
  -> GET /api/live2d/models rescans direct child directories
  -> Live2DStorage validates .model.json/.model3.json + Moc + textures
  -> invalid/incomplete directories are warned and skipped
  -> valid model summaries + static asset URLs
  -> frontend live2d store maps model summaries
  -> Live2DCanvas passes model_url to Live2DModel.from(...)
  -> pixi-live2d-display selects the Cubism 2 or Cubism 3/4 runtime
  -> Pixi runtime renders model
```

## 统一运行时与对象所有权

Cubism 2 与 Cubism 3/4 共用一个 `Live2DCanvas`、一个 store 和一套交互状态。格式差异只收敛在以下薄适配边界：

- 设置文件分别使用 `.model.json` 与 `.model3.json`；
- 参数适配器把统一的 `Param...` 名称映射到 Cubism 2 的 `PARAM_...` 名称，并选择对应的 Core setter；
- 点击动作控制器同时读取 Cubism 3/4 的 `File` 与 Cubism 2 的 `file`，但只在画布内部选择动作。

Pixi、Live2D 与 Cubism SDK 的 class 实例由画布组件直接拥有，不进入 Vue 深度响应式系统。`Application` 和 `Live2DModel` 使用 `shallowRef` 保存，因此 `stage`、`internalModel`、`coreModel` 和 `motionManager` 都保持原始实例。Pinia 只保存可序列化的用户偏好、默认表情和临时表情请求，不保存动作定义或当前动作。

`modelParameters` 延续已有语义：模型载入后应用一次，用户修改配置时再次应用。画布不会在每一帧把完整配置写回 Core，也不建立参数锁定层，以免覆盖动作、眨眼、视线、呼吸和物理更新。

表情控制的数据流是：

```text
assistant text
  -> extractLive2dExpression()
  -> live2dStore.requestExpression(name)
  -> Live2DCanvas.applyExpression()
```

这里的长期约束是：聊天文本仍然是主链路，Live2D 只是旁路消费者。

## 资源生命周期

### 安装阶段

管理员把原始模型目录直接复制到 `data/live2d/models/`。直接子目录名就是模型 ID 和默认展示名称；模型内部可继续使用 `runtime/` 等原始层级。

后端不接收 ZIP，也不生成 `live2d-xxxxxxxx` 目录或 `metadata.json`。复制过程不要求原子发布：暂时不完整的目录在扫描时被跳过并记录 `WARNING`，复制完成后由下一次列表请求发现。

### 默认模型阶段

默认模型使用 `config/live2d_config.yaml` 的 `default_model` 指定。配置值与某个有效直接子目录名完全匹配时，API 才为该模型返回 `is_default=true`。

默认目录缺失或无效时只记录 `WARNING`；后端不会自动选择列表第一项，也不会从 AIRI ZIP 缓存自动导入模型。

### 删除阶段

删除模型由管理员直接删除服务器目录完成。下一次 `GET /api/live2d/models` 不再返回该模型。

前端若本地选择已失效，回退到有效的后端默认模型；若默认模型也不存在，则清空当前模型并停止渲染，不回退到列表第一项或过期 URL。

## 前端舞台生命周期

首页 `index.vue` 当前通过 `live2dStore.enabled` 切换普通聊天模式和舞台模式。

舞台模式下：

- `StageHeader` 负责顶部操作；
- `Live2DCanvas` 负责渲染和交互；
- `StageChatShell` 负责聊天浮层。

长期约束：

- 切换舞台模式不改变聊天协议；
- 只改变页面布局和 Live2D 可见性；
- 聊天状态、WebSocket 连接和音频播放器都继续复用同一套全局运行时。

## 表情与动作边界

### 表情

当前表情系统的稳定事实是：

1. 后端只提供“表情名称列表”。
2. 前端通过“默认表情”下拉框保存一个默认表情，也可选择不叠加命名 expression 的“模型默认表情”。
3. 聊天消息可通过 `[expression:Name]` 标签触发表情。
4. “表情系统”开关可以暂停所有命名 expression；关闭时模型回到基础状态，但原生动作、眨眼和其他运行时能力继续工作。

下拉选择会立即保存并预览。聊天标签触发的是临时表情，不会覆盖保存的默认值。设置页不提供与单选下拉框重复的“恢复默认表情”按钮。“向 LLM 暴露”的 `None / All / Custom` 及其自定义列表只是既有本地偏好，当前未接入后端 LLM 工具。

它不是：

- 参数级 expression mixer；
- 服务端工具调用；
- 多表情叠加系统。

### 动作

普通用户不选择动作，前端也不持久化动作清单、动作文件路径或当前动作。模型原生 Idle 由 `pixi-live2d-display` 的 `motionManager` 自动调度；画布不建立自己的 `motionFinish` 重播循环。

画布只在内部读取 `motionManager.definitions`，消费 `pixi-live2d-display` 的 `hit` 事件，并把命中区域映射到动作：先查找 `Tap@Body`、`TapBody`、`tap_body` 等语义组，再尝试空组，最后尝试非待机动作。内部选择兼容 Cubism 3/4 的 `File` 和 Cubism 2 的 `file`，同一文件只作为一个回退候选；运行时原始定义不被改写，空字符串仍是合法动作组。没有可用动作时安全忽略。

因此 Hiyori 的 Body 命中可以播放 `Tap@Body`，Katou 的 head/body 命中可以使用空组回退。动作定义和选择结果不会发布到 Pinia 或设置 UI，后端也不参与点击动作选择。

### 口型同步

当前仓库里能看到的是嘴型参数的手动控制，不是音频驱动的自动 lip-sync。

因此旧文档里关于口型同步的章节，当前只能算历史设计意图。

## 缓存设计

浏览器 `localStorage` 只保存舞台偏好和模型选择。模型设置文件、Moc、纹理、动作和表情资源直接通过后端 `model_url` 及其相对 URL 请求，复用浏览器标准 HTTP 缓存。

前端不维护自定义模型文件数据库、缓存清单、版本号或产品内清缓存入口。无论浏览器是否命中 HTTP 缓存，后端实时模型目录和 `GET /api/live2d/models` 始终是模型可用性的唯一权威来源。

## 与旧设计文档的取舍

旧 `Live-2d设计文档.md` 中这些内容现在已经不再能当作当前事实：

- 服务端 `set-model` 语义
- 文件列表接口
- LLM 工具接口 `expression_set/get/...`
- 表情混合模式
- 成熟口型同步

当前仍然成立并被迁移吸收的，是这些骨架：

- 模型资源通过后端静态文件边界提供给浏览器
- 前后端职责必须拆开
- 前端需要本地持久化舞台偏好
- 表情控制要能消费聊天链路里的控制信号

以下旧产品方向已明确废止：

- 前端 ZIP 上传
- 在线模型重命名
- 远程递归删除模型
- UUID 包装目录和 ATRI `metadata.json`

## 文档关系

- [storage-and-api.zh-CN.md](storage-and-api.zh-CN.md) 解释管理员目录、后端实时发现和只读 API 边界。
- [frontend-runtime.zh-CN.md](frontend-runtime.zh-CN.md) 解释统一舞台运行时、直接 URL 加载和浏览器本地状态。
- [expression-control.zh-CN.md](expression-control.zh-CN.md) 解释表情名称、标签和本地开关。
