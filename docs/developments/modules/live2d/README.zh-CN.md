---
status: active
owner: live2d
created: 2026-07-09
updated: 2026-07-12
related_code:
  - src/routes/live2d.py
  - src/storage/live2d_storage.py
  - frontend/src/components/live2d/
  - frontend/src/stores/live2d.ts
---

# Live2D 模块长期设计

本目录沉淀当前仓库里 Live2D 的长期模块文档。这里的重点不是泛化 Live2D 理论，而是说明本仓库已经实现了哪些后端存储/API 能力，以及哪些运行时状态明确属于前端。

## 当前文档

| 文档 | 内容 |
| --- | --- |
| [design.zh-CN.md](design.zh-CN.md) | Live2D 模块总设计，串起管理员目录投放、只读模型目录、前端舞台运行时和表情控制边界。 |
| [storage-and-api.zh-CN.md](storage-and-api.zh-CN.md) | 后端模型目录实时扫描、结构校验、默认模型配置、静态资源挂载和只读 REST 边界。 |
| [frontend-runtime.zh-CN.md](frontend-runtime.zh-CN.md) | 前端 `live2d` store、Pixi/`pixi-live2d-display` 运行时、OPFS 缓存和本地持久化边界。 |
| [expression-control.zh-CN.md](expression-control.zh-CN.md) | 当前表情名称来源、前端切换逻辑、消息标签解析和未接通的 LLM 工具边界。 |

## 阅读顺序

1. 先读 [storage-and-api.zh-CN.md](storage-and-api.zh-CN.md)，确认后端到底维护什么。
2. 再读 [design.zh-CN.md](design.zh-CN.md)，确认整体职责划分和当前真实能力边界。
3. 再读 [frontend-runtime.zh-CN.md](frontend-runtime.zh-CN.md)，确认“当前模型、位置、动作、缓存”都在哪里。
4. 最后读 [expression-control.zh-CN.md](expression-control.zh-CN.md)，确认表情系统目前是标签驱动和本地 UI 驱动，而不是后端工具系统。

## 文档关系

- 旧文档 [../../module-design/CN/Live-2d设计文档.md](../../module-design/CN/Live-2d设计文档.md) 仍保留为历史来源。
- 旧文档中关于“后端 set-model API、文件列表 API、成熟 LLM 表情工具、口型同步链路”的描述不再代表当前实现。
- 当前事实以 `src/routes/live2d.py`、`src/storage/live2d_storage.py`、`frontend/src/stores/live2d.ts` 和 `frontend/src/components/live2d/` 为准。

## 收录规则

这里记录跨版本仍应成立的后端/前端职责划分、静态资源边界和运行时状态所有权。设计草案、第三方 AIRI 参考实现细节和未落地能力不在本目录复刻。
