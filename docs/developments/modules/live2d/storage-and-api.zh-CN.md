---
status: active
owner: live2d
created: 2026-07-09
updated: 2026-07-09
source:
  - docs/developments/module-design/CN/Live-2d设计文档.md
related_code:
  - src/app.py
  - src/routes/live2d.py
  - src/storage/live2d_storage.py
  - src/models/live2d.py
---

# Live2D 存储与 API 边界

## 后端职责

当前后端只负责两类事情：

1. 管理 Live2D 模型 ZIP 的落盘、校验、元数据维护和删除。
2. 把落盘后的模型文件作为静态资源暴露给前端渲染。

后端**不**负责：

- 记录哪个模型是当前前端正在使用的 active model；
- 保存前端的模型位置、缩放、动作、表情选择和缓存状态；
- 提供表情切换、动作播放或口型同步 API。

## 存储布局

默认根目录：

```text
data/live2d/models/
```

每个模型目录形如：

```text
data/live2d/models/live2d-xxxxxxxx/
  metadata.json
  <模型原始解压文件>
```

`metadata.json` 当前持久化：

- `id`
- `name`
- `model_path`
- `thumbnail_path`
- `expressions`
- `created_at`
- `is_default`

## 默认模型导入

`Live2DStorage.ensure_default_model()` 会在以下条件同时满足时，尝试从 AIRI 缓存导入默认 Hiyori 模型：

- 使用默认模型目录；
- 该目录下还没有任何模型；
- `airi/.cache/live2d/models/hiyori_free_zh.zip` 存在。

这是“尽力导入”行为，不是强依赖。找不到缓存压缩包时，后端仍可正常工作，只是没有默认模型。

## 上传与解压规则

### 接受的上传

- 文件扩展名必须是 `.zip`；
- Content-Type 允许：
  - `application/zip`
  - `application/x-zip-compressed`
  - `application/octet-stream`

### 解压安全

上传后端会：

- 统一路径分隔符；
- 拒绝空路径；
- 拒绝跳出目标目录的危险路径；
- 仅在模型目录内部落盘。

### 结构校验

当前只要求压缩包里至少存在一个：

- `.model3.json`
- 或 `.model.json`

系统会选择“目录层级更浅、路径更短”的设置文件作为 `model_path`。

### 预览图和表情名

上传后端会：

- 优先寻找 `preview.png` 作为缩略图；
- 若没有 `preview.png`，退化为第一个图片文件；
- 从设置文件里的 `FileReferences.Expressions` 或 `expressions` 数组抽取表情名称；
- 只保存**表情名称列表**，不解析 `exp3.json` 参数细节。

这意味着后端目前知道“有哪些表情名”，但不知道“每个表情具体改了哪些参数”。

## 静态资源暴露

`src/app.py` 会把默认模型目录挂载到：

```text
/api/assets/live2d
```

`Live2DStorage.build_asset_url(relative_path, base_url)` 会生成绝对资源 URL，供 API 返回给前端：

- `model_url`
- `thumbnail_url`

前端后续通过这些 URL 加载 `.model3.json` 和相关纹理、动作、表情文件。

## REST API

当前公开的管理接口前缀是：

```text
/api/live2d/models
```

### 已有接口

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/api/live2d/models` | 返回所有模型摘要列表。 |
| `POST` | `/api/live2d/models` | 上传并解压一个模型 ZIP。 |
| `GET` | `/api/live2d/models/{model_id}/expressions` | 返回该模型的表情名称列表。 |
| `PUT` | `/api/live2d/models/{model_id}` | 只更新模型名称。 |
| `DELETE` | `/api/live2d/models/{model_id}` | 删除模型目录。 |

### 摘要字段

模型摘要 `Live2DModelSummary` 当前包含：

- `id`
- `name`
- `model_path`
- `model_url`
- `thumbnail_url`
- `expressions`
- `created_at`
- `is_default`

这里没有：

- `is_current`
- `position`
- `scale`
- `motion`

因为这些都不是后端持久化状态。

## 默认模型语义

当前 `is_default` 只是“后端模型列表里的默认项”：

- 第一个保存成功的模型会成为默认模型；
- 删除默认模型后，若还有剩余模型，会把排序后的第一个剩余模型标记为默认。

它不等于“某个浏览器标签页正在使用的当前模型”。

## 当前明确没有的接口

以下能力在旧文档中出现过，但当前代码没有：

- `POST /api/live2d/set-model`
- `GET /api/live2d/models/{id}/files`
- 服务器端“设为当前模型”状态
- 表情切换、动作播放、口型同步或工具调用 API

因此任何涉及 active model、动作或表情运行时切换的行为，都应在前端文档中说明，而不是归到本页。

## 文档关系

- 旧 Live2D 设计文档把后端和前端职责写得更满；当前实现已收敛为“后端 CRUD + 静态资源”。
- 本页不讨论前端 Pixi 运行时、OPFS 缓存和表情标签逻辑，那些内容见本目录另外两篇文档。
