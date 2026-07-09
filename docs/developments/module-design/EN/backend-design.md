# Backend Project Architecture and Directory Structure Design

> Legacy design note:
> Prefer the current implementation docs under [../../project-architecture-design.en.md](../../project-architecture-design.en.md), [../../modules/README.zh-CN.md](../../modules/README.zh-CN.md), and [../../modules/routes/README.zh-CN.md](../../modules/routes/README.zh-CN.md).
> This file is kept as historical design source and migration reference, not as the authoritative entry point for the current implementation.

> **Project**: emotion-robot
> **Created**: 2026-04-18
> **Status**: Finalized
> **Related Documents**: LLM Calling Layer Design Discussion.md, Memory System Design Discussion.md

---

## 1. Technology Selection

### 1.1 Backend Framework: FastAPI

**Decision:** Use FastAPI + Uvicorn as the backend framework.

**Reference Project Comparison:**

| Project | Language | Backend Framework | Communication |
|------|------|----------|----------|
| OLV | Python | FastAPI + Uvicorn | WebSocket + REST |
| Neuro | Python | No framework (pure Python) | Socket.IO |
| airi | TypeScript | Hono + crossws | WebSocket + HTTP |

**Reasons for choosing FastAPI:**
- Native async — LLM streaming output and mem0 calls are both asynchronous
- WebSocket support — needed for future voice streaming (ASR/TTS)
- Auto-generated API documentation (Swagger UI) — convenient for debugging
- OLV has already validated this approach
- Python ecosystem — naturally compatible with mem0, openai SDK, and various ASR/TTS libraries

### 1.2 Python Version + Dependency Management: Python 3.11+ / uv

**Decision:** Python 3.11+, using uv for dependency and version management.

**Reasons for Python 3.11+:**
- 10-60% performance improvement over 3.10 (CPython optimizations)
- `tomllib` built-in (no extra dependency needed to read pyproject.toml)
- `asyncio.TaskGroup` available (more elegant concurrent task management)
- mem0 supports 3.9~3.12, FastAPI supports 3.8+, both are compatible

**Reasons for uv:**
- Validated by OLV (`uv sync` one-click install)
- Rust implementation, 10-100x faster than pip
- Compatible with pip ecosystem, `pyproject.toml` + `uv.lock`
- Also manages Python versions (`uv python install 3.11`)

**Project initialization commands:**
```bash
uv init emotion-robot
uv python pin 3.11
uv add fastapi uvicorn loguru pyyaml openai mem0ai
```

**Deployment plan:** Use uv for management during development, add docker-compose one-click deployment after project completion. Docker configuration is not within the MVP scope.

### 1.3 Frontend: Separate Repository

**Decision:** The frontend is a separate repository, not included in the backend project.

**Reasons:**
- Backend is Python (FastAPI), frontend can use any technology stack (planning to follow airi's Vue implementation)
- Independent deployment, independent version management
- Communicates via WebSocket + REST API, with clear interfaces
- OLV also has a separate frontend (Git submodule), validating this pattern works

---

## 2. Project Directory Structure

### 2.1 Mapping to readme Layers

| readme Layer | Directory Module | Status |
|---|---|---|
| 4.1 Core Layer: LLM Calling | `src/llm/` | MVP implemented (Phase 2) |
| 4.2 Memory Layer: RAG system | `src/memory/` | MVP implemented (Phase 3) |
| 4.3 Output Layer: TTS + Text | `src/tts/` | Reserved |
| 4.4 Input Layer: ASR + Text | `src/asr/` | Reserved |
| 4.5 Frontend Layer | Separate repository | Later |
| (Translation module) | `src/translate/` | Reserved |
| (Chat Agent composition layer) | `src/agent/` | MVP implemented (Phase 4) |
| (FastAPI service layer) | `src/app.py` + `src/routes/` | MVP implemented (Phase 5) |
| (Storage abstraction layer) | `src/storage/` | MVP implemented (Phase 5) |

### 2.2 Complete Directory Structure

```
atri/                              # Project repository root
├── config.yaml                    # Root config entry (path references to sub-files)
├── config/
│   ├── llm_config.yaml            # LLM credential pool + role mapping (LLM Design Doc section 2.5)
│   ├── memory_config.yaml         # Memory system config (Memory Design Doc section 7)
│   ├── server_config.yaml         # Server config (Phase 5)
│   ├── storage_config.yaml        # Storage config (Phase 5)
│   ├── asr_config.yaml            # ASR config (reserved)
│   ├── tts_config.yaml            # TTS config (reserved)
│   └── translate_config.yaml      # Translation config (reserved)
├── src/
│   ├── main.py                    # Uvicorn server entry point (Phase 5)
│   ├── app.py                     # FastAPI application factory function (Phase 5)
│   ├── service_context.py         # Service context (manages lifecycle of all engine instances)
│   │
│   ├── llm/                       # === Core Layer: LLM Calling Layer (Phase 2) ===
│   │   ├── interface.py           # LLMInterface abstract base class (streaming + non-streaming)
│   │   ├── factory.py             # LLMFactory registry
│   │   ├── exceptions.py          # LLMError exception hierarchy
│   │   └── providers/
│   │       └── openai_compatible.py  # MVP implementation
│   │
│   ├── memory/                    # === Memory Layer: Memory System (Phase 3) ===
│   │   ├── manager.py             # Memory Manager (orchestrates L1/L3/L4 + round counting)
│   │   ├── short_term.py          # Short-term memory read/write (short_term_memory.json)
│   │   ├── long_term.py           # Long-term memory (mem0 integration wrapper)
│   │   ├── compressor.py          # L3/L4 compression logic (calls LLM to generate summaries)
│   │   ├── snip.py                # L1 Snip pure rule-based cleaning
│   │   ├── chat_history.py        # chat_history.json read/write
│   │   └── _io_utils.py           # atomic_replace (Windows-friendly)
│   │
│   ├── agent/                     # === Chat Agent Composition Layer (Phase 4) ===
│   │   ├── chat_agent.py          # Composes LLM + Memory, handles main chat logic
│   │   └── persona.py             # Persona dataclass + markdown frontmatter parsing
│   │
│   ├── storage/                   # === Storage Abstraction Layer (Phase 5) ===
│   │   ├── interface.py           # ChatStorageInterface ABC
│   │   ├── factory.py             # create_chat_storage factory function
│   │   ├── json_storage.py        # JSONChatStorage implementation
│   │   └── database_storage.py    # DatabaseChatStorage skeleton (Phase 7)
│   │
│   ├── routes/                    # === FastAPI Routes (Phase 5) ===
│   │   ├── health.py              # GET /health health check
│   │   ├── characters.py          # GET /api/characters character management
│   │   ├── chats.py               # Chat CRUD REST API
│   │   └── chat_ws.py             # WebSocket /ws streaming conversation endpoint
│   │
│   ├── asr/                       # === Input Layer: ASR (reserved) ===
│   │   ├── interface.py
│   │   ├── factory.py
│   │   └── providers/
│   │
│   ├── tts/                       # === Output Layer: TTS (reserved) ===
│   │   ├── interface.py
│   │   ├── factory.py
│   │   └── providers/
│   │
│   ├── translate/                 # === Translation Module (reserved) ===
│   │   ├── interface.py
│   │   └── factory.py
│   │
│   └── utils/
│       ├── config_loader.py       # Layered config loading (LLM Design Doc section 2.5)
│       └── logger.py              # Logging configuration
│
├── data/                          # Runtime data (memory system + chat storage)
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
├── execution_guidelines.md        # Claude Code workflow specification
├── tests/                         # Test suite
│   ├── utils/
│   ├── llm/
│   ├── memory/
│   ├── agent/
│   ├── storage/
│   └── routes/
```

### 2.3 Inter-module Dependencies

```
service_context.py (top-level orchestration)
  ├── llm/factory.py        -> Creates LLM instances for each outlet
  ├── memory/manager.py     -> Injects LLM instances for L3/L4 + mem0 config
  ├── agent/chat_agent.py   -> Injects main chat LLM instance + Memory Manager
  ├── asr/factory.py        -> Creates ASR instances (reserved)
  └── tts/factory.py        -> Creates TTS instances (reserved)

agent/chat_agent.py
  ├── Depends on llm/interface.py (main chat LLM)
  └── Depends on memory/manager.py (memory management)

memory/manager.py
  ├── Depends on llm/interface.py (LLM for L3/L4 compression)
  ├── Depends on memory/short_term.py
  ├── Depends on memory/long_term.py (mem0)
  ├── Depends on memory/compressor.py
  └── Depends on memory/snip.py (L1)
```

### 2.4 Design Principles

- **Each module follows the same three-layer structure**: `interface.py` (abstract base class) -> `providers/` (concrete implementations) -> `factory.py` (registry factory)
- **Modules depend on interfaces**: `chat_agent` depends on `LLMInterface`, not on the concrete `OpenAICompatibleLLM`
- **Configuration separated from code**: All configurable items are in YAML files under `config/`, no hardcoding in code
- **Reserved modules only have skeletons**: ASR/TTS/translate only create `interface.py` and `factory.py`, no implementation code

### 2.5 Core Data Flow (ChatAgent + LLM Calling + Memory System + Raw Input)

> **Supplementary note (2026-04-19)**: This section clarifies the collaboration between the four parties after Phase 4 introduced `ChatAgent`.
> Detailed step-by-step diagrams can be found in `docs/developments/module-design/EN/memory-system-design.md` section 6.1.

**Main response path**:

```
raw user text (text / ASR)
     |
     v
+------------------------ ChatAgent (src/agent/chat_agent.py) ------------------------+
|  Composition layer: holds persona + LLMInterface(role=chat) + MemoryManager        |
|                                                                                      |
|  (1) messages = await mgr.build_llm_context(raw, persona)                            |
|         +-> MemoryManager internally assembles 6-segment payload (section 3.5 order):|
|            [1] system=persona                                                        |
|            [2] long-term facts = search_long_term(raw) -> mem0.search(...)           |
|            [3] meta_blocks (cleaned)                                                 |
|            [4] active_blocks (cleaned)                                               |
|            [5] recent_messages (cleaned)                                             |
|            [6] this round's user_input (raw, as-is)                                  |
|                                                                                      |
|  (2) async for chunk in llm.chat_completion_stream(messages):                        |
|         yield chunk  (LLM native language text, e.g. zh)                             |
|            +-> Frontend plugin       (consumes LLM raw text by default)              |
|            +-> Translation module plugin (optional: output text ->                   |
|            |                     translate -> translated text;                        |
|            |                     downstream consumers = frontend / TTS / both)        |
|            +-> TTS module plugin    (optional; consumption source = LLM raw text /   |
|                                      translation module output, configured)          |
|                                                                                      |
|  (3) After stream ends, automatically calls: mgr.on_round_complete(raw_user, reply)  |
|         +-> MemoryManager internally:                                                |
|            + L1 snip(user)          -> cleaned                                       |
|            + chat_history.append    (cleaned + optional raw_input)                   |
|            + recent_messages +=     (cleaned, reply)                                 |
|            + total_rounds % 26 == 0 -> L3 Collapse + mem0.add                       |
|            + active_blocks >= 4     -> L4 Super-Compact                              |
+--------------------------------------------------------------------------------------+
```

**Responsibility boundaries of the four parties**:

| Module | Dependencies | Called By | Responsibilities |
|------|------|---------|--------|
| **raw input text** | Upstream (Phase 5 FastAPI WS / CLI / other entry points) | -- | Raw text string, enters `ChatAgent.chat()` |
| **ChatAgent** (`src/agent/`) | `LLMInterface` + `MemoryManager` + `persona` | Upstream entry point | Composition layer -- assembles payload -> calls LLM -> distributes stream -> commits round |
| **LLM calling** (`src/llm/`) | None (stateless interface) | ChatAgent (main chat role=chat) + MemoryManager (L3/L4 compression role=l3_compress / l4_compact) | Streaming + non-streaming text generation; interface layer only throws exceptions |
| **Memory system** (`src/memory/`) | `LLMInterface` (for compression) + `mem0` | ChatAgent (build_llm_context / on_round_complete / search_long_term / append_system_note) | L1/L3/L4 compression + chat_history archiving + short/long-term memory management |

**Pluggable plugin modules (bypass consumers of LLM stream)**:

| Plugin | Enable/Disable | Consumption Source | Location | Affects Memory System? |
|--------|------|--------|------|---------------|
| Frontend | Upstream decision | LLM raw text (default) / translation output (configurable) | Upstream | No |
| Translation Module | Config toggle | LLM raw text -> translated text | `src/translate/` (reserved) | No (not stored in chat_history) |
| TTS | Config toggle | LLM raw text / translation output (configurable) | `src/tts/` (reserved) | No |

**Key constraints**:
- **L1 position**: **Internal step** of `MemoryManager.on_round_complete`, not an independent entry layer. ChatAgent passes through raw user_input, MemoryManager handles L1 internally. This keeps LLM position [6] as raw (fresh for current round), while chat_history / recent_messages / mem0 index are all cleaned (consistent across rounds).
- **Translation module != TTS prerequisite**: The translation module is an independent transformer applied to LLM output text. Downstream consumers (frontend / TTS / both) are determined by configuration; the translation module itself does not know who consumes it.
- **chat_history language immutability**: Regardless of frontend / translation / TTS configuration, chat_history always records LLM native language, ensuring language consistency for memory / compression / recovery.
- **Error path**: LLM throws `LLMError` -> ChatAgent yields error text to caller + calls `mgr.append_system_note(...)` to write a `role=system` line to chat_history, not counted as a round, not triggering L3, not added to recent_messages.

---

## 3. Logging Solution

### 3.1 Technology Selection: loguru

**Decision:** Follow OLV's logging approach -- loguru + console/file dual output.

**Why loguru instead of standard logging:**
- Zero configuration: `from loguru import logger` and you're ready to go, no need for the tedious setup of `getLogger` / `Handler` / `Formatter`
- Automatic colorization, automatic exception stack formatting
- `logger.catch` decorator can automatically capture and log function exceptions
- OLV has validated this approach in similar projects

### 3.2 Logging Configuration

```python
# src/utils/logger.py
import sys
from loguru import logger

def init_logger(console_log_level: str = "INFO") -> None:
    logger.remove()  # Remove default handler

    # Console output (with color)
    logger.add(
        sys.stderr,
        level=console_log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "{message}",
        colorize=True,
    )

    # File output (with milliseconds + extra fields)
    logger.add(
        "logs/debug_{time:YYYY-MM-DD}.log",
        rotation="10 MB",
        retention="30 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
               "{name}:{function}:{line} | {message} | {extra}",
        backtrace=True,
        diagnose=True,
    )
```

### 3.3 Output Examples

**Console (INFO level, with color):**
```
2026-04-18 02:37:24 | INFO     | llm.factory:create:42 | Creating LLM: openai_compatible
2026-04-18 02:37:25 | INFO     | memory.manager:on_round:88 | Round 26: triggering L3 compress
2026-04-18 02:37:30 | WARNING  | memory.long_term:add:55 | mem0.add() failed, will retry on session close
```

**File (DEBUG level, with milliseconds + extra):**
```
2026-04-18 02:37:24.123 | DEBUG    | llm.providers.openai:stream:78 | chunk received | {"tokens": 15}
2026-04-18 02:37:24.456 | DEBUG    | memory.snip:clean:22 | L1 removed 3 filler words | {"freed_tokens": 12}
```

### 3.4 Usage

```python
# Each module file imports and uses directly
from loguru import logger

class MemoryManager:
    def on_round_complete(self, round_num: int):
        logger.info(f"Round {round_num} complete")
        if round_num % 26 == 0:
            logger.info(f"Triggering L3 compress for rounds {round_num-19}-{round_num}")
```

### 3.5 Configuration Options

| Config | Value | Description |
|------|-----|------|
| Console level | INFO (default) / DEBUG (`--verbose`) | Command-line argument toggle |
| File level | DEBUG | Always records detailed logs |
| File rotation | 10 MB | Auto-rotates when single file exceeds 10MB |
| File retention | 30 days | Logs older than 30 days are automatically deleted |
| File path | `logs/debug_{date}.log` | Separate files by date |
