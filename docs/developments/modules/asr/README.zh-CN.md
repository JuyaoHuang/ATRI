---
status: active
owner: asr
created: 2026-07-09
updated: 2026-07-09
related_code:
  - src/asr/
  - src/routes/asr.py
  - src/routes/chat_ws.py
  - frontend/src/stores/asr.ts
  - frontend/src/composables/useVoiceInput.ts
---

# ASR 模块长期设计

本目录沉淀 `src/asr/` 的长期模块文档。用户侧安装、模型准备和设置页面操作仍以 [ASR配置说明](../../../configs/CN/ASR配置说明.md) 为准。

## 当前文档

| 文档 | 内容 |
| --- | --- |
| [design.zh-CN.md](design.zh-CN.md) | ASR 模块总设计，串起三条链路、Provider 能力模型、WAV 上传契约和本地实例常驻缓存。 |
| [architecture.zh-CN.md](architecture.zh-CN.md) | ASR 的模块定位、分层结构、上传转录链路和与 VAD/WebSocket 的交界。 |
| [interface.zh-CN.md](interface.zh-CN.md) | ASR 接口、工厂、服务层、上传 WAV 契约、常驻本地 Provider 缓存和异常映射。 |
| [config.zh-CN.md](config.zh-CN.md) | `config/asr_config.yaml` 的结构、前后端可写边界、敏感字段和遗留配置说明。 |
| [provider-matrix.zh-CN.md](provider-matrix.zh-CN.md) | 当前已注册 Provider 的能力矩阵、健康前提、输入格式和注意事项。 |

## 阅读顺序

1. 先读 [design.zh-CN.md](design.zh-CN.md)，确认三条链路和模块总边界。
2. 再读 [architecture.zh-CN.md](architecture.zh-CN.md)，确认 ASR 在系统中的职责。
3. 再读 [interface.zh-CN.md](interface.zh-CN.md)，确认 Provider 契约、工厂和上传转录边界。
4. 再读 [provider-matrix.zh-CN.md](provider-matrix.zh-CN.md)，确认当前代码真正注册了哪些 Provider。
5. 最后读 [config.zh-CN.md](config.zh-CN.md)，核对 YAML、前端设置页和后端运行边界。

## 文档关系

- 旧文档 [../../module-design/CN/ASR模块设计文档.md](../../module-design/CN/ASR模块设计文档.md) 仍保留为历史来源。
- 旧文档中关于 6 个 Provider、独立 ASR WebSocket、统一流式 `transcribe_stream()` 的表述不再代表当前实现。
- 与 VAD 实时打断链路的交界，以 [../vad/realtime-interrupt-boundary.zh-CN.md](../vad/realtime-interrupt-boundary.zh-CN.md) 和 `src/routes/chat_ws.py` 为准。

## 收录规则

这里记录跨版本仍应成立的 ASR 模块边界、配置语义和 Provider 事实；一次性联调过程、M 阶段日志和排障流水继续保留在 `features/`、`wiki/` 或 `configs/`。
