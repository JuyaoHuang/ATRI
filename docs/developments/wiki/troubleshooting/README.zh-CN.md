---
status: active
owner: docs
created: 2026-07-09
updated: 2026-07-09
---

# Troubleshooting

本目录保存准备迁移到 GitHub Wiki 的问题排查文章。

这里的文档面向“遇到问题的人”，不是原始开发日志。开发过程流水应先放在 `../../features/`。

## 当前文档

### 实时语音

| 文档 | 内容 |
| --- | --- |
| [realtime-voice-mode.zh-CN.md](realtime-voice-mode.zh-CN.md) | 实时语音模式的 WebSocket、VAD、ASR 自动提交和浏览器采集排障。 |
| [realtime-voice-mode.en-US.md](realtime-voice-mode.en-US.md) | English realtime voice mode troubleshooting note. |

### 存储与记忆

| 文档 | 内容 |
| --- | --- |
| [chat-history-cleanup.zh-CN.md](chat-history-cleanup.zh-CN.md) | 中文聊天历史、短期记忆和长期记忆清理入口。 |
| [chat-history-cleanup.en-US.md](chat-history-cleanup.en-US.md) | English chat history cleanup and batch deletion guide. |
| [chat-history-memory-repair.zh-CN.md](chat-history-memory-repair.zh-CN.md) | 手工修改聊天历史后的短期记忆修复原则与校验项。 |

### TTS 与音频播放

当前还没有独立的 TTS 排障稿。涉及分段流式化、自动播放和打断边界时，先读：

| 文档 | 内容 |
| --- | --- |
| [../../modules/tts/streaming-design.zh-CN.md](../../modules/tts/streaming-design.zh-CN.md) | TTS 分段流式化长期设计，覆盖 `generation_id`、`sequence` 和丢弃规则。 |
| [../../features/2026-07-tts-segment-streaming/README.zh-CN.md](../../features/2026-07-tts-segment-streaming/README.zh-CN.md) | 第一版 TTS 分段流式化 feature 的范围与落地状态。 |
