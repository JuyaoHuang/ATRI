# Contributing

Thank you for your interest in the **atri** project! This document will help you get started with development quickly.

---

## Getting Started

Please read [docs/quickstart.md](docs/quickstart.md) first to set up your environment and complete the initial run.

---

## Branch and PR Workflow

1. Create a feature branch from `main`: `feat/<phase>-<feature>` (e.g., `feat/phase7-character-management`)
2. Develop according to the execution specification for the corresponding Phase, with one commit per User Story
3. Run self-checks before submitting:
   - **Backend**: `mypy` -> `ruff` -> `pytest`
   - **Frontend**: `vue-tsc --noEmit` -> `eslint` -> manual verification
4. Create a PR to `main`, noting the corresponding Phase and User Story in the description
5. Wait for review and then merge

---

## Code Standards

### Backend

- See [执行准则.md](执行准则.md) for detailed standards
- Use `loguru` instead of the standard `logging` module
- New modules should follow the registry factory pattern (refer to the LLM calling layer)
- Read the relevant design document section before modifying code

### Frontend

- See [frontend/执行准则.md](frontend/执行准则.md) for detailed standards (if configured as a submodule)
- Components use `<script setup lang="ts">` + Composition API
- State management uses Pinia Store
- Styling uses UnoCSS

---

## Development Documentation Guide

The `docs/developments/` directory contains architecture design and module design documents. You **do not need to read all of them** -- please selectively read based on the module you are working on.

### Required Reading for All Contributors

| Document | Description |
|------|------|
| [Architecture Design](docs/developments/module-design/EN/project-architecture-design.md) | Overall project architecture (frontend/backend layering, module division, data flow) |
| [Backend API Documentation](docs/developments/module-design/EN/backend-API-documentation.md) | Complete REST API + WebSocket protocol specification |

### Backend Developers

> Tech stack: Python 3.11+ / FastAPI / uv / loguru

| Document | Description | When to Read |
|------|------|---------|
| [执行准则.md](执行准则.md) | Backend code standards and self-check workflow | **Required** |
| [后端设计.md](docs/developments/module-design/后端设计.md) | Backend architecture design (layering, data flow) | When understanding the overall backend architecture |
| [记忆系统设计讨论.md](docs/developments/module-design/记忆系统设计讨论.md) | Memory system complete design (L1/L3/L4 compression + mem0) | When modifying the memory system |
| [LLM调用层设计讨论.md](docs/developments/module-design/LLM调用层设计讨论.md) | LLM calling layer design (factory pattern, streaming interface) | When modifying the LLM module |
| [TTS模块设计文档.md](docs/developments/module-design/TTS模块设计文档.md) | TTS module design (6 providers, factory pattern) | When developing TTS features |
| [ASR模块设计文档.md](docs/developments/module-design/ASR模块设计文档.md) | ASR module design (5 providers, streaming support) | When developing ASR features |
| [VAD语音唤醒模块设计.md](docs/developments/module-design/VAD语音唤醒模块设计.md) | VAD module design | When developing voice wake-up features |

### Frontend Developers

> Tech stack: Vue 3 + TypeScript + Vite + Pinia + UnoCSS

| Document | Description | When to Read |
|------|------|---------|
| [前端设计文档.md](docs/developments/module-design/前端设计文档.md) | Frontend complete architecture design (components, Store, routing, UI) | **Required** |
| [Live-2d设计文档.md](docs/developments/module-design/Live-2d设计文档.md) | Live2D integration plan (rendering, expression control) | When developing Live2D features |

### Other Reference Documents

| Document | Description |
|------|------|
| [会话上下文备份_20260418.md](docs/developments/会话上下文备份_20260418.md) | Phase 1-5 implementation archive and current status |
| [总结_前端对话历史.md](docs/developments/总结_前端对话历史.md) | Structured summary of frontend design decisions |

---

## Configuration Documentation

The `docs/configs/` directory contains user-facing configuration and usage guides:

| Document | Description |
|------|------|
| [角色创建指南.md](docs/configs/角色创建指南.md) | How to create and manage character cards |
| [TTS配置说明.md](docs/configs/TTS配置说明.md) | TTS module configuration |
| [ASR配置说明.md](docs/configs/ASR配置说明.md) | ASR module configuration |
| [CosyVoice3_TTS使用说明.md](docs/configs/CosyVoice3_TTS使用说明.md) | CosyVoice3 TTS usage guide |
| [认证系统使用指南.md](docs/configs/认证系统使用指南.md) | Authentication system configuration |
| [对话历史存储与批量删除说明.md](docs/configs/对话历史存储与批量删除说明.md) | Chat history storage management |

---

## License

This project is licensed under [CC BY-NC 4.0](LICENSE). **Commercial use is prohibited.**

---

## Issue Reporting

If you encounter issues or have improvement suggestions during development, please submit them via Issues.
