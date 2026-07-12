---
status: active
owner: live2d
created: 2026-07-09
updated: 2026-07-12
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

后端每次扫描管理员安装的模型目录时，会从 `.model3.json` / `.model.json` 的：

- `FileReferences.Expressions`
- 或 `expressions`

里动态提取表情**名称**，再通过：

- `GET /api/live2d/models`
- `GET /api/live2d/models/{model_id}/expressions`

返回给前端。

表情名称不写入 `metadata.json` 或其他 sidecar 文件；管理员修改模型目录后，下一次读取会重新派生结果。

当前后端只知道“有哪些表情名”，不知道 `exp3.json` 的参数混合细节，因此它不是表情计算引擎。

## 前端状态

前端 `live2d` store 当前维护：

- `expressionEnabled`
- `expressionRequest`
- `activeExpressions`
- `savedExpressionDefaults`
- `expressionLlmMode`
- `expressionLlmExposed`

其中真正驱动画布更新的是 `expressionRequest`。`activeExpressions` 在当前实现里实际上只允许单选：

- `toggleExpression(name)` 会把激活列表设置为 `[name]`；
- 再次点击同名表情会清空；
- `resetAllExpressions()` 恢复本地保存的默认单选结果。

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
| `live2d` store | `requestExpression(name)` 负责把名称规范化到当前模型已知表达式列表里。 |

因此当前“表情控制”和“聊天显示”已经有耦合点：标签会被用作控制信号，但不会直接展示给用户。

## 画布应用方式

`Live2DCanvas.vue` 的 `applyExpression()` 当前只有两种行为：

- 若系统关闭或没有表达式名，则调用 `motionManager.resetExpression()`；
- 否则调用 `model.value.expression(expressionName)`。

这说明当前实现是“按名称切换模型已有表情”，不是“前端自己重算每个参数值”。

## 本地 UI 开关的真实边界

设置面板里有：

- `向 LLM 暴露` 的 `all/none/custom`
- 自定义暴露列表 `expressionLlmExposed`

但当前 `Live2DSettings.vue` 已经明确写出：

```text
LLM 工具集成暂未接通。
```

也就是说：

- `expressionLlmMode`
- `expressionLlmExposed`

当前只是本地持久化 UI 偏好，并没有接到后端 prompt 注入、工具注册或服务端策略。

## 与旧文档的差异

旧 Live2D 设计文档曾描述：

- 一组完整的 `expression_set/get/toggle/save/reset` LLM 工具；
- 表情混合模式；
- 更接近 AIRI 的参数级表情控制。

这些都**不是**当前仓库已经实现的事实。当前仓库已经实现的是：

1. 后端从模型设置 JSON 动态返回表情名称列表；
2. 前端手动单选表情；
3. 前端从聊天文本里解析 `[expression:...]` 标签并切换表情。

## 与口型同步的边界

表情控制页里虽然也能改嘴型相关参数，但那属于 `modelParameters` 的手动覆盖，不是 TTS 驱动的自动 lip-sync。

因此不应把“表情切换”和“口型同步”混写成同一能力。

## 文档关系

- 后端只读模型目录和表情名称来源见 [storage-and-api.zh-CN.md](storage-and-api.zh-CN.md)。
- 前端画布、缓存和动作运行时见 [frontend-runtime.zh-CN.md](frontend-runtime.zh-CN.md)。
