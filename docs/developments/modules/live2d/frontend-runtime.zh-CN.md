---
status: active
owner: live2d
created: 2026-07-09
updated: 2026-07-12
source:
  - docs/developments/module-design/CN/Live-2d设计文档.md
related_code:
  - frontend/src/stores/live2d.ts
  - frontend/src/components/live2d/Live2DCanvas.vue
  - frontend/src/components/live2d/ModelSettingsPreviewStage.vue
  - frontend/src/components/live2d/runtime.ts
  - frontend/src/utils/live2dOpfs.ts
---

# Live2D 前端运行时边界

## 运行时所有权

当前 Live2D 的“正在使用哪个模型、放在哪里、播哪个动作、缓存到哪里”全部由前端维护。核心状态集中在 `frontend/src/stores/live2d.ts`。

### 本地持久化字段

`live2d` store 会把以下偏好写入 `localStorage` 键 `atri-live2d-settings`：

- `enabled`
- `activeModelId`
- `position`
- `scale`
- `disableFocus`
- `idleAnimationEnabled`
- `autoBlinkEnabled`
- `forceAutoBlinkEnabled`
- `shadowEnabled`
- `maxFps`
- `renderScale`
- `modelParameters`
- `savedExpressionDefaults`
- `selectedRuntimeMotionPath`
- `currentMotion`
- `expressionEnabled`
- `expressionLlmMode`
- `expressionLlmExposed`

这些都不会回写到后端。

## 模型列表与当前模型

前端通过 `live2dApi.list()` 调用 `GET /api/live2d/models`，再把响应映射为本地 `Live2DModel`。

当前模型的归属规则：

- 以 `activeModelId` 为主；
- 如果本地记录的模型不存在，则优先回退到 `isDefault=true` 的模型；
- 若后端没有有效默认模型，则把 `activeModelId` 置为 `null`；
- 管理员从服务器移除当前模型后，前端在下一次获取列表时重新执行同一套回退逻辑；
- 不使用列表第一项作为隐式默认值，也不继续加载失效模型的旧 URL。

模型列表请求失败和“成功返回但模型已不存在”是两种不同状态：

- 请求失败时，前端清空当前可渲染目录，停止使用旧 URL，但保留尚未被有效目录
  判定失效的本地 `activeModelId`；
- 只有成功取得目录后，才能把不存在的本地 ID 回退到后端默认模型或 `null`。

这说明“当前模型”是浏览器本地语义，不是服务器全局语义。

`enabled` 仍是独立的浏览器偏好。后端默认模型只提供选择回退，不会在首次访问时强制开启 Live2D。

## 加载链路

`Live2DCanvas.vue` 的加载顺序是：

```text
activeModel.modelUrl
  -> resolvedModelUrl（可附加 cache bust 参数）
  -> 优先尝试 OPFS 本地缓存
  -> 回退到网络加载
  -> Live2DModel.from(...)
  -> 加入 Pixi stage
```

当同时拿到 `modelId` 和 `modelPath` 时，前端会调用 `loadLive2dFilesWithOpfs()`：

1. 读取设置文件；
2. 解析 `FileReferences` 下的相关资源；
3. 下载并写入 OPFS；
4. 通过 `FileLoader.createSettings()/upload()` 组装本地文件集；
5. 再交给 `Live2DModel.from(settings)`。

如果 OPFS 失败，会自动回退到网络模式。

模型文件加载是异步过程。每次 URL 变化或组件卸载都会使前一代加载失效；迟到的
模型实例必须立即销毁，不能重新加入 Pixi stage，也不能发送 `loaded` 或覆盖新一代
模型状态。

## OPFS 缓存边界

`frontend/src/utils/live2dOpfs.ts` 维护浏览器侧缓存目录：

```text
atri-live2d-opfs
```

缓存键由：

- `modelId`
- `settingsUrl`

共同决定。缓存元数据只记录 `sourceUrl`，不会把后端运行状态写回服务器。

`clearModelCache()` 会：

- 清空 OPFS 根目录；
- 更新 `modelCacheVersion`；
- 让后续 `resolvedModelUrl` 带上新的 `_live2d` 查询参数。

## 渲染与交互控制

`Live2DCanvas.vue` 当前负责：

- 创建 Pixi `Application`；
- 注册 `TickerPlugin`、`InteractionManager`；
- 根据容器尺寸、`position`、`scale` 计算模型变换；
- 根据鼠标位置驱动 `ParamEyeBallX/Y`；
- 按开关启动/停止自定义眨眼循环；
- 应用 `modelParameters` 里的手动参数覆盖；
- 根据 `currentMotion` 播放动作；
- 根据 `expressionRequest` 应用表情。

其中 `modelParameters` 已经包含多组手动覆盖值，如：

- 头部角度
- 眼睛开合
- 眉毛参数
- `mouthOpen`
- `mouthForm`
- 身体角度
- 呼吸参数

这些都是前端直接写 core model 参数，不经过后端。

## 动作运行时

动作运行时的关键事实：

- 可用动作从 `model.internalModel.motionManager.definitions` 动态提取；
- `motionsLoaded` 事件把动作清单回写到 store；
- `selectedRuntimeMotionPath` 记录用户选择；
- `currentMotion` 保存 `group + index`；
- 选中动作后会把 `_looper.loopDuration = 0`，并在 `motionFinish` 时按需重播。

后端目前不知道“当前用户选中了哪个动作”。

## 与表情和消息的边界

运行时只消费一个非常轻量的表情请求对象：

```ts
{
  name: string | null
  token: number
}
```

`token` 用于在“同一表情名再次触发”时强制重新应用。至于这个请求来自哪里：

- 手动设置页；
- 聊天消息里的 `[expression:...]` 标签；
- 载入聊天历史时恢复的最后一个助手表情；

都属于前端逻辑，不属于后端 Live2D API。

## 当前明确不由后端负责的内容

后端目前不维护以下运行时信息：

- `activeModelId`
- `position`
- `scale`
- `renderScale`
- `maxFps`
- `currentMotion`
- OPFS 缓存
- 表情开关和本地默认值

因此不能把这些状态写成“服务端 Live2D 会话状态”。

## 口型同步边界

当前前端确实暴露了 `mouthOpen`、`mouthForm` 手动参数，但这不等于已经有成熟的 TTS 音频驱动口型同步。

当前事实是：

- `ParamMouthOpenY` / `ParamMouthForm` 可以由设置面板手动调；
- 没有看到后端音频振幅驱动或 TTS 播放时序驱动接入 `Live2DCanvas.vue`；
- 不应把现状写成“已完成 lip-sync”。

## 文档关系

- 旧文档把大量 AIRI 参考实现细节和未来扩展都写进了主说明；本页只保留本仓库当前前端运行时事实。
- 表情标签解析和未接通的 LLM 工具边界见 [expression-control.zh-CN.md](expression-control.zh-CN.md)。
