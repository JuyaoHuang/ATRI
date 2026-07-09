# 功能开发过程

本目录保存每次较大功能开发的过程文档。每个 feature 使用独立目录：

```text
features/YYYY-MM-feature-slug/
```

推荐文件：

| 文件 | 职责 |
|---|---|
| `README.zh-CN.md` | feature 入口、范围、状态、相关链接 |
| `design.zh-CN.md` | 本次功能的目标、边界、方案和取舍 |
| `implementation-plan.zh-CN.md` | step、point、文件改动和测试计划 |
| `dev-log.zh-CN.md` | 开发过程事实、问题、修正和阶段记录 |
| `acceptance.zh-CN.md` | 验收场景、命令、结果和遗留风险 |
| `references.zh-CN.md` | 参考资料、相关代码、issue/PR |

## 当前 Feature

| Feature | 状态 | 入口 |
|---|---|---|
| VAD 实时打断 | accepted | [2026-06-vad-realtime-interrupt/README.zh-CN.md](2026-06-vad-realtime-interrupt/README.zh-CN.md) |
| TTS 分段流式化 | accepted | [2026-07-tts-segment-streaming/README.zh-CN.md](2026-07-tts-segment-streaming/README.zh-CN.md) |
| Frontend WebSocket Session Refactor | active | [2026-07-frontend-websocket-session-refactor/README.zh-CN.md](2026-07-frontend-websocket-session-refactor/README.zh-CN.md) |

feature 完成后，应把长期有效结论提炼到 `../modules/<module>/`，把适合阅读的文章整理到 `../wiki/`。
