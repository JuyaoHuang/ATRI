---
status: accepted
owner: tts
created: 2026-07-08
updated: 2026-07-08
related_code:
  - src/tts/
  - src/routes/chat_ws.py
  - frontend/src/composables/useAudioPlayer.ts
  - frontend/src/composables/useWebSocket.ts
---

# TTS 分段流式化

本目录用于承载 2026-07 TTS 分段流式化 feature 的过程文档。当前先建立 feature 入口，后续可逐步把旧 `wiki/TTS/` 下的设计、实施和验收记录迁移为本目录的 `design.zh-CN.md`、`implementation-plan.zh-CN.md`、`dev-log.zh-CN.md` 和 `acceptance.zh-CN.md`。

## 当前状态

- 状态：第一版已完成并验收通过。
- 长期模块结论：见 `../../modules/tts/streaming-design.zh-CN.md`。
- 旧设计来源：见 `../../wiki/TTS/tts-stream-design.md`。
- 旧实施来源：见 `../../wiki/TTS/tts-stream-implement.md`。

## 功能范围

本 feature 完成 ATRI 应用层 TTS 分段流式化：

1. LLM 文本流继续以 `output:chat:*` 作为聊天显示和历史保存依据。
2. 后端用 `SentenceDivider` 将已发送给前端的文本切成可朗读 segment。
3. `TTSSegmentManager` 复用现有 `TTSService.synthesize()` 并发合成小音频。
4. 后端通过 `output:audio:segment`、`output:audio:complete`、`output:audio:error` 下发音频事件。
5. 前端按 `generation_id + sequence` 播放音频段，并在 VAD interrupt 或上下文变化时丢弃旧 generation。

## 不在本范围

- 不实现 provider 原生 `synthesize_stream()`。
- 不引入 `heard_response`。
- 不让 TTS 播放进度回写聊天历史、记忆或 interrupted partial reply。
- 不新增前端上下文切换时主动通知后端取消旧 TTS 的协议。
- 不做二进制 WebSocket audio frame。

## 阅读顺序

1. 长期设计：`../../modules/tts/streaming-design.zh-CN.md`
2. 旧设计草案：`../../wiki/TTS/tts-stream-design.md`
3. 旧实施记录：`../../wiki/TTS/tts-stream-implement.md`
4. 代码实现：`src/tts/sentence_divider.py`、`src/tts/segment_manager.py`、`src/routes/chat_ws.py`
