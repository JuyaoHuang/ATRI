---
status: superseded
owner: docs
created: 2026-07-09
updated: 2026-07-09
---

# 旧模块设计文档说明

本目录保留的是早期长篇设计稿与讨论稿。它们现在的定位是：

- 历史设计来源
- 迁移参考材料
- 尚未完全清理前的旧入口

它们**不是**当前实现的正式权威入口。

## 当前权威入口

请优先阅读这些目录：

| 类型 | 目录 |
| --- | --- |
| 长期模块设计 | `../modules/` |
| 稳定接口协议 | `../api/` |
| 项目级架构 | `../architecture/` |
| 功能开发过程 | `../features/` |
| Wiki 预发布稿 | `../wiki/` |

## 使用原则

阅读本目录中的旧稿时，应按以下原则处理：

1. 先以当前代码为准。
2. 再以 `docs/developments/modules/` 中对应模块文档为准。
3. 仅把本目录内容当作历史设计意图、备选方案和迁移素材。

## 当前状态

截至当前整理阶段，下列旧主题已经在新目录中有对应落点：

- LLM 调用层 -> `../modules/llm/`
- TTS -> `../modules/tts/`
- ASR -> `../modules/asr/`
- VAD -> `../modules/vad/`
- Frontend -> `../modules/frontend/`
- Live2D -> `../modules/live2d/`
- Memory -> `../modules/memory/`
- Storage / Routes 相关结构 -> `../modules/storage/` 与 `../modules/routes/`

后续如需继续清理，本目录适合逐步变为：

- 每篇旧稿顶部增加“已迁移 / superseded”说明；
- 或整体迁入 `../archive/`。
