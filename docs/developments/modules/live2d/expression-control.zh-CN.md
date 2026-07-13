---
status: active
owner: live2d
created: 2026-07-09
updated: 2026-07-13
source:
  - docs/developments/module-design/CN/Live-2d设计文档.md
related_code:
  - src/routes/live2d.py
  - src/storage/live2d_storage.py
  - frontend/src/stores/live2d.ts
  - frontend/src/components/live2d/Live2DCanvas.vue
  - frontend/src/composables/useWebSocket.ts
  - frontend/src/composables/useChat.ts
  - frontend/src/utils/live2dExpression.ts
---

# Live2D 表情控制边界

## 表情名来自哪里

后端每次扫描管理员安装的模型目录时，会从 Cubism 3/4 `.model3.json` 的：

- `FileReferences.Expressions`

或 Cubism 2 `.model.json` 的：

- `expressions`

里动态提取表情**名称**，再通过：

- `GET /api/live2d/models`
- `GET /api/live2d/models/{model_id}/expressions`

返回给前端。

表情名称不写入 `metadata.json` 或其他 sidecar 文件；管理员修改模型目录后，下一次读取会重新派生结果。

两种格式的表情文件字段分别兼容 `File` 和 `file`，前端通过统一的
`model.expression(name)` 接口切换，不为 Cubism 2 维护第二套表情状态。

当前后端只知道“有哪些表情名”，不知道 `exp3.json` 的参数混合细节，因此它不是表情计算引擎。

## 前端状态

前端 `live2d` store 当前维护：

- `expressionEnabled`
- `expressionRequest`
- `activeExpressions`
- `savedExpressionDefaults`
- `expressionLlmMode`
- `expressionLlmExposed`

其中真正驱动画布更新的是 `expressionRequest`：

- `savedExpressionDefaults` 只保存零个或一个默认表情名；空数组表示使用模型默认表情；
- `activeExpressions` 记录当前已请求的零个或一个表情，包括聊天标签产生的临时表情；
- `setDefaultExpression(name)` 先按当前模型的表情名称做大小写无关匹配，再保存规范名称并立即发出预览请求；
- `requestExpression(name)` 只改变当前临时状态，不会覆盖 `savedExpressionDefaults`。

切换模型时，store 会删除新模型不支持的默认表情、临时表情和自定义暴露项，避免把旧模型名称应用到新模型。

## 手动选择与默认值

`/settings/models` 的“表情系统”保留手动选择能力，但使用单选的“默认表情”下拉框，不再为每个表情提供一组独立选择按钮。

“表情系统”开关控制命名 expression 是否可以影响画布。开启时，默认表情和 AI 文本回复中的 `[expression:Name]` 标记可以切换模型表情；关闭时，画布通过 SDK 的 expression manager 回到不叠加命名 expression 的模型基础状态，同时保留模型原生动作、眨眼、呼吸、物理和鼠标互动。开关不会删除浏览器中保存的默认表情。

下拉框包含：

- “模型默认表情”：映射为 `savedExpressionDefaults=[]` 和 `expressionRequest.name=null`，由 SDK 回到不叠加命名 expression 的模型基础状态；
- 当前模型返回的每个表情名：保存规范名称，并立即应用到预览画布。

聊天消息中的 `[expression:Name]` 属于临时运行时状态。它可以暂时覆盖当前画布表情，但不会改写下拉框保存的默认值。设置页只使用“默认表情”单选下拉框修改并立即预览默认值，不提供语义重复的恢复按钮。

## 消息标签路径

当前仓库已经接通的“LLM 到 Live2D 表情”路径，不是工具调用，而是文本标签：

```text
[expression:Happy]
```

解析逻辑在 `frontend/src/utils/live2dExpression.ts`：

- 用正则提取 `expression`；
- 把标签从最终显示文本中剥离；
- 返回 `{ expression, content }`。

### 实际消费点

| 位置 | 行为 |
| --- | --- |
| `useWebSocket.ts` | 在 `chat:complete` 和 `chat:interrupted` 时解析标签，剥离显示文本，并请求切换表情。 |
| `useChat.ts` | 载入历史消息时再次解析标签，并恢复最后一条助手消息的表情。 |
| `live2d` store | `requestExpression(name)` 负责把名称规范化到当前模型已知表情列表里；它不会修改保存的默认表情。 |

因此当前“表情控制”和“聊天显示”已经有耦合点：标签会被用作控制信号，但不会直接展示给用户。

## 画布应用方式

`Live2DCanvas.vue` 的 `applyExpression()` 当前只有两种行为：

- 若系统关闭或没有表达式名，则调用 `motionManager.expressionManager.resetExpression()`；
- 若请求名仍是 SDK 记录的 `currentExpression`，则调用 `restoreExpression()`，用于在关闭后重新开启时恢复该表情；
- 否则调用 `model.value.expression(expressionName)`。

这说明当前实现是“按名称切换模型已有表情”，不是“前端自己重算每个参数值”。

## 本地 UI 开关的真实边界

设置面板保留既有的：

- `向 LLM 暴露` 的 `all/none/custom`
- 自定义暴露列表 `expressionLlmExposed`

但当前 `Live2DSettings.vue` 已经明确写出：

```text
LLM 工具集成暂未接通。
```

也就是说：

- `expressionLlmMode`
- `expressionLlmExposed`

当前只是本地持久化 UI 偏好，并没有接到后端 prompt 注入、工具注册或服务端策略。本次 Live2D 运行时重构不扩展这项功能，也不改变 `None / All / Custom` 的既有行为。

## 与旧文档的差异

旧 Live2D 设计文档曾描述：

- 一组完整的 `expression_set/get/toggle/save/reset` LLM 工具；
- 表情混合模式；
- 更接近 AIRI 的参数级表情控制。

这些都**不是**当前仓库已经实现的事实。当前仓库已经实现的是：

1. 后端从模型设置 JSON 动态返回表情名称列表；
2. 前端通过“默认表情”下拉框手动单选并持久化默认值；
3. 前端从聊天文本里解析 `[expression:...]` 标签并切换表情。

## 与口型同步的边界

表情控制页里虽然也能改嘴型相关参数，但那属于 `modelParameters` 的手动覆盖，不是 TTS 驱动的自动 lip-sync。

这些参数只在模型加载完成后和用户修改配置时应用，不会在每个渲染帧硬写回 Core。该语义允许动作、呼吸、物理和模型自身的自然更新继续生效。

因此不应把“表情切换”和“口型同步”混写成同一能力。

## 文档关系

- 后端只读模型目录和表情名称来源见 [storage-and-api.zh-CN.md](storage-and-api.zh-CN.md)。
- 前端画布、直接 URL 加载和自动点击动作见 [frontend-runtime.zh-CN.md](frontend-runtime.zh-CN.md)。
