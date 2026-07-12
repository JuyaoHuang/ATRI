---
status: active
owner: live2d
created: 2026-07-09
updated: 2026-07-12
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
  - frontend/src/utils/live2dOpfs.ts
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
- 前端负责模型选择、渲染、动作、表情和本地缓存。

这意味着 Live2D 在系统中的位置更接近：

```text
管理员：data/live2d/models/ 目录维护
后端：实时模型目录 + 只读 API + 静态文件服务
前端：模型选择/关闭 + 舞台运行时 + 用户偏好 + 消息驱动表情
```

## 设计目标

结合旧设计文档、当前代码和近期 git log，当前长期目标可以概括为 4 条：

1. 把服务器模型安装和普通前端用户的舞台运行时明确拆开。
2. 让前端可以在不依赖服务端会话状态的情况下独立管理当前模型与舞台参数。
3. 让标准 Live2D 模型目录无需 ZIP、UUID 包装层或 ATRI `metadata.json` 即可被发现。
4. 对表情和动作保持“名称级控制”，不把未落地的参数级工具系统写成事实。

## 模块组成

当前 Live2D 模块可以稳定拆成三块：

| 子系统 | 代码 | 职责 |
| --- | --- | --- |
| 后端目录与 API | `src/storage/live2d_storage.py` `src/routes/live2d.py` | 直接子目录实时扫描、最低加载校验、默认模型标记、资源 URL 输出 |
| 前端舞台运行时 | `frontend/src/stores/live2d.ts` `frontend/src/components/live2d/Live2DCanvas.vue` | 当前模型、位置、缩放、动作、表情、OPFS 缓存 |
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
- 当前动作
- 当前表情请求
- OPFS 缓存状态
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
  -> Live2DStorage validates settings JSON + Moc + textures
  -> invalid/incomplete directories are warned and skipped
  -> valid model summaries + static asset URLs
  -> frontend live2d store maps model summaries
  -> Live2DCanvas loads model_url
  -> optional OPFS cache
  -> Pixi runtime renders model
```

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
2. 前端手动单选表情。
3. 聊天消息可通过 `[expression:Name]` 标签触发表情。

它不是：

- 参数级 expression mixer；
- 服务端工具调用；
- 多表情叠加系统。

### 动作

动作由前端从 `motionManager.definitions` 动态抽取并管理。后端并不知道“当前用户选择了哪个动作”。

### 口型同步

当前仓库里能看到的是嘴型参数的手动控制，不是音频驱动的自动 lip-sync。

因此旧文档里关于口型同步的章节，当前只能算历史设计意图。

## 缓存设计

当前缓存分两层：

1. 浏览器 `localStorage`
   - 保存舞台偏好和模型选择。
2. OPFS
   - 缓存模型文件和相关静态资源。

长期约束：

- 这两层缓存都属于浏览器本地；
- 不回写服务端；
- 清缓存只影响前端加载路径，不影响后端模型目录真相。

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
- [frontend-runtime.zh-CN.md](frontend-runtime.zh-CN.md) 解释舞台运行时与 OPFS。
- [expression-control.zh-CN.md](expression-control.zh-CN.md) 解释表情名称、标签和本地开关。
