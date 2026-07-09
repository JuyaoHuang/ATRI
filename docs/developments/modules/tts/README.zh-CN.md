---
status: active
owner: tts
created: 2026-07-08
updated: 2026-07-09
---

# TTS 模块长期设计

本目录保存 TTS 模块长期有效的设计结论。这里的文档回答模块边界、核心协议、配置含义和扩展约束；开发计划、验收记录和迁移过程仍保留在 feature 或 wiki 文档中。

## 当前文档

| 文档 | 内容 |
| --- | --- |
| [design.zh-CN.md](design.zh-CN.md) | TTS 模块总览，说明当前 Provider 注册表、REST 完整音频路径、WebSocket 分段音频路径和与聊天/VAD 的长期边界。 |
| [config.zh-CN.md](config.zh-CN.md) | TTS 配置的开发侧边界，覆盖 Provider 块、前端回写白名单、敏感配置、REST 完整音频链路和错误处理。 |
| [config.en-US.md](config.en-US.md) | English version of the TTS configuration and runtime boundary notes. |
| [cosyvoice3-provider.zh-CN.md](cosyvoice3-provider.zh-CN.md) | CosyVoice3 Provider 实现说明，覆盖 Gradio WebUI 调用方式、音色机制、参数含义和当前限制。 |
| [cosyvoice3-provider.en-US.md](cosyvoice3-provider.en-US.md) | English version of the CosyVoice3 Provider implementation notes. |
| [streaming-design.zh-CN.md](streaming-design.zh-CN.md) | TTS 应用层分段流式化设计，覆盖模块定位、分段策略、`TTSSegmentManager`、WebSocket audio 协议、播放丢弃策略和后续扩展边界。 |
| [streaming-design.en-US.md](streaming-design.en-US.md) | English summary of the application-level segmented TTS streaming design. |

## 阅读路径

修改 TTS 分段流式化相关设计或实现前，建议按以下顺序阅读：

1. 模块总览：`design.zh-CN.md`
2. 配置边界：`config.zh-CN.md`
3. 长期流式设计：`streaming-design.zh-CN.md`
4. feature 范围与完成状态：`../../features/2026-07-tts-segment-streaming/README.zh-CN.md`
5. 原始设计来源：`../../wiki/TTS/tts-stream-design.md`
6. 原始实施来源：`../../wiki/TTS/tts-stream-implement.md`

相关实现入口：

1. `src/tts/sentence_divider.py`
2. `src/tts/segment_manager.py`
3. `src/routes/chat_ws.py`
4. `frontend/src/utils/websocket.ts`
5. `frontend/src/composables/useWebSocket.ts`
6. `frontend/src/composables/useAudioPlayer.ts`

## 收录规则

本目录只收录跨版本仍应遵守的模块设计，例如协议语义、生命周期边界、配置约束和扩展原则。

以下内容不放入本目录，应继续保留在 `docs/developments/features/`、`docs/developments/wiki/` 或 `docs/developments/archive/`：

- 分 step 实施计划和 commit 拆分建议。
- 一次性验收清单、测试执行记录和 debug 过程。
- 已被长期设计吸收的旧草案全文。
- 针对某次实现细节的临时风险列表。
