---
status: active
owner: vad
created: 2026-07-09
updated: 2026-07-09
related_code:
  - src/vad/
  - src/routes/chat_ws.py
  - frontend/src/composables/useRealtimeVoiceInput.ts
  - frontend/src/components/chat/RealtimeVoiceInput.vue
---

# VAD 模块长期设计

本目录沉淀 `src/vad/` 和实时语音打断链路的长期模块文档。用户侧参数说明仍以 [VAD配置说明](../../../configs/CN/VAD配置说明.md) 和 [实时语音模式使用说明](../../../configs/CN/实时语音模式使用说明.md) 为准。

## 当前文档

| 文档 | 内容 |
| --- | --- |
| [design.zh-CN.md](design.zh-CN.md) | VAD 模块总设计，串起 Provider、session、防抖、连接态和实时打断链路的分工。 |
| [architecture.zh-CN.md](architecture.zh-CN.md) | VAD 的模块定位、Provider/session/service 分层和聊天 WebSocket 集成。 |
| [config.zh-CN.md](config.zh-CN.md) | `config/vad_config.yaml` 的结构、Provider 参数和防抖归属。 |
| [realtime-interrupt-boundary.zh-CN.md](realtime-interrupt-boundary.zh-CN.md) | `speech_start`/`speech_end` 的长期语义、协议边界，以及与 ASR/TTS/记忆的交界。 |

## 阅读顺序

1. 先读 [design.zh-CN.md](design.zh-CN.md)，确认 Provider、session、chat_ws 连接态如何分工。
2. 再读 [architecture.zh-CN.md](architecture.zh-CN.md)，确认 VAD 不是独立 REST 子系统。
3. 再读 [config.zh-CN.md](config.zh-CN.md)，确认根参数和 Provider 参数各自控制什么。
4. 最后读 [realtime-interrupt-boundary.zh-CN.md](realtime-interrupt-boundary.zh-CN.md)，核对打断、ASR 接管和旧音频丢弃的长期契约。

## 文档关系

- 开发过程、M0-M6 阶段事实和验收记录保留在 [../../features/2026-06-vad-realtime-interrupt/README.zh-CN.md](../../features/2026-06-vad-realtime-interrupt/README.zh-CN.md) 及其子文档。
- Wiki 发布稿保留在 [../../wiki/development-blogs/2026-07-08-vad-realtime-interrupt.zh-CN.md](../../wiki/development-blogs/2026-07-08-vad-realtime-interrupt.zh-CN.md)。
- 旧文档 [../../module-design/CN/VAD语音唤醒模块设计.md](../../module-design/CN/VAD语音唤醒模块设计.md) 仍是历史来源，但其中“独立 `/api/vad/detect` 主路径”和“待实现 Phase”不再代表当前状态。

## 收录规则

这里记录跨版本仍应遵守的 VAD 边界：实时控制事件、防抖归属、ASR 接管时机和与聊天/TTS/记忆的接口。阶段计划、调试流水和一次性验收不放在本目录。
