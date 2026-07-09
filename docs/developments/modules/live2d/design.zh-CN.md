---
status: active
owner: live2d
created: 2026-07-09
updated: 2026-07-09
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

当前 Live2D 不是一个“服务端驱动角色引擎”，而是一个分裂但边界清晰的双端模块：

- 后端负责模型资源管理和静态资源暴露；
- 前端负责模型选择、渲染、动作、表情和本地缓存。

这意味着 Live2D 在系统中的位置更接近：

```text
后端：模型资源仓库 + CRUD API + 静态文件服务
前端：舞台运行时 + 用户偏好 + 消息驱动表情
```

## 设计目标

结合旧设计文档、当前代码和近期 git log，当前长期目标可以概括为 4 条：

1. 把 Live2D 资源管理和舞台运行时明确拆开。
2. 让前端可以在不依赖服务端会话状态的情况下独立管理当前模型与舞台参数。
3. 保持后端模型上传、校验和资源 URL 输出稳定，便于前端长期缓存。
4. 对表情和动作保持“名称级控制”，不把未落地的参数级工具系统写成事实。

## 模块组成

当前 Live2D 模块可以稳定拆成三块：

| 子系统 | 代码 | 职责 |
| --- | --- | --- |
| 后端存储与 API | `src/storage/live2d_storage.py` `src/routes/live2d.py` | 模型 ZIP 上传、结构校验、元数据持久化、资源 URL 输出 |
| 前端舞台运行时 | `frontend/src/stores/live2d.ts` `frontend/src/components/live2d/Live2DCanvas.vue` | 当前模型、位置、缩放、动作、表情、OPFS 缓存 |
| 消息驱动表情 | `frontend/src/utils/live2dExpression.ts` + `useWebSocket()` | 从聊天文本中解析 `[expression:...]` 并发出表情请求 |

## 前后端职责划分

### 后端拥有的真相

后端当前拥有这些持久化事实：

- 有哪些模型
- 每个模型的名称
- 设置文件路径
- 缩略图路径
- 表情名称列表
- 是否为默认模型

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

## 数据流

当前 Live2D 的稳定数据流是：

```text
ZIP upload
  -> Live2DStorage.save_model()
  -> metadata.json + extracted files
  -> GET /api/live2d/models
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

### 上传阶段

`Live2DStorage.save_model()` 当前会：

1. 验证扩展名和 Content-Type。
2. 解压 ZIP。
3. 拒绝危险路径。
4. 选择最浅层、最短路径的 `.model3.json` / `.model.json`。
5. 解析表情名称和缩略图。
6. 生成 `metadata.json`。

### 默认模型阶段

近期日志里有两次关键演化：

- `feat: add Live2D model management backend`
- `feat: add Hiyori model and update Live2D model management`

这两步确认了当前一个稳定事实：

- 默认 Hiyori 导入是“本地开发便利能力”，不是强依赖部署链路；
- 找不到 AIRI 缓存时，Live2D 后端仍然可以正常工作，只是没有默认模型。

### 删除阶段

删除模型时：

- 后端删除整个模型目录；
- 若删掉的是默认模型，会从剩余模型里重新选默认项；
- 前端若当前正使用该模型，需要自行回退到新的默认模型或第一项。

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
- 清缓存只影响前端加载路径，不影响模型元数据真相。

## 与旧设计文档的取舍

旧 `Live-2d设计文档.md` 中这些内容现在已经不再能当作当前事实：

- 服务端 `set-model` 语义
- 文件列表接口
- LLM 工具接口 `expression_set/get/...`
- 表情混合模式
- 成熟口型同步

当前仍然成立并被迁移吸收的，是这些骨架：

- 模型资源要走 ZIP 上传和静态文件暴露
- 前后端职责必须拆开
- 前端需要本地持久化舞台偏好
- 表情控制要能消费聊天链路里的控制信号

## 文档关系

- [storage-and-api.zh-CN.md](storage-and-api.zh-CN.md) 解释后端资源与 CRUD 边界。
- [frontend-runtime.zh-CN.md](frontend-runtime.zh-CN.md) 解释舞台运行时与 OPFS。
- [expression-control.zh-CN.md](expression-control.zh-CN.md) 解释表情名称、标签和本地开关。
