---
status: active
owner: docs
created: 2026-07-08
updated: 2026-07-09
---

# 开发 Blog 发布稿

本目录保存整理后、适合迁移到 GitHub Wiki 的开发文章。这里不放原始开发流水，也不替代 feature 目录中的 `dev-log.zh-CN.md`。

## 当前文章

| 文档 | 主题 | 来源 |
|---|---|---|
| [2026-07-08-vad-realtime-interrupt.zh-CN.md](2026-07-08-vad-realtime-interrupt.zh-CN.md) | VAD 实时打断开发复盘 | `../../features/2026-06-vad-realtime-interrupt/dev-log.zh-CN.md` |
| [2026-07-09-tts-segment-streaming.zh-CN.md](2026-07-09-tts-segment-streaming.zh-CN.md) | TTS 分段流式化开发复盘 | `../../features/2026-07-tts-segment-streaming/README.zh-CN.md` 与旧 `wiki/TTS/*` 设计/实施稿 |
| [2026-07-09-frontend-websocket-session-refactor.zh-CN.md](2026-07-09-frontend-websocket-session-refactor.zh-CN.md) | Frontend WebSocket Session 重构复盘 | `../../features/2026-07-frontend-websocket-session-refactor/dev-log.zh-CN.md` |

## 当前主题

这批文章当前覆盖三类主题：

- 实时语音链路：VAD 打断、ASR 自动接管、旧 generation 失效治理
- 语音输出链路：TTS 应用层分段流式化、音频事件协议、播放丢弃策略
- 前端运行时：WebSocket session authority、发送出口收敛、页面级连接生命周期

## 写作要求

- 先交代背景和问题，再说明方案。
- 保留关键协议、边界和验收证据。
- 删除临时 debug、重复对话和过时尝试。
- 长期设计结论应沉淀到 `../../modules/`，不要只留在 blog 中。
