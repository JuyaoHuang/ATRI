# Project Architecture Design

> **Document Version**: v1.0  
> **Created**: 2026-04-23  
> **Last Updated**: 2026-04-23

---

## Document Description

This document serves as the **architecture overview and documentation navigation hub for the atri project**, aimed at helping AI and developers quickly grasp the overall structure, layered design, and module relationships of the project.

**How to Read**:
1. First read the document headings to understand the structure
2. Based on the headings/structure, read the key content you need
3. Use keywords to search the document for key information

**Repository Paths**:
- **Backend**: `D:\Coding\GitHub_Resuorse\emotion-robot\atri`
- **Frontend**: `D:\Coding\GitHub_Resuorse\emotion-robot\atri-webui`
- **Root Directory**: `D:\Coding\GitHub_Resuorse\emotion-robot` (not managed by git)

---

## 1. Project Overview

### 1.1 Project Introduction

**atri** is an RAG (Retrieval-Augmented Generation) based emotional chatbot, focused on **persistent memory** and **multimodal interaction**. The project uses a frontend-backend separated architecture, where the backend provides REST API + WebSocket services, and the frontend supports dual-mode UI (ChatGPT style / AIRI style).

**Core Features**:
- **Long-term Memory System**: RAG architecture based on mem0, supporting session recovery and cross-session memory
- **Multi-character Dialogue**: Supports multiple chat characters (Persona), each with independent memory
- **Streaming Dialogue**: Real-time streaming output via WebSocket, supporting typewriter effect
- **Modular Design**: LLM/ASR/TTS/Translation modules all use the factory pattern with pluggable configuration
- **Live2D Integration**: Optional Live2D model display (reusing AIRI implementation)

### 1.2 Core Features

| Feature Module | Status | Description |
|---------|------|------|
| **Chat Dialogue** | Completed | Streaming dialogue, history management, character switching |
| **Memory System** | Completed | L1/L3/L4 three-layer compression + mem0 long-term memory |
| **Character Management** | Completed | Persona loading, character list API |
| **Session Management** | Completed | Create/delete/update chats, automatic title generation |
| **Frontend UI** | In Planning | Dual-mode main page, settings system |
| **Live2D** | In Planning | Model rendering, expression control |
| **ASR Voice Input** | In Planning | 5 Providers (faster_whisper/whisper_cpp/sherpa_onnx/azure/Web Speech API) |
| **TTS Voice Output** | In Planning | 6 Providers (edge_tts/cosyvoice2/gpt_sovits/siliconflow/openai/elevenlabs) |
| **Translation Module** | In Planning | Plugin-style text transformation, supporting frontend/TTS consumption |
| **Authentication System** | In Planning | GitHub OAuth + whitelist mode |

### 1.3 Technology Stack

#### Backend Technology Stack
- **Language**: Python 3.11+
- **Framework**: FastAPI + Uvicorn
- **Dependency Management**: uv (pyproject.toml + uv.lock)
- **LLM Calling**: OpenAI SDK (supporting openai_compatible provider)
- **Memory System**: mem0 (v3 ADD-only algorithm) + Qdrant (vector database)
- **Logging**: loguru (console INFO + file DEBUG, 10MB rotation)
- **Testing**: pytest + mypy + ruff

#### Frontend Technology Stack
- **Language**: TypeScript
- **Framework**: Vue 3 + Vite
- **State Management**: Pinia
- **Styling**: UnoCSS (atomic CSS)
- **UI Components**: reka-ui (reusing AIRI's @proj-airi/ui)
- **HTTP Client**: axios
- **WebSocket**: Native WebSocket API (exponential backoff reconnection)
- **Live2D**: pixi-live2d-display (reusing AIRI implementation)

### 1.4 Implementation Status

#### Completed (Phase 1-5)

| Phase | Module | Status | Test Coverage |
|-------|------|------|---------|
| **Phase 1** | Infrastructure (config loading + logging) | Completed | 12 tests |
| **Phase 2** | LLM Calling Layer (registry factory + openai_compatible) | Completed | 42 tests |
| **Phase 3** | Memory System (L1/L3/L4 + mem0 + session management) | Completed | 117 tests |
| **Phase 4** | ChatAgent (streaming dual interface + Persona + ServiceContext) | Completed | 31 tests |
| **Phase 5** | FastAPI Service Layer (REST API + WebSocket + storage abstraction) | Completed | 58 tests |

**Backend Status**:
- 264 tests passed / 4 deselected
- mypy all green (35 source files)
- ruff clean (60+ files)
- Production-ready (excluding frontend)

#### In Planning (Phase 6-10)

> **Note**: The division and execution boundaries of Phase 6-10 still need to be discussed and confirmed later; the following is for reference only.

| Phase | Module | Priority | Description |
|-------|------|--------|------|
| **Phase 6-7** | Frontend MVP (basic chat interface + character management) | P0 | Dual-mode main page, WebSocket integration, settings system |
| **Phase 8** | Live2D Integration | P1 | Model rendering, expression control, model management |
| **Phase 9** | Authentication System | P1 | GitHub OAuth + whitelist |
| **Phase 10** | ASR/TTS Voice Interaction | P2 | 5 ASR Providers + 6 TTS Providers |

---

## 2. Documentation Navigation

This section categorizes all design documents by use case, providing quick navigation.

### 2.1 Quick Start

| Document | Path | Purpose |
|------|------|------|
| **Project README** | `D:\Coding\GitHub_Resuorse\emotion-robot\readme.md` | Project goals, execution steps, memory system implementation overview |
| **Session Context Backup** | `D:\Coding\GitHub_Resuorse\emotion-robot\docs\会话上下文备份_20260418.md` | Phase 1-5 implementation archive, key decision records, new session context recovery |
| **CLAUDE.md** | `D:\Coding\GitHub_Resuorse\emotion-robot\CLAUDE.md` | Claude Code workflow specifications, document reading order |

### 2.2 Backend Design Documents

| Document | Path | Purpose |
|------|------|------|
| **Backend Design** | `D:\Coding\GitHub_Resuorse\emotion-robot\docs\后端设计.md` | Technology selection, directory structure, module responsibilities, data flow design |
| **LLM Calling Layer Design Discussion** | `D:\Coding\GitHub_Resuorse\emotion-robot\docs\LLM调用层设计讨论.md` | Registry factory pattern, streaming interface, credential pool, error handling (Phase 2 design anchor) |
| **Memory System Design Discussion** | `D:\Coding\GitHub_Resuorse\emotion-robot\docs\记忆系统设计讨论.md` | L1/L3/L4 compression, mem0 integration, session management, recovery logic (Phase 3 design anchor) |
| **Backend API Documentation** | `D:\Coding\GitHub_Resuorse\emotion-robot\docs\后端API接口文档.md` | REST API specification, WebSocket protocol, data models, error handling |
| **Backend Execution Guidelines** | `D:\Coding\GitHub_Resuorse\emotion-robot\atri\执行准则.md` | Claude Code coding/commit/implementation workflow specifications |

### 2.3 Frontend Design Documents

| Document | Path | Purpose |
|------|------|------|
| **Frontend Design Document** | `D:\Coding\GitHub_Resuorse\emotion-robot\docs\前端设计文档.md` | Frontend architecture design (4007 lines, 15 chapters, condensed version): technology stack, component design, state management, 11 settings pages |
| **Frontend Design Discussion History** | `D:\Coding\GitHub_Resuorse\emotion-robot\docs\前端设计对话历史.md` | Complete frontend design discussion process (5465 lines, 18 rounds of dialogue, with code examples and configuration details) |
| **Frontend Discussion History Summary** | `D:\Coding\GitHub_Resuorse\emotion-robot\docs\总结_前端对话历史.md` | Structured summary of frontend design decisions (2060 lines, quick lookup) |
| **Phase X Division Discussion** | `D:\Coding\GitHub_Resuorse\emotion-robot\docs\Phase_X划分讨论.md` | Phase 6-10 division discussion (Rounds 13-18 contain frontend architecture discussion) |
| **Frontend Execution Guidelines** | `D:\Coding\GitHub_Resuorse\emotion-robot\atri-webui\执行准则.md` | Frontend development principles and specifications |

### 2.4 Module Design Documents

| Document | Path | Purpose |
|------|------|------|
| **ASR Module Design Document** | `D:\Coding\GitHub_Resuorse\emotion-robot\docs\ASR模块设计文档.md` | ASR module design (2814 lines, 15 chapters): 5 Providers, factory pattern, health check, streaming support |
| **TTS Module Design Document** | `D:\Coding\GitHub_Resuorse\emotion-robot\docs\TTS模块设计文档.md` | TTS module design (3276 lines, 15 chapters): 6 Providers, factory pattern, health check, VAD integration |
| **Live2D Design Document** | `D:\Coding\GitHub_Resuorse\emotion-robot\docs\Live-2d设计文档.md` | Live2D integration solution (15 chapters): rendering engine, expression control, model storage, frontend-backend responsibilities |

### 2.5 Reference Project Documents

| Document | Path | Purpose |
|------|------|------|
| **AIRI Architecture Document** | `D:\Coding\GitHub_Resuorse\emotion-robot\docs\projects-docs\airi_架构文档.md` | AIRI project architecture analysis (frontend UI + Live2D reference) |
| **OLV Architecture Document** | `D:\Coding\GitHub_Resuorse\emotion-robot\docs\projects-docs\OLV架构文档.md` | Open-LLM-VTuber architecture analysis (ASR/TTS factory pattern reference) |
| **Neuro Architecture Document** | `D:\Coding\GitHub_Resuorse\emotion-robot\docs\projects-docs\Neuro架构文档.md` | Neuro project architecture analysis (memory system reference) |
| **mem0 Architecture Document** | `D:\Coding\GitHub_Resuorse\emotion-robot\docs\projects-docs\mem0_架构文档.md` | mem0 long-term memory store architecture analysis |
| **AIRI vs atri Feature Comparison** | `D:\Coding\GitHub_Resuorse\emotion-robot\docs\projects-docs\AIRI与atri功能对比分析.md` | AIRI frontend features vs atri backend comparison, missing feature analysis |
| **AIRI Frontend Feature List** | `D:\Coding\GitHub_Resuorse\emotion-robot\docs\projects-docs\AIRI前端功能清单.md` | AIRI frontend feature implementation details |

---

## 3. Architecture Layering

### 3.1 Backend Layered Architecture

The backend uses a **layered modular architecture**, with clear responsibilities for each layer and modules interacting through interfaces.

```
+---------------------------------------------------------------+
|                    Service Layer (FastAPI)                      |
|  REST API + WebSocket + Routing + Lifecycle Management         |
|  See: docs/developments/module-design/EN/backend-API-documentation.md                                   |
+---------------------------------------------------------------+
                              |
                              v
+---------------------------------------------------------------+
|                      Agent Layer (ChatAgent)                    |
|  Combines LLM + Memory + Persona, handles main chat logic      |
|  See: docs/developments/module-design/EN/backend-design.md Section 2.5                              |
+---------------------------------------------------------------+
                              |
                              v
+---------------------------+------------------------------------+
|   Core Layer (LLM)        |   Memory Layer (RAG)               |
|   LLM calling + streaming |   L1/L3/L4 compression +           |
|   See: LLM Calling Layer  |   mem0 long-term memory            |
|                           |   See: Memory System Design        |
+---------------------------+------------------------------------+
                              |
                              v
+---------------------------------------------------------------+
|                    Storage Layer (Storage Abstraction)          |
|  ChatStorageInterface + JSONChatStorage                        |
+---------------------------------------------------------------+
                              |
                              v
+---------------------------+------------------------------------+
|  Input Layer (ASR)         |   Output Layer (TTS + Translation) |
|  Voice input (reserved)    |   Voice output + text translation  |
|  See: ASR Module Design    |   (reserved)                       |
|                           |   See: TTS Module Design Doc       |
+---------------------------+------------------------------------+
```

#### 3.1.1 Core Layer - LLM Calling Layer

**Responsibility**: Encapsulates LLM calling logic, providing unified streaming/non-streaming interfaces.

**Core Components**:
- `LLMInterface`: Abstract base class, defines the `chat_completion_stream` streaming interface
- `LLMFactory`: Registry factory, decorator-based Provider registration
- `openai_compatible`: MVP implementation, supporting OpenAI-compatible API

**Design Features**:
- Registry factory pattern: Providers self-register via `@LLMFactory.register("name")`
- Streaming-first: Subclasses only need to implement the streaming interface; non-streaming has a default implementation
- Credential pool + role mapping: `llm_configs` pool + `llm_roles` mapping with 3 outlets (chat/l3_compress/l4_compact)

**Detailed Design**: `D:\Coding\GitHub_Resuorse\emotion-robot\docs\LLM调用层设计讨论.md`

#### 3.1.2 Memory Layer - Memory System

**Responsibility**: Manages short-term memory (L1/L3/L4 compression) and long-term memory (mem0 RAG).

**Core Components**:
- `MemoryManager`: Orchestrates L1/L3/L4 compression + round counting + session lifecycle
- `ShortTermStore`: Short-term memory read/write (`short_term_memory.json`)
- `LongTermMemory`: mem0 integration wrapper (dual mode: sdk / local_deploy)
- `Compressor`: L3/L4 compression logic (calls LLM to generate summaries)
- `Snip`: L1 pure rule-based cleaning (filler word removal, consecutive duplicate deduplication)
- `ChatHistoryWriter`: chat_history.json read/write (append-only)

**Design Features**:
- **Three-layer compression**: L1 rule-based cleaning -> L3 single compression (20 rounds -> 1 block) -> L4 merge compression (4 blocks -> 1 meta_block)
- **Trigger scheduling**: `total_rounds % 26 == 0` triggers L3, `len(active_blocks) >= 4` triggers L4
- **mem0 integration**: L3 trigger synchronously calls `mem0.add(raw_20_rounds)`, each round calls `mem0.search(current_input)` before calling
- **Session recovery**: Uses `chat_history` as source of truth, validates `short_term_memory` consistency on recovery

**Detailed Design**: `D:\Coding\GitHub_Resuorse\emotion-robot\docs\记忆系统设计讨论.md`

#### 3.1.3 Agent Layer - Chat Agent

**Responsibility**: Combines LLM + Memory + Persona, handles main chat logic.

**Core Components**:
- `ChatAgent`: Streaming `chat()` + collecting `chat_collect()`, automatically calls `on_round_complete`
- `Persona`: Character definition in Markdown + frontmatter format
- `ServiceContext`: Manages multi-character lifecycle (lazy-loading cache + `close_all`)

**Design Features**:
- **Dual interface**: `chat()` streaming generator + `chat_collect()` default collecting implementation
- **Automatic memory**: After stream ends, automatically calls `mgr.on_round_complete(raw_user, reply)`
- **Error handling**: `LLMError` -> `append_system_note` writes `role=system` lines to chat_history, does not count rounds, does not trigger L3

**Detailed Design**: `D:\Coding\GitHub_Resuorse\emotion-robot\docs\后端设计.md` Section 2.5

#### 3.1.4 Service Layer - FastAPI Service

**Responsibility**: Provides REST API + WebSocket endpoints, manages service lifecycle.

**Core Components**:
- `app.py`: FastAPI application factory function + lifespan management
- `routes/`: Health check, character management, chat CRUD, WebSocket streaming dialogue
- `main.py`: Uvicorn server startup entry point

**Design Features**:
- **REST API**: `GET /health`, `GET /api/characters`, `POST /api/chats`, `GET /api/chats/{id}`, `POST /api/chats/{id}/update`, `POST /api/chats/{id}/delete`
- **WebSocket**: `/ws` streaming dialogue endpoint (`input:text` -> `output:chat:chunk` -> `output:chat:complete`)
- **CORS Support**: Allows frontend cross-origin access
- **LLM Title Generation**: Generates title based on first user message when creating a chat, falls back to first 20 characters on failure

**Detailed Design**: `D:\Coding\GitHub_Resuorse\emotion-robot\docs\后端API接口文档.md`

#### 3.1.5 Storage Layer - Storage Abstraction

**Responsibility**: Provides abstract interface for chat storage, supporting multiple storage backends.

**Core Components**:
- `ChatStorageInterface`: ABC defining 7 methods (create/get/list/update/delete/append_message/get_messages)
- `JSONChatStorage`: File persistence implementation (`{base_path}/{user_id}/{character_id}/index.json` + `sessions/{chat_id}.json`)
- `DatabaseChatStorage`: Database implementation skeleton (reserved for Phase 7)

**Design Features**:
- **Storage structure**: Character-scoped index (one `index.json` per character) + per-session message files
- **Atomic writes**: Uses `atomic_replace` to ensure write atomicity (Windows Defender friendly)

#### 3.1.6 Input/Output Layer - ASR/TTS (Reserved)

**ASR (Voice Input)**:
- **5 Providers**: faster_whisper, whisper_cpp, sherpa_onnx_asr, azure_asr, Web Speech API
- **Factory pattern**: Decorator-based registration (consistent with LLM)
- **Health check**: Interface layer defines `async def health_check() -> bool`
- **Detailed Design**: `D:\Coding\GitHub_Resuorse\emotion-robot\docs\ASR模块设计文档.md`

**TTS (Voice Output)**:
- **6 Providers**: edge_tts, cosyvoice2_tts, gpt_sovits_tts, siliconflow_tts, openai_tts, elevenlabs_tts
- **Factory pattern**: Decorator-based registration (consistent with LLM)
- **VAD integration**: Voice activity detection, optimizing silence handling
- **Detailed Design**: `D:\Coding\GitHub_Resuorse\emotion-robot\docs\TTS模块设计文档.md`

**Translation Module**:
- **Plugin-style design**: Independent text transformer, not a prerequisite layer for TTS
- **Consumer configuration**: `output text -> translate -> translated text`, downstream consumers (frontend/TTS/both) determined by configuration

### 3.2 Frontend Layered Architecture

The frontend uses a **standard Vue 3 layered architecture**: View Layer -> Component Layer -> State Layer -> Service Layer -> Transport Layer.

```
+---------------------------------------------------------------+
|                        View Layer (Pages)                       |
|  index.vue (main page) + settings/* (11 settings pages) +      |
|  login.vue                                                      |
+---------------------------------------------------------------+
                              |
                              v
+---------------------------------------------------------------+
|                       Component Layer (Components)              |
|  chat/ + sidebar/ + live2d/ + settings/ + ui/ (reusing AIRI)   |
+---------------------------------------------------------------+
                              |
                              v
+---------------------------------------------------------------+
|                       State Layer (Pinia Stores)                |
|  chatStore + chatsStore + charStore + userStore + wsStore      |
+---------------------------------------------------------------+
                              |
                              v
+---------------------------------------------------------------+
|                       Service Layer (Services)                  |
|  composables/ (useChat/useWebSocket/useLive2D) + api/          |
+---------------------------------------------------------------+
                              |
                              v
+---------------------------------------------------------------+
|                       Transport Layer (Transport)               |
|  HTTP (axios) + WebSocket (native API + exponential backoff    |
|  reconnection)                                                  |
+---------------------------------------------------------------+
                              |
                              v
+---------------------------------------------------------------+
|                     atri Backend (FastAPI)                       |
|  REST API + WebSocket                                           |
+---------------------------------------------------------------+
```

#### 3.2.1 View Layer (Pages)

**Responsibility**: Page-level components, defining routes and page layouts.

**Core Pages**:
- `index.vue`: Main page (dual mode: ChatGPT style when Live2D is off, AIRI style when on)
- `settings/*`: 11 settings pages (account/airi-card/consciousness/speech/hearing/vision/scene/models/providers/data/connection/system)
- `login.vue`: Login page (GitHub OAuth)

#### 3.2.2 Component Layer (Components)

**Responsibility**: Reusable UI components.

**Core Components**:
- `chat/`: ChatArea, InputBox, MessageItem, MessageList
- `sidebar/`: Sidebar, CharacterSelector, ChatHistory (Mode A exclusive)
- `live2d/`: Live2DCanvas, Live2DController, FoldPanel (Mode B exclusive)
- `settings/`: Sub-components for each settings page
- `ui/`: Basic UI components (Button/Input/Modal etc., reusing AIRI's @proj-airi/ui)

#### 3.2.3 State Layer (Pinia Stores)

**Responsibility**: Global state management.

**Core Stores**:
- `chatStore`: Current conversation state (message list, streaming accumulation)
- `chatsStore`: Conversation list (chat history, CRUD operations)
- `charStore`: Character management (character list, current character)
- `userStore`: User authentication (login state, user info)
- `wsStore`: WebSocket connection (connection state, reconnection logic)
- `settStore`: Settings preferences (Live2D toggle, background settings, theme)

#### 3.2.4 Service Layer (Services)

**Responsibility**: Business logic encapsulation and API calls.

**Composables**:
- `useChat.ts`: Chat logic (send message, streaming receive)
- `useWebSocket.ts`: WebSocket management (connection, reconnection, message handling)
- `useLive2D.ts`: Live2D control (model loading, expression switching)
- `useBackground.ts`: Background management (image upload, opacity adjustment)

**API Wrappers**:
- `client.ts`: axios instance configuration
- `characters.ts`: Character API (GET /api/characters)
- `chats.ts`: Chat API (POST /api/chats, GET /api/chats/{id})
- `tts.ts` / `asr.ts`: Voice API (reserved)
- `live2d.ts`: Live2D API (reserved)
- `auth.ts`: Authentication API (GitHub OAuth)
- `data.ts`: Data management API (export/import/clear)

#### 3.2.5 Transport Layer (Transport)

**Responsibility**: Communication with the backend.

**HTTP (axios)**:
- REST API calls (GET/POST requests)
- Request interceptor (add token)
- Response interceptor (error handling)

**WebSocket**:
- Native WebSocket API
- Exponential backoff reconnection (up to 5 retries, intervals 1s/2s/4s/8s/16s)
- Message protocol: `input:text` -> `output:chat:chunk` -> `output:chat:complete`

**Detailed Design**: `D:\Coding\GitHub_Resuorse\emotion-robot\docs\前端设计文档.md`

---

## 4. Core Data Flow

### 4.1 Backend Core Data Flow

**ChatAgent + LLM calling + Memory system + raw input**

```
raw user text (text / ASR)
     |
     v
+------------------- ChatAgent (src/agent/chat_agent.py) -------------------+
|  Composition layer: holds persona + LLMInterface(role=chat) +              |
|  MemoryManager                                                              |
|                                                                             |
|  (1) messages = await mgr.build_llm_context(raw, persona)                  |
|         +-> MemoryManager internally assembles 6-segment payload            |
|            (Section 3.5 order):                                            |
|            [1] system=persona                                              |
|            [2] long-term facts = search_long_term(raw) -> mem0.search(...) |
|            [3] meta_blocks (cleaned)                                       |
|            [4] active_blocks (cleaned)                                     |
|            [5] recent_messages (cleaned)                                   |
|            [6] current round user_input (raw, as-is)                       |
|                                                                             |
|  (2) async for chunk in llm.chat_completion_stream(messages):              |
|         yield chunk  (LLM native language text, e.g. zh)                   |
|            +-> frontend plugin       (consumes LLM original text by        |
|            |                          default)                              |
|            +-> translation module    (optionally enabled: output text ->    |
|            |   plugin                translate -> translated text;          |
|            |                          downstream consumers = frontend /     |
|            |                          TTS / both)                           |
|            +-> TTS module plugin     (optionally enabled; consumption      |
|                                       source = LLM original text /         |
|                                       translation module output,           |
|                                       determined by configuration)         |
|                                                                             |
|  (3) After stream ends, automatically calls:                               |
|         mgr.on_round_complete(raw_user, reply)                             |
|         +-> MemoryManager internally:                                      |
|            |+ L1 snip(user)          -> cleaned                            |
|            |+ chat_history.append    (cleaned + optional raw_input)        |
|            |+ recent_messages +=     (cleaned, reply)                      |
|            |+ total_rounds % 26 == 0 -> L3 Collapse + mem0.add             |
|            + active_blocks >= 4      -> L4 Super-Compact                   |
+---------------------------------------------------------------------------+
```

**Key Path Description**:
1. **Context Construction**: `build_llm_context` assembles the 6-segment payload in strict order (system -> long-term facts -> meta -> active -> recent -> current round input)
2. **Streaming Output**: LLM native language text (e.g. Chinese) is returned via `yield chunk`
3. **Downstream Consumption**: Frontend/translation/TTS are all independent plugin-style modules, with enable/disable and consumption source determined by configuration
4. **Automatic Memory**: After stream ends, `on_round_complete` is automatically triggered, executing L1 cleaning -> writing to chat_history -> checking L3/L4 trigger conditions

### 4.2 Memory System Data Flow

```
User input (text / ASR, raw text)
  |
  v
ChatAgent (Phase 4 composition layer)
  |  Holds: persona + LLMInterface(role=chat) + MemoryManager
  |
  +-- (1) await mgr.build_llm_context(raw user_input, persona)
  |        |
  |        v Internally assembles payload (strictly in Section 3.5 order):
  |        +--------------------------------------------------------+
  |        | [1] system                : persona                     |
  |        | [2] long-term facts       : search_long_term(raw)       |
  |        |     +-> mem0.search(query=raw, user_id, agent_id)      |
  |        |        -> wrapped "About this user, you remember:       |
  |        |           \n- ..."                                      |
  |        | [3] meta_blocks   (cleaned; L4 output)                  |
  |        | [4] active_blocks (cleaned; L3 output)                  |
  |        | [5] recent_messages (cleaned; Section 3.2 valid rounds) |
  |        | [6] current round user_input (raw, as-is passthrough)   |
  |        +--------------------------------------------------------+
  |
  +-- (2) async for chunk in llm.chat_completion_stream(messages):
  |        yield chunk   (LLM native language text, e.g. zh)
  |            |
  |            v Downstream consumers (all independent plugin-style modules,
  |              enable/disable + consumption source determined by config):
  |            +-> Frontend (consumes LLM original text by default;
  |            |              can be configured to consume translated text)
  |            +-> Translation module (optionally enabled; form:
  |            |   output text -> translate -> translated;
  |            |              when enabled, its downstream consumers =
  |            |              frontend / TTS / both, determined by config)
  |            +-> TTS module (optionally enabled; consumption source =
  |                               LLM original text / translated text,
  |                               determined by config)
  |
  v Stream ends (all chunks merged into reply)
  |
  +-- (3) await mgr.on_round_complete(
             user_msg={role:"human", content: raw, raw_input: ASR original?},
             ai_msg  ={role:"ai",    content: reply},
         )   <- ChatAgent automatically calls (S1b decision)
          |
          v MemoryManager.on_round_complete internally:
          |
          +-- L1 Snip (only applied to user_msg; AI reply untouched)
          |   -> cleaned_user
          |
          +-- chat_history.append_human(cleaned.content, raw_input=raw_input?)
          +-- chat_history.append_ai(reply)
          |     (error rounds S4 use append_system_note instead of append_ai)
          |
          +-- recent_messages += [{human: cleaned}, {ai: reply}]
          |
          +-- total_rounds++ (only when _is_valid_round: content non-empty &
          |                    does not start with "Error"; Section 3.2)
          |
          +-- Check total_rounds % 26 == 0?
          |     +-- Yes -> L3 Collapse
          |              +-> Earliest 20 rounds cleaned -> compression LLM ->
          |              |   block -> active_blocks
          |              +-> Same window -> long_term.add()
          |                 v mem0 internally calls LLM to extract facts ->
          |                   fact sentence embeddings indexed
          |
          +-- Check active_blocks >= 4?
                +-- Yes -> L4 Super-Compact
                         +-> 4 blocks -> compression LLM -> meta_block ->
                             meta_blocks
```

**Key Path Description**:
1. **Context Construction**: 6-segment payload assembled in strict order, long-term facts retrieved via `mem0.search(raw)`
2. **L1 Cleaning**: Only applied to user messages (filler word removal, consecutive duplicate deduplication, overlength truncation); AI reply untouched
3. **Round Counting**: Only valid rounds (content non-empty & does not start with "Error") count toward `total_rounds`
4. **L3 Trigger**: Triggered every 26 rounds, earliest 20 rounds -> compression LLM -> block -> `active_blocks`, while calling `mem0.add()` to write to long-term memory
5. **L4 Trigger**: Triggered when `active_blocks` accumulates to 4, 4 blocks -> compression LLM -> meta_block -> `meta_blocks`
6. **Session Recovery**: Uses `chat_history` as source of truth, validates `short_term_memory` consistency on recovery; if JSON is corrupted, fully rebuilds from `chat_history`

**Detailed Design**: `D:\Coding\GitHub_Resuorse\emotion-robot\docs\记忆系统设计讨论.md`

---

## 5. Project Directory Structure

### 5.1 Backend Directory Structure

```
atri/                              # Backend project root
├── config.yaml                    # Root config entry (path references sub-files)
├── config/
│   ├── llm_config.yaml            # LLM credential pool + role mapping
│   ├── memory_config.yaml         # Memory system configuration
│   ├── server_config.yaml         # Server configuration (host/port/cors)
│   ├── storage_config.yaml        # Storage configuration (mode: json/database)
│   ├── asr_config.yaml            # ASR configuration (reserved)
│   ├── tts_config.yaml            # TTS configuration (reserved)
│   └── translate_config.yaml      # Translation configuration (reserved)
├── src/
│   ├── main.py                    # Uvicorn server startup entry point
│   ├── app.py                     # FastAPI application factory function
│   ├── service_context.py         # Service context (manages all engine instances)
│   │
│   ├── llm/                       # === Core Layer: LLM Calling Layer ===
│   │   ├── interface.py           # LLMInterface abstract base class
│   │   ├── factory.py             # LLMFactory registry
│   │   ├── exceptions.py          # LLMError exception hierarchy
│   │   └── providers/
│   │       └── openai_compatible.py  # OpenAI-compatible Provider
│   │
│   ├── memory/                    # === Memory Layer: Memory System ===
│   │   ├── manager.py             # MemoryManager (orchestrates L1/L3/L4)
│   │   ├── short_term.py          # Short-term memory read/write
│   │   ├── long_term.py           # Long-term memory (mem0 integration)
│   │   ├── compressor.py          # L3/L4 compression logic
│   │   ├── snip.py                # L1 Snip pure rule-based cleaning
│   │   ├── chat_history.py        # chat_history.json read/write
│   │   └── _io_utils.py           # atomic_replace (Windows friendly)
│   │
│   ├── agent/                     # === Agent Layer: Chat Agent ===
│   │   ├── chat_agent.py          # ChatAgent (combines LLM + Memory)
│   │   └── persona.py             # Persona dataclass + parser
│   │
│   ├── storage/                   # === Storage Layer: Storage Abstraction ===
│   │   ├── interface.py           # ChatStorageInterface ABC
│   │   ├── factory.py             # create_chat_storage factory function
│   │   ├── json_storage.py        # JSONChatStorage implementation
│   │   └── database_storage.py    # DatabaseChatStorage skeleton
│   │
│   ├── routes/                    # === Service Layer: FastAPI Routes ===
│   │   ├── health.py              # GET /health health check
│   │   ├── characters.py          # GET /api/characters character management
│   │   ├── chats.py               # Chat CRUD REST API
│   │   └── chat_ws.py             # WebSocket /ws streaming dialogue
│   │
│   ├── asr/                       # === Input Layer: ASR (Reserved) ===
│   │   ├── interface.py
│   │   ├── factory.py
│   │   └── providers/
│   │
│   ├── tts/                       # === Output Layer: TTS (Reserved) ===
│   │   ├── interface.py
│   │   ├── factory.py
│   │   └── providers/
│   │
│   ├── translate/                 # === Translation Module (Reserved) ===
│   │   ├── interface.py
│   │   └── factory.py
│   │
│   └── utils/
│       ├── config_loader.py       # Layered config loading
│       └── logger.py              # Logging configuration
│
├── data/                          # Runtime data
│   ├── characters/                # Memory system data (Phase 3)
│   │   └── atri/
│   │       ├── sessions/          # chat_history JSON files
│   │       └── short_term_memory.json
│   └── chats/                     # Chat storage data (Phase 5)
│       └── default/               # user_id=default
│           └── atri/              # character_id=atri
│               ├── index.json     # Chat list index
│               └── sessions/      # Chat session messages
│
├── prompts/                       # Prompt templates
│   ├── compress/                  # Compression prompts (Phase 3)
│   │   ├── l3_collapse.txt
│   │   └── l4_super_compact.txt
│   ├── persona/                   # Character personas (Phase 4)
│   │   └── atri.md
│   └── prompt_loader.py           # Prompt loader
│
├── logs/                          # Log output
├── 执行准则.md                     # Claude Code workflow specifications
├── tests/                         # Test suite
│   ├── utils/
│   ├── llm/
│   ├── memory/
│   ├── agent/
│   ├── storage/
│   └── routes/
├── pyproject.toml                 # Project configuration + dependencies
├── uv.lock                        # Dependency lock file
└── README.md                      # Project description
```

### 5.2 Frontend Directory Structure

```
atri-webui/                        # Frontend project root
├── public/                        # Static assets
│   └── favicon.ico
├── src/
│   ├── main.ts                    # Application entry point
│   ├── App.vue                    # Root component
│   ├── router/
│   │   └── index.ts               # Route configuration
│   │
│   ├── pages/                     # === View Layer ===
│   │   ├── index.vue              # Main page (dual mode)
│   │   ├── login.vue              # Login page
│   │   └── settings/              # Settings pages (11)
│   │       ├── index.vue          # Settings home
│   │       ├── account.vue        # Account settings
│   │       ├── airi-card.vue      # AIRI card
│   │       ├── consciousness.vue  # Consciousness settings (LLM)
│   │       ├── speech.vue         # Speech settings (TTS)
│   │       ├── hearing.vue        # Hearing settings (ASR)
│   │       ├── vision.vue         # Vision settings
│   │       ├── scene.vue          # Scene settings
│   │       ├── models.vue         # Model management
│   │       ├── providers.vue      # Provider configuration
│   │       ├── data.vue           # Data management
│   │       ├── connection.vue     # Connection settings
│   │       └── system.vue         # System settings
│   │
│   ├── components/                # === Component Layer ===
│   │   ├── ui/                    # Basic UI components (reusing AIRI)
│   │   │   ├── Button.vue
│   │   │   ├── Input.vue
│   │   │   ├── Modal.vue
│   │   │   └── ...
│   │   ├── chat/                  # Chat components
│   │   │   ├── ChatArea.vue
│   │   │   ├── InputBox.vue
│   │   │   ├── MessageItem.vue
│   │   │   └── MessageList.vue
│   │   ├── sidebar/               # Sidebar components (Mode A)
│   │   │   ├── Sidebar.vue
│   │   │   ├── CharacterSelector.vue
│   │   │   └── ChatHistory.vue
│   │   ├── live2d/                # Live2D components (Mode B)
│   │   │   ├── Live2DCanvas.vue
│   │   │   ├── Live2DController.vue
│   │   │   └── FoldPanel.vue      # Fold panel (history + characters)
│   │   └── layouts/               # Layout components
│   │       ├── ChatGPTLayout.vue  # Mode A layout
│   │       └── AIRILayout.vue     # Mode B layout
│   │
│   ├── stores/                    # === State Layer (Pinia) ===
│   │   ├── chat.ts                # Current conversation state
│   │   ├── chats.ts               # Conversation list
│   │   ├── characters.ts          # Character management
│   │   ├── user.ts                # User authentication
│   │   ├── websocket.ts           # WebSocket connection
│   │   └── settings.ts            # Settings preferences
│   │
│   ├── composables/               # === Service Layer: Composables ===
│   │   ├── useChat.ts             # Chat logic
│   │   ├── useWebSocket.ts        # WebSocket management
│   │   ├── useLive2D.ts           # Live2D control
│   │   └── useBackground.ts       # Background management
│   │
│   ├── api/                       # === Service Layer: API Wrappers ===
│   │   ├── client.ts              # axios instance
│   │   ├── types.ts               # API type definitions
│   │   ├── characters.ts          # Character API
│   │   ├── chats.ts               # Chat API
│   │   ├── tts.ts                 # TTS API (reserved)
│   │   ├── asr.ts                 # ASR API (reserved)
│   │   ├── live2d.ts              # Live2D API (reserved)
│   │   ├── auth.ts                # Authentication API
│   │   └── data.ts                # Data management API
│   │
│   ├── types/                     # TypeScript types
│   │   ├── chat.ts
│   │   ├── character.ts
│   │   ├── websocket.ts
│   │   └── settings.ts
│   │
│   ├── utils/                     # Utility functions
│   │   ├── websocket.ts           # WebSocketManager
│   │   └── storage.ts             # LocalStorage wrapper
│   │
│   ├── styles/                    # Global styles (reusing AIRI)
│   │   ├── theme.css
│   │   └── global.css
│   │
│   └── assets/                    # Static assets
│
├── package.json
├── vite.config.ts
├── tsconfig.json
├── uno.config.ts                  # UnoCSS configuration (reusing AIRI)
├── 执行准则.md                     # Frontend development execution guidelines
└── README.md                      # Project description
```

---

## 6. Interface Design

### 6.1 Backend Interfaces

The backend provides both **REST API** and **WebSocket** interfaces.

**REST API Overview**:

| Category | Endpoint | Method | Description |
|------|------|------|------|
| **Health Check** | `/health` | GET | Service health status |
| **Character Management** | `/api/characters` | GET | Get character list |
| | `/api/characters/{character_id}` | GET | Get character details |
| **Chat Management** | `/api/chats` | GET | Get chat list |
| | `/api/chats` | POST | Create new chat |
| | `/api/chats/{chat_id}` | GET | Get chat details |
| | `/api/chats/{chat_id}/update` | POST | Update chat title |
| | `/api/chats/{chat_id}/delete` | POST | Delete chat |
| **Real-time Dialogue** | `/ws` | WebSocket | Streaming dialogue |

**WebSocket Protocol**:
- **Client -> Server**: `{"type": "input:text", "content": "user message", "chat_id": "...", "character_id": "..."}`
- **Server -> Client**:
  - Streaming message: `{"type": "output:chat:chunk", "content": "text fragment"}`
  - Complete message: `{"type": "output:chat:complete"}`
  - Error message: `{"type": "error", "message": "error message"}`

**Detailed Documentation**: `D:\Coding\GitHub_Resuorse\emotion-robot\docs\后端API接口文档.md`

### 6.2 Frontend Interfaces

Frontend interfaces mainly include **Component Interfaces**, **Store Interfaces**, and **Composables Interfaces**.

**Core Store Interfaces**:
- `chatStore`: `messages`, `addMessage`, `clearMessages`, `appendChunk`
- `chatsStore`: `chats`, `createChat`, `deleteChat`, `updateChat`, `fetchChats`
- `charStore`: `characters`, `currentCharacter`, `setCharacter`, `fetchCharacters`
- `userStore`: `user`, `isAuthenticated`, `login`, `logout`
- `wsStore`: `isConnected`, `connect`, `disconnect`, `send`, `onMessage`
- `settStore`: `live2dEnabled`, `background`, `theme`, `updateSettings`

**Core Composables Interfaces**:
- `useChat()`: `sendMessage`, `messages`, `isStreaming`
- `useWebSocket()`: `connect`, `disconnect`, `send`, `onMessage`, `isConnected`
- `useLive2D()`: `loadModel`, `setExpression`, `models`
- `useBackground()`: `uploadImage`, `setOpacity`, `setBlur`

**Detailed Documentation**: `D:\Coding\GitHub_Resuorse\emotion-robot\docs\前端设计文档.md`

---

## Appendix

### A. Key Design Decisions

| Decision | Content | Document Link |
|------|------|---------|
| **Architecture Pattern** | Centralized architecture (backend manages configuration, API keys not exposed to frontend) | `docs/developments/module-design/EN/frontend-design.md` Section 1.1 |
| **Factory Pattern** | Decorator-based registration (unified pattern for LLM/ASR/TTS) | `docs/developments/module-design/EN/LLM-calling-layer-design.md` Section 2.1 |
| **Memory System** | L1/L3/L4 three-layer compression + mem0 long-term memory | `docs/developments/module-design/EN/memory-system-design.md` |
| **Session Recovery** | chat_history as source of truth, lightweight validation approach | `docs/developments/module-design/EN/memory-system-design.md` Section 8.5 |
| **Streaming Interface** | Subclasses only implement streaming, non-streaming has default implementation | `docs/developments/module-design/EN/LLM-calling-layer-design.md` Section 2.2 |
| **Error Handling** | Interface layer only raises exceptions, caller decides retry strategy | `docs/developments/module-design/EN/LLM-calling-layer-design.md` Section 2.6 |
| **WebSocket Reconnection** | Exponential backoff, up to 5 retries | `docs/developments/module-design/EN/frontend-design.md` Section 7.2 |
| **Live2D Integration** | Fully reuses AIRI's pixi-live2d-display package | `docs/developments/module-design/EN/Live2D-design.md` |

### B. Reference Projects

| Project | Reference Value | Document Link |
|------|---------|---------|
| **AIRI** | Frontend UI + Live2D implementation | `docs/projects-docs/airi_架构文档.md` |
| **Open-LLM-VTuber** | ASR/TTS factory pattern + FastAPI architecture | `docs/projects-docs/OLV架构文档.md` |
| **Neuro** | Reflective memory system | `docs/projects-docs/Neuro架构文档.md` |
| **mem0** | Long-term memory foundation + v3 ADD-only algorithm | `docs/projects-docs/mem0_架构文档.md` |
