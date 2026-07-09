# 开发文档导航

本目录保存 ATRI 的开发侧文档，面向需要理解架构、模块边界、功能开发过程和技术决策的维护者。

## 目录职责

| 目录 | 职责 | 适合放置 |
|---|---|---|
| `architecture/` | 项目级架构 | 分层、跨模块数据流、整体工作流 |
| `api/` | 稳定接口协议 | REST API、WebSocket、事件格式 |
| `modules/` | 长期模块设计 | 与 `src/` 模块对齐的设计、配置、边界 |
| `features/` | 功能开发过程 | 某次 feature 的设计、计划、日志、验收 |
| `wiki/` | GitHub Wiki 预发布稿 | 整理后的教程、模块介绍、开发文章 |
| `decisions/` | 架构决策记录 | ADR、关键取舍、被放弃方案 |
| `templates/` | 文档模板 | feature、模块设计、ADR、验收模板 |
| `archive/` | 历史归档 | 不再维护但仍有参考价值的旧文档 |

## 阅读路径

1. 修改某个模块前，先读 `modules/<module>/` 中的长期设计。
2. 继续某次功能开发时，读 `features/<YYYY-MM-feature>/` 中的设计、计划和日志。
3. 查询某个关键技术取舍时，读 `decisions/`。
4. 准备对外发布或整理 Wiki 时，读 `wiki/`。

## 当前重点入口

| 主题 | 推荐入口 |
|---|---|
| TTS 分段流式化长期设计 | [modules/tts/streaming-design.zh-CN.md](modules/tts/streaming-design.zh-CN.md) |
| TTS 配置与 CosyVoice3 Provider | [modules/tts/README.zh-CN.md](modules/tts/README.zh-CN.md) |
| TTS 分段流式化 feature 过程 | [features/2026-07-tts-segment-streaming/README.zh-CN.md](features/2026-07-tts-segment-streaming/README.zh-CN.md) |
| VAD 实时打断 feature 过程 | [features/2026-06-vad-realtime-interrupt/README.zh-CN.md](features/2026-06-vad-realtime-interrupt/README.zh-CN.md) |
| VAD 实时打断 Wiki 发布稿 | [wiki/development-blogs/2026-07-08-vad-realtime-interrupt.zh-CN.md](wiki/development-blogs/2026-07-08-vad-realtime-interrupt.zh-CN.md) |
| 认证模块与协议 | [modules/auth/README.zh-CN.md](modules/auth/README.zh-CN.md) |
| 对话历史存储与记忆归档 | [modules/storage/README.zh-CN.md](modules/storage/README.zh-CN.md) |
| 角色 Persona 技术说明 | [modules/agent/README.zh-CN.md](modules/agent/README.zh-CN.md) |
| 实时语音模式排障 | [wiki/troubleshooting/realtime-voice-mode.zh-CN.md](wiki/troubleshooting/realtime-voice-mode.zh-CN.md) |

## 迁移原则

旧文档不要一次性删除。迁移时先保留旧路径入口，并在旧文档顶部指向新位置。长期有效结论沉淀到 `modules/`，开发流水保留在 `features/`，整理后的发布稿放入 `wiki/`。
