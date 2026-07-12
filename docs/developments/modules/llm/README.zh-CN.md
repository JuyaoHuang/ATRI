---
status: active
owner: llm
created: 2026-07-09
updated: 2026-07-11
---

# LLM 模块长期设计

本目录沉淀 LLM 调用层的长期规则。这里回答调用契约、角色映射、Provider 注册、当前轮单图边界、错误边界和后续扩展入口；具体模型选型、密钥配置和值班排障仍以运行配置和源码为准。

## 当前文档

| 文档 | 内容 |
| --- | --- |
| [design.zh-CN.md](design.zh-CN.md) | LLM 模块总设计，串起无状态调用层、角色映射、Provider 池、错误所有权和上游调用关系。 |
| [call-layer.zh-CN.md](call-layer.zh-CN.md) | LLM 调用层的接口、工厂、角色映射、Provider、异常层次和 `tools` 预留说明。 |

## 模块边界

LLM 模块负责四件事：

1. 定义无状态调用接口 `LLMInterface`。
2. 通过 `LLMFactory` 和 `create_from_role()` 把运行配置解析为具体 Provider 实例。
3. 统一把 SDK 异常映射为项目内的 `LLMError` 层次。
4. 将可选的当前轮图片序列化为 Provider 的多模态 user message。

它不负责：

- 组装 Persona、短期记忆、长期记忆后的完整上下文。
- 决定重试、降级或向用户展示怎样的错误文本。
- 管理角色文件、聊天历史、mem0 或 TTS。

## 阅读路径

建议按下面顺序阅读：

1. `config/llm_config.yaml`
2. [design.zh-CN.md](design.zh-CN.md)
3. [call-layer.zh-CN.md](call-layer.zh-CN.md)
4. `src/llm/interface.py`
5. `src/llm/factory.py`
6. `src/llm/providers/`
7. `src/service_context.py`

## 相关实现入口

- `src/llm/__init__.py`
- `src/llm/interface.py`
- `src/llm/factory.py`
- `src/llm/exceptions.py`
- `src/llm/multimodal.py`
- `src/llm/providers/openai_compatible.py`
- `src/llm/providers/siliconflow.py`
- `src/llm/providers/xiaomi.py`
- `src/service_context.py`
- `src/routes/chats.py`

## 设计约束

- Provider 选择由 `config/llm_config.yaml` 中的 `llm_roles` 和 `llm_configs` 驱动。
- `mem0` 自身使用的事实抽取模型不走这里的角色映射，而是走 `config/memory_config.yaml`。
- `tools` 参数已经在接口层保留，但当前内置 Provider 都不会消费它。
- `input_image` 只属于当前调用，不进入历史或 Memory；模型是否具备视觉能力由运行配置决定。
