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

- See [AGENTS.md](AGENTS.md) for detailed standards
- Use `loguru` instead of the standard `logging` module
- New modules should follow the registry factory pattern (refer to the LLM calling layer)
- Read the relevant design document section before modifying code

### Frontend

- See [frontend/AGENTS.md](frontend/AGENTS.md) for detailed standards (if configured as a submodule)
- Components use `<script setup lang="ts">` + Composition API
- State management uses Pinia Store
- Styling uses UnoCSS

---

## Development Documentation Guide

The `docs/developments/` directory contains architecture design and module design documents. You **do not need to read all of them** -- please selectively read based on the module you are working on.

### Required Reading for All Contributors

| Document | Description |
|------|------|
| [Architecture Design](docs/developments/project-architecture-design.en.md) | Overall project architecture (frontend/backend layering, module division, data flow) |
| [Backend API Documentation](docs/developments/module-design/EN/backend-API-documentation.md) | Complete REST API + WebSocket protocol specification |

### Backend Developers

> Tech stack: Python 3.11+ / FastAPI / uv / loguru

| Document | Description | When to Read |
|------|------|---------|
| [Backend Guidelines](AGENTS.md) | Backend code standards and self-check workflow | **Required** |
| [Backend Design](docs/developments/module-design/EN/backend-design.md) | Backend architecture design (layering, data flow) | When understanding the overall backend architecture |
| [Memory System Design](docs/developments/module-design/EN/memory-system-design.md) | Memory system complete design (L1/L3/L4 compression + mem0) | When modifying the memory system |
| [LLM Calling Layer Design](docs/developments/module-design/EN/LLM-calling-layer-design.md) | LLM calling layer design (factory pattern, streaming interface) | When modifying the LLM module |
| [TTS Module Design](docs/developments/module-design/EN/TTS-module-design.md) | TTS module design (6 providers, factory pattern) | When developing TTS features |
| [ASR Module Design](docs/developments/module-design/EN/ASR-module-design.md) | ASR module design (5 providers, streaming support) | When developing ASR features |
| [VAD Voice Wake Module Design](docs/developments/module-design/EN/VAD-voice-wake-module-design.md) | VAD module design | When developing voice wake-up features |

### Frontend Developers

> Tech stack: Vue 3 + TypeScript + Vite + Pinia + UnoCSS

| Document | Description | When to Read |
|------|------|---------|
| [Frontend Design](docs/developments/module-design/EN/frontend-design.md) | Frontend complete architecture design (components, Store, routing, UI) | **Required** |
| [Live2D Design](docs/developments/module-design/EN/Live2D-design.md) | Live2D integration plan (rendering, expression control) | When developing Live2D features |

### Other Reference Documents

| Document | Description |
|------|------|
| [Session Context Backup (20260418)](docs/developments/会话上下文备份_20260418.md) | Phase 1-5 implementation archive and current status |
| [Frontend Design History Summary](docs/developments/总结_前端对话历史.md) | Structured summary of frontend design decisions |

---

## Configuration Documentation

The `docs/configs/` directory contains user-facing configuration and usage guides:

| Document | Description |
|------|------|
| [Character Creation Guide](docs/configs/EN/character-creation-guide.md) | How to create and manage character cards |
| [TTS Configuration](docs/configs/EN/TTS-configuration.md) | TTS module configuration |
| [ASR Configuration](docs/configs/EN/ASR-configuration.md) | ASR module configuration |
| [CosyVoice3 TTS Usage](docs/configs/EN/CosyVoice3-TTS-usage.md) | CosyVoice3 TTS usage guide |
| [Authentication System Guide](docs/configs/EN/authentication-system-guide.md) | Authentication system configuration |
| [Chat History Storage & Batch Deletion](docs/configs/EN/chat-history-storage-batch-deletion.md) | Chat history storage management |

---

## License

This project is licensed under [CC BY-NC 4.0](LICENSE). **Commercial use is prohibited.**

---

## Issue Reporting

If you encounter issues or have improvement suggestions during development, please submit them via Issues.
