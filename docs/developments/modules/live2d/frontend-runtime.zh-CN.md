---
status: active
owner: live2d
created: 2026-07-09
updated: 2026-07-13
source:
  - docs/developments/module-design/CN/Live-2d设计文档.md
related_code:
  - frontend/src/stores/live2d.ts
  - frontend/src/components/live2d/Live2DCanvas.vue
  - frontend/src/components/live2d/ModelSettingsPreviewStage.vue
  - frontend/src/components/live2d/runtime.ts
  - frontend/src/components/live2d/coreParameterAdapter.ts
  - frontend/src/components/live2d/motionController.ts
---

# Live2D 前端运行时边界

## 运行时所有权

当前 Live2D 的“正在使用哪个模型、放在哪里、默认使用哪个表情”由前端维护。核心可序列化状态集中在 `frontend/src/stores/live2d.ts`，第三方运行时实例和动作控制只由画布组件拥有。

### 本地持久化字段

`live2d` store 会把以下偏好写入 `localStorage` 键 `atri-live2d-settings`：

- `enabled`
- `activeModelId`
- `position`
- `scale`
- `disableFocus`
- `autoBlinkEnabled`
- `forceAutoBlinkEnabled`
- `shadowEnabled`
- `maxFps`
- `renderScale`
- `modelParameters`
- `savedExpressionDefaults`
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

前端通过 `pixi-live2d-display` 的双运行时入口同时支持：

- Cubism 2 `.model.json + .moc`；
- Cubism 3/4 `.model3.json + .moc3`。

页面本地加载 Cubism 2 `live2d.min.js` 和 Cubism 3/4
`live2dcubismcore.min.js`。运行库根据设置 JSON schema 自动选择对应 runtime，API
不需要增加模型版本字段。

`Live2DCanvas.vue` 的加载顺序是：

```text
activeModel.modelUrl
  -> Live2DModel.from(modelUrl)
  -> pixi-live2d-display 根据设置 JSON 选择 runtime
  -> 加入 Pixi stage
```

`modelUrl` 是模型目录 API 返回的后端绝对静态 URL。设置 JSON 中的 Moc、纹理、动作和表情相对路径继续由运行库从同一后端静态资源边界解析。前端不再复制、重组或二次托管模型文件。

模型资源复用浏览器标准 HTTP 缓存。应用不维护额外的模型文件缓存、版本参数、缓存清单或清缓存按钮；浏览器缓存不改变 `GET /api/live2d/models` 作为模型目录真相的地位。

Cubism 2 与 Cubism 3/4 的底层参数 API 和标准参数 ID 不同。
`coreParameterAdapter.ts` 把前端统一的 `Param...` 名称映射到 Cubism 2
`PARAM_...` 名称，并分别调用 `setParameterValueById()` 或 `setParamFloat()`，使眼球
跟随、眨眼、头部、眉毛、嘴型、身体和呼吸控制在两种 runtime 下都能工作。

模型文件加载是异步过程。每次 URL 变化或组件卸载都会使前一代加载失效；迟到的
模型实例必须立即销毁，不能重新加入 Pixi stage，也不能发送 `loaded` 或覆盖新一代
模型状态。

## 运行时对象所有权

Pixi、Live2D 与 Cubism SDK 的对象依赖 class identity、内部可变状态和原型方法，不能进入 Vue 深度响应式代理。`Live2DCanvas.vue` 只用浅层引用保存两个根实例：

```ts
const app = shallowRef<Application | null>(null)
const model = shallowRef<Live2DModel | null>(null)
```

由此派生的 `Application.stage`、`internalModel`、`coreModel`、`motionManager` 和其他 SDK 对象保持原始实例。它们不写入 Pinia、`reactive()` 或普通深层 `ref()`。Pinia 只保存 ID、数值、布尔值、默认表情等产品偏好，不保存动作定义或当前动作。

这一边界对 Cubism 2 尤其重要：它的 `ParamID` 使用对象身份定位参数，深度代理会破坏相同参数 ID 的稳定索引。Cubism 3/4 与 Cubism 2 均遵守同一所有权规则，而不是为旧格式维护第二套 Canvas。

## 渲染与交互控制

`Live2DCanvas.vue` 当前负责：

- 创建 Pixi `Application`；
- 注册 `TickerPlugin`、`InteractionManager`；
- 根据容器尺寸、`position`、`scale` 计算模型变换；
- 根据鼠标位置驱动 `ParamEyeBallX/Y`；
- 按开关启动/停止自定义眨眼循环；
- 在加载后或配置变化时应用 `modelParameters`；
- 让模型运行库自动调度原生 Idle；
- 把模型命中事件映射为内部点击动作；
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

`modelParameters` 不会在每个渲染帧完整写回 Core，也没有稀疏参数锁定层。这样动作、眨眼、鼠标跟随、呼吸、物理和模型自身的自然运动仍可在后续帧更新对应参数。

## 动作运行时

动作不是普通用户配置。当前边界是：

- 模型原生 Idle 由 `pixi-live2d-display` 的 `motionManager` 自动启动和续接；
- store 不保存 `availableMotions`、`currentMotion`、`selectedRuntimeMotionPath` 或 Idle 开关；
- 设置页不展示手动动作选择器；
- 画布不向 store 发布动作清单，也不注册自建 `motionFinish` 重播循环；
- 后端不保存动作状态，也不提供动作播放 API。

`Live2DCanvas` 只为点击交互读取 `model.internalModel.motionManager.definitions`。该读取是画布内部实现细节，不会把动作定义变成用户偏好。

## 点击动作

Hiyori 与 Katou 共用同一套 `hit → motion` 控制逻辑。`pixi-live2d-display` 完成 `pointertap`、命中测试并发出 `hit` 事件后，画布按以下顺序选择动作：

1. 命中区域对应的语义组，例如 Body 对应 `Tap@Body`、`TapBody`、`tap_body`；
2. 空字符串动作组；
3. 非待机动作组；
4. 没有可用动作时安全忽略。

内部选择器兼容 Cubism 3/4 的 `File` 与 Cubism 2 的 `file`。在最终的非待机回退集合中，同一路径只作为一个候选，且优先保留具名组；它不会改写运行时原始定义。

因此 Hiyori 的 Body 命中优先播放 `Tap@Body`，Katou 的 head/body 命中可回退到空组。点击动作以 `MotionPriority.FORCE` 启动，不会随机切换表情。动作完成后的 Idle 恢复继续由模型运行库负责。模型被替换或组件卸载时，旧模型的 `hit` 监听器会解除。

## 与表情和消息的边界

运行时只消费一个非常轻量的表情请求对象：

```ts
{
  name: string | null
  token: number
}
```

`token` 用于在“同一表情名再次触发”时强制重新应用。这个请求可以来自：

- 设置页“默认表情”下拉框；
- 聊天消息里的 `[expression:...]` 标签；
- 载入聊天历史时恢复的最后一个助手表情；

都属于前端逻辑，不属于后端 Live2D API。

保存的 `savedExpressionDefaults` 与临时的 `expressionRequest` 是两层状态：选择下拉项会立即保存并预览；聊天标签和历史恢复只发出临时请求，不覆盖保存值。“模型默认表情”使用空保存值并请求 SDK 回到不叠加命名 expression 的模型基础状态。设置页不提供与单选下拉框重复的恢复按钮。

`expressionEnabled` 是命名 expression 的总开关。设置页必须通过 store 的 `setExpressionEnabled()` 更新它，使 `expressionRequest` 与开关状态同步。关闭时，Canvas 调用 `motionManager.expressionManager.resetExpression()`，而不是不存在的 `motionManager.resetExpression()`；这只清除命名 expression 对画面的影响，不销毁 SDK expression manager，也不停止原生动作和眨眼。

SDK 的 `resetExpression()` 不会清空其 `currentExpression` 指针。重新开启后，如果请求名仍与该指针对应的表情相同，直接再次调用 `model.expression(name)` 会被 SDK 判定为重复请求。Canvas 在这种情况下调用公开的 `restoreExpression()` 恢复该表情，不额外维护一份运行时状态。

`expressionLlmMode`、`expressionLlmExposed` 以及设置页 `None / All / Custom` 仍是既有本地偏好。它们尚未接入后端 LLM 工具，本次运行时重构不扩展该能力。

## 当前明确不由后端负责的内容

后端目前不维护以下运行时信息：

- `activeModelId`
- `position`
- `scale`
- `renderScale`
- `maxFps`
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
