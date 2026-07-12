# 模块长期设计

本目录保存长期有效的模块设计，目录名尽量和 `src/` 下的模块对齐。

推荐结构：

```text
modules/<module>/
├── README.zh-CN.md
├── design.zh-CN.md
├── config.zh-CN.md
├── interface.zh-CN.md
└── <feature>-design.zh-CN.md
```

文档应回答：

- 模块负责什么，不负责什么
- 与其他模块如何交互
- 配置项和默认值是什么
- 关键数据流和生命周期是什么
- 当前实现有哪些稳定约束

## 当前模块入口

| 模块 | 文档 |
|---|---|
| Agent | [agent/README.zh-CN.md](agent/README.zh-CN.md) |
| ASR | [asr/README.zh-CN.md](asr/README.zh-CN.md) |
| Auth | [auth/README.zh-CN.md](auth/README.zh-CN.md) |
| Frontend | [frontend/README.zh-CN.md](frontend/README.zh-CN.md) |
| Live2D | [live2d/README.zh-CN.md](live2d/README.zh-CN.md) |
| LLM | [llm/README.zh-CN.md](llm/README.zh-CN.md) |
| Memory | [memory/README.zh-CN.md](memory/README.zh-CN.md) |
| Routes | [routes/README.zh-CN.md](routes/README.zh-CN.md) |
| Storage | [storage/README.zh-CN.md](storage/README.zh-CN.md) |
| TTS | [tts/README.zh-CN.md](tts/README.zh-CN.md) |
| VAD | [vad/README.zh-CN.md](vad/README.zh-CN.md) |
| Vision | [vision/README.zh-CN.md](vision/README.zh-CN.md) |

开发过程、验收记录和临时讨论应放入 `../features/`，不要堆进模块长期设计。
