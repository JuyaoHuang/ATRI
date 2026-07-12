---
status: active
owner: live2d
created: 2026-07-09
updated: 2026-07-12
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

1. 在每次读取模型列表时，扫描并校验管理员已放入模型根目录的 Live2D 模型文件夹。
2. 通过只读 API 返回动态派生的模型摘要，并把模型文件作为静态资源暴露给前端渲染。

后端**不**负责：

- 接收、解压或保存前端上传的模型；
- 通过 HTTP 重命名或删除模型目录；
- 记录哪个模型是当前前端正在使用的 active model；
- 保存前端的模型位置、缩放、动作、表情选择和缓存状态；
- 提供表情切换、动作播放或口型同步 API。

## 存储布局

默认根目录：

```text
data/live2d/models/
```

模型根目录的每个**直接子目录**代表一个模型，例如：

```text
data/live2d/models/
├── hiyori_free_zh/
│   └── runtime/
│       └── hiyori_free_t08.model3.json
└── mao_pro/
    └── runtime/
        └── mao_pro.model3.json
```

直接子目录名同时作为：

- API `id`；
- 默认展示名称 `name`；
- 静态资源 URL 的模型根路径。

模型可以保留发行包本来的内部层级，例如 `runtime/`。ATRI 不再要求、生成或读取：

- `live2d-xxxxxxxx` UUID 包装目录；
- `metadata.json`；
- 上传时间或 `created_at` 元数据。

## 管理员安装与删除

管理员通过服务器文件系统管理模型：

1. 把原始模型文件夹直接复制到 `data/live2d/models/<模型名>/`；
2. 刷新前端，或再次请求 `GET /api/live2d/models`；
3. 后端重新扫描目录，验证通过后返回该模型。

删除模型同样由管理员直接删除对应文件夹完成。后端不提供上传、重命名或删除模型的 HTTP API。

管理员可以直接复制到最终目录，不要求暂存目录或原子重命名。复制期间出现的暂时不完整目录会被跳过并记录 `WARNING`；复制完成后，下一次列表请求即可发现它。

例如，把 Open-LLM-VTuber 的 `mao_pro` 原始目录复制为：

```text
data/live2d/models/mao_pro/
└── runtime/
    └── mao_pro.model3.json
```

不需要修改目录名，也不需要补写 `metadata.json`。使用 `docker-compose.prod.yml` 时，宿主机 `./data` 已挂载到容器 `/app/data`，因此管理员同样直接维护宿主机的 `./data/live2d/models/`。

## 实时发现与校验

### 扫描时机

`GET /api/live2d/models` 每次都直接扫描模型根目录，不建立：

- 启动时索引；
- TTL 缓存；
- 文件系统 watcher；
- 数据库或中央 `index.json`。

目标规模为 5 到 10 个模型。扫描只读取目录项和设置 JSON，不读取 `.moc3`、纹理图片等大型二进制内容。

### 设置文件选择

后端在每个直接子目录内递归寻找 `.model3.json`。当前前端只加载
`pixi-live2d-display/cubism4`，并只随页面提供 Cubism 3/4 Core，因此 Cubism 2
的 `.model.json` 不会被目录列为可选模型，避免出现“后端判定有效但浏览器必然
无法渲染”的条目。

若存在多个候选项，按以下顺序确定性选择，并记录 `WARNING`：

1. 相对路径层级更浅；
2. 相对路径字符串更短；
3. 规范化后的相对路径按字典序更靠前。

### 最低有效性边界

一个模型必须满足：

1. 模型目录是模型根目录下的普通直接子目录，而不是符号链接；
2. 设置文件可以解析为 JSON；
3. `FileReferences.Moc` 是非空相对路径，目标文件存在且仍位于该模型目录内；
4. `FileReferences.Textures` 是非空列表，每个纹理文件存在且仍位于该模型目录内；
5. 所有用于 API URL 输出的路径都不能越出该模型目录。

任一模型校验失败时，后端会记录包含目录和原因的 Loguru `WARNING`，跳过该模型，并继续返回其他有效模型。扫描期间文件被删除也按同一规则处理，不把整个列表请求变成 500。

### 缩略图和表情名

后端动态派生：

- 优先选择名为 `preview.png` 的文件作为缩略图；
- 没有 `preview.png` 时，选择确定排序后的第一个 `.png`、`.jpg`、`.jpeg` 或 `.webp`；
- 从设置 JSON 的 `FileReferences.Expressions`（兼容旧版 `expressions`）提取表情名称；
- 只返回表情名称，不解析 `exp3.json` 参数细节。

可选表情文件缺失时会记录诊断日志，但不会否定已经满足 Moc 和纹理最低加载条件的模型。

### 模型 ID 边界

模型 ID 只能来自模型根目录枚举得到的直接子目录名。按 ID 读取表情时会拒绝空值、`.`、`..`、斜杠、反斜杠、绝对路径、盘符路径和控制字符，并再次确认解析后的目录仍是模型根目录的直接子目录。

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

当前公开的只读接口前缀是：

```text
/api/live2d/models
```

### 保留接口

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/api/live2d/models` | 实时扫描并返回所有有效模型摘要。 |
| `GET` | `/api/live2d/models/{model_id}/expressions` | 重新校验指定模型并返回表情名称列表。 |
| `GET` | `/api/assets/live2d/{path}` | 返回已安装模型的静态资源。 |

以下管理接口已删除：

- `POST /api/live2d/models`；
- `PUT /api/live2d/models/{model_id}`；
- `DELETE /api/live2d/models/{model_id}`。

即使绕过前端直接发起 HTTP 请求，也不能通过 Live2D API 修改服务器文件系统。

### 摘要字段

模型摘要 `Live2DModelSummary` 当前包含：

- `id`
- `name`
- `model_path`
- `model_url`
- `thumbnail_url`
- `expressions`
- `is_default`

这里没有：

- `is_current`
- `position`
- `scale`
- `motion`

因为这些都不是后端持久化状态。

## 默认模型语义

默认模型由后端统一配置：

```yaml
# config/live2d_config.yaml
default_model: hiyori_free_zh
```

- 配置值精确匹配某个有效直接子目录名时，该模型返回 `is_default=true`；
- 配置为空时，不标记默认模型；
- 配置指向缺失或无效目录时，记录 `WARNING`，且不把列表第一项静默标记为默认模型。

它不等于“某个浏览器标签页正在使用的当前模型”。

## 当前明确没有的接口

以下能力在旧文档中出现过，但当前代码没有：

- `POST /api/live2d/set-model`
- `GET /api/live2d/models/{id}/files`
- 服务器端“设为当前模型”状态
- 表情切换、动作播放、口型同步或工具调用 API
- 模型上传、在线重命名和远程删除 API

因此任何涉及 active model、动作或表情运行时切换的行为，都应在前端文档中说明，而不是归到本页。

## 文档关系

- 旧 Live2D 设计文档把后端和前端职责写得更满；当前实现已收敛为“管理员文件系统维护 + 后端只读目录 + 静态资源”。
- 本页不讨论前端 Pixi 运行时、OPFS 缓存和表情标签逻辑，那些内容见本目录另外两篇文档。
