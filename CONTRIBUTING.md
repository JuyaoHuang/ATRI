# Contributing / 贡献指南

感谢你对 **atri** 项目的关注！本文档将帮助你快速上手项目开发。

---

## 快速开始

请先阅读 [docs/quickstart.md](docs/quickstart.md) 完成环境搭建和首次运行。

---

## 分支与 PR 流程

1. 从 `main` 创建功能分支：`feat/<phase>-<feature>`（如 `feat/phase7-character-management`）
2. 按照对应 Phase 的执行规格开发，每个 User Story 一个 commit
3. 提交前运行自检：
   - **后端**：`mypy` → `ruff` → `pytest`
   - **前端**：`vue-tsc --noEmit` → `eslint` → 手动验证
4. 创建 PR 到 `main`，描述中注明对应的 Phase 和 User Story
5. 等待 review 后合并

---

## 代码规范

### 后端

- 详细规范见 [执行准则.md](执行准则.md)
- 使用 `loguru` 而非标准 `logging`
- 新模块遵循注册表工厂模式（参考 LLM 调用层）
- 修改代码前先阅读对应的设计文档章节

### 前端

- 详细规范见 [frontend/执行准则.md](frontend/执行准则.md)（如已配置为子模块）
- 组件使用 `<script setup lang="ts">` + Composition API
- 状态管理使用 Pinia Store
- 样式使用 UnoCSS

---

## 开发文档导读

`docs/developments/` 目录下包含架构设计和模块设计文档。你**不需要全部阅读**，请根据你要参与的模块选择性阅读。

### 所有贡献者必读

| 文档 | 说明 |
|------|------|
| [项目架构设计.md](docs/developments/项目架构设计.md) | 整体项目架构（前后端分层、模块划分、数据流） |
| [后端API接口文档.md](docs/developments/module-design/后端API接口文档.md) | 完整的 REST API + WebSocket 协议规范 |

### 后端开发者

> 技术栈：Python 3.11+ / FastAPI / uv / loguru

| 文档 | 说明 | 何时阅读 |
|------|------|---------|
| [执行准则.md](执行准则.md) | 后端代码规范和自检流程 | **必读** |
| [后端设计.md](docs/developments/module-design/后端设计.md) | 后端架构设计（分层、数据流） | 理解后端整体架构时 |
| [记忆系统设计讨论.md](docs/developments/module-design/记忆系统设计讨论.md) | 记忆系统完整设计（L1/L3/L4 压缩 + mem0） | 修改记忆系统时 |
| [LLM调用层设计讨论.md](docs/developments/module-design/LLM调用层设计讨论.md) | LLM 调用层设计（工厂模式、流式接口） | 修改 LLM 模块时 |
| [TTS模块设计文档.md](docs/developments/module-design/TTS模块设计文档.md) | TTS 模块设计（6 个提供商、工厂模式） | 开发 TTS 功能时 |
| [ASR模块设计文档.md](docs/developments/module-design/ASR模块设计文档.md) | ASR 模块设计（5 个提供商、流式支持） | 开发 ASR 功能时 |
| [VAD语音唤醒模块设计.md](docs/developments/module-design/VAD语音唤醒模块设计.md) | VAD 模块设计 | 开发语音唤醒功能时 |

### 前端开发者

> 技术栈：Vue 3 + TypeScript + Vite + Pinia + UnoCSS

| 文档 | 说明 | 何时阅读 |
|------|------|---------|
| [前端设计文档.md](docs/developments/module-design/前端设计文档.md) | 前端完整架构设计（组件、Store、路由、UI） | **必读** |
| [Live-2d设计文档.md](docs/developments/module-design/Live-2d设计文档.md) | Live2D 集成方案（渲染、表情控制） | 开发 Live2D 功能时 |

### 其他参考文档

| 文档 | 说明 |
|------|------|
| [会话上下文备份_20260418.md](docs/developments/会话上下文备份_20260418.md) | Phase 1-5 实现存档和当前状态 |
| [总结_前端对话历史.md](docs/developments/总结_前端对话历史.md) | 前端设计决策的结构化总结 |

---

## 配置文档

`docs/configs/` 目录下是面向用户的配置和使用指南：

| 文档 | 说明 |
|------|------|
| [角色创建指南.md](docs/configs/角色创建指南.md) | 如何创建和管理角色卡 |
| [TTS配置说明.md](docs/configs/TTS配置说明.md) | TTS 模块配置 |
| [ASR配置说明.md](docs/configs/ASR配置说明.md) | ASR 模块配置 |
| [CosyVoice3_TTS使用说明.md](docs/configs/CosyVoice3_TTS使用说明.md) | CosyVoice3 TTS 使用说明 |
| [认证系统使用指南.md](docs/configs/认证系统使用指南.md) | 认证系统配置 |
| [对话历史存储与批量删除说明.md](docs/configs/对话历史存储与批量删除说明.md) | 对话历史存储管理 |

---

## 许可证

本项目采用 [CC BY-NC 4.0](LICENSE) 许可证，**禁止商业使用**。

---

## 问题反馈

如果你在开发过程中遇到问题或有改进建议，请通过 Issue 提交。
