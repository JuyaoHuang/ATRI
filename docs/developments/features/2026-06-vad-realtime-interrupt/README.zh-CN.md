---
status: accepted
owner: vad
created: 2026-06-15
updated: 2026-07-08
related_code:
  - src/vad/
  - src/asr/
  - src/routes/chat_ws.py
  - frontend/src/components/chat/RealtimeVoiceInput.vue
  - frontend/src/composables/useRealtimeVoiceInput.ts
  - frontend/src/composables/useAudioPlayer.ts
  - frontend/src/composables/useWebSocket.ts
---

# VAD 实时打断

本目录记录 2026-06 VAD 实时打断功能从设计到落地的开发过程。它属于 feature 过程文档，用于追溯阶段事实、关键边界和验收结果，不替代长期模块设计文档。

## 当前状态

- 状态：已完成第一版 MVP，并进入文档重组。
- 开发窗口：2026-06-15 到 2026-06-19。
- 后续补丁：2026-06-19 完成状态归属与竞态治理。
- Wiki 发布稿：见 `../../wiki/development-blogs/2026-07-08-vad-realtime-interrupt.zh-CN.md`。

## 整理口径

- 本 README 只作为 feature 入口，固定范围、边界和阅读顺序。
- `dev-log.zh-CN.md` 从旧 `development.md` 中提取阶段事实、关键决策、问题修正和验收结果。
- Wiki 发布稿面向读者解释设计动机、方案取舍和经验教训，不逐条复制开发流水。
- 旧 `development.md` 中 2026-07-08 的 TTS 分段流式化内容不并入本 feature，只在边界处说明它是后续独立 feature。

## 功能范围

本 feature 完成了 ATRI 的实时语音控制主链路：

1. 前端通过 WebSocket 持续发送麦克风音频片段。
2. 后端 VAD 在 `speech_start` 时立即触发 `control:interrupt`。
3. `speech_start` 使当前 LLM `generation_id` 失效，旧 generation 的 chunk、complete 和普通持久化结果会被丢弃。
4. 前端收到 interrupt 后停止当前播放，并丢弃旧 generation 的自动 TTS 音频结果。
5. `speech_end` 后端提交 ASR，转写成功后自动进入新一轮聊天。
6. 被打断的半截回复以“后端已经发送给前端的文本”为准，保存为 `interrupted=true` 的审计历史，但不进入普通记忆轮次。

## 不在本范围

- 不把 VAD 做成一次性 REST `/api/vad/detect` 主路径。
- 不复用 OLV 的 WebSocket 消息名或 sentinel bytes。
- 不把 Web Speech API 当作 VAD model。
- 不引入前端 `heard_response` 回传。
- 不要求 TTS provider 支持原生 `synthesize_stream()`。
- 不把 TTS 分段流式化并入 VAD MVP；该方向后续作为独立 feature 推进。

## 子文档

| 文档 | 职责 |
|---|---|
| `dev-log.zh-CN.md` | 按阶段重组的开发过程事实、决策、问题和验收记录 |
| `../../wiki/development-blogs/2026-07-08-vad-realtime-interrupt.zh-CN.md` | 面向 Wiki 读者的整理版开发文章 |

## 参考来源

- `../../wiki/VAD/vad-design.md`
- `../../wiki/VAD/vad-implement.md`
- `../../wiki/VAD/vad-implementation-plan.md`
- `../../wiki/VAD/development.md`

## 阅读顺序

1. 想理解功能边界，先读本 README。
2. 想追溯实现过程，读 `dev-log.zh-CN.md`。
3. 想读整理后的发布文章，读 Wiki 发布稿。
4. 修改 VAD 模块前，再回到长期设计和实施计划文档核对边界。
