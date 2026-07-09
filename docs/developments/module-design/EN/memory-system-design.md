# Emotion-Robot Memory System Design Document

> Legacy design note:
> Prefer the current implementation docs under [../../modules/memory/README.zh-CN.md](../../modules/memory/README.zh-CN.md).
> This file is kept as historical design source and migration reference, not as the authoritative entry point for the current implementation.

> This document serves as the design blueprint for the memory system, based on a comprehensive analysis of three reference projects (Open-LLM-VTuber / Neuro / airi) + the mem0 framework + Claude Code context compression strategies, determined through multiple rounds of discussion. Subsequent implementation should follow this document as the authoritative reference.

---

## 1. Requirement Anchors

### 1.1 Core Objectives

Build an **memory-persistent** emotional chatbot capable of:

- Maintaining coherent context within the same session (short-term memory)
- Remembering user preferences, facts, and emotional changes across sessions (long-term memory)
- Automatically compressing history as conversation turns grow, controlling token consumption for LLM calls

### 1.2 Memory Position in the Response Pipeline

```
User Input (text/ASR) -> L1 Snip Cleaning -> Short-term Memory Management -> mem0 Long-term Memory Retrieval
                                                                                       |
                                                                          Build LLM Context
                                                                                       |
                                                                                 LLM Call
                                                                                       |
                                                                          LLM Real-time Output Text
                                                                            |              |
                                                                          TTS      Translation Module
                                                                            |
                                                                      Write to chat_history
                                                                      Update short_term_memory
```

### 1.3 Design Constraints

- No MCP, Plugin, or other external tools; focus on RAG system
- Support dual-mode deployment: mem0 SDK cloud calls + local open-source deployment
- TTS/Translation modules consume LLM real-time output stream, do not read stored files
- Frontend is responsible for reading chat_history to render historical messages; backend is responsible for memory management

---

## 2. Reference Source Analysis

### 2.1 Contributions of Each Project to the Memory System

| Source | Contribution | Adoption Status |
|--------|-------------|-----------------|
| **Neuro** | Reflective memory: generate 3 Q&A pairs every 20 messages and write to ChromaDB | Borrowed the "periodic batch extraction" idea, but replaced ChromaDB with mem0 and fixed Q&A with free fact extraction |
| **airi** | Dual-stack storage: browser-side DuckDB + server-side pgvector | Borrowed the "layered storage" concept, but simplified to files (short-term) + mem0 vector store (long-term) |
| **Open-LLM-VTuber** | Factory pattern modular design, chat_history JSON format | Adopted JSON storage format (adjusted to one file per session), referenced modular architecture |
| **mem0** | v3 ADD-only fact extraction, three-way fusion retrieval, multi-tenant isolation | Serves as the core foundation for long-term memory, providing `add()` write + `search()` retrieval |
| **Claude Code** | 4-level progressive context compression (Snip/Micro/Collapse/Auto Compact) | Adopted 3-layer compression strategy (L1+L3+L4), round-driven instead of token-driven |

### 2.2 Key Design Decision Comparison

| Design Point | Neuro's Approach | Our Approach | Rationale |
|-------------|-----------------|--------------|-----------|
| Memory write timing | Reflect every 20 messages | Batch write to mem0 when L3 triggers at every 26 rounds | Similar frequency, but our "round" definition is stricter (one Q&A pair) |
| Memory extraction method | Fixed "3 most notable questions + answers" | mem0 v3 free fact extraction | Free extraction has broader coverage, not limited by fixed templates |
| Short-term memory structure | Latest 5 history + all twitch messages | Layered block structure + latest 6 raw rounds | Supports long conversations without context explosion from round growth |
| Vector store selection | ChromaDB PersistentClient | mem0 pluggable (Qdrant/Chroma/pgvector, etc., 30+ providers) | Higher flexibility, switchable as needed |
| Multi-tenancy | Single collection, no isolation | mem0 native user_id/agent_id/run_id three-dimensional isolation | Natively supports multi-user x multi-role |

---

## 3. Short-term Memory Design

### 3.1 Overview

Short-term memory is responsible for managing the context content sent to the LLM **within the current session**. The core challenge: as conversation turns grow, the token count of raw messages inflates linearly, and compression must be applied to control the payload size.

A Claude Code-inspired **3-layer progressive compression strategy** is adopted, using conversation turns (rather than token budget) as the trigger condition.

### 3.2 Round Definition

**1 round = a complete user->AI interaction pair.**

Counting rules:
- User sends one message + AI returns one valid reply = 1 round
- AI reply is empty or an error message (e.g., `Error calling the chat endpoint`) -> not counted as a round
- User sends multiple consecutive messages (ASR fragments) -> merged into one by L1, counted as 1 round after AI replies
- System messages (interrupt markers, etc.) -> not counted as a round, but retained in chat_history

```python
def count_rounds(messages):
    """Calculate effective round count"""
    return len([
        m for m in messages
        if m["role"] == "ai"
        and m["content"]                          # non-empty
        and not m["content"].startswith("Error")   # not an error
    ])
```

### 3.3 Three-Layer Compression Strategy

#### Overview

| Layer | Name | Trigger Condition | Processing Content | Uses LLM | Source |
|-------|------|-------------------|--------------------|----------|--------|
| **L1** | **Snip** | Every round, automatic | Pure rule-based cleaning: remove filler words, deduplicate, truncate oversized | No | Claude Code L1 |
| **L3** | **Collapse** | Every 26 rounds | Compress earliest 20 rounds -> generate block | Yes | Claude Code L3 |
| **L4** | **Super-Compact** | Every 4 accumulated blocks | Merge 4 blocks -> generate meta_block | Yes | Claude Code L4 |

> Skipping Claude Code's L2 (Micro compression), because L2's core value is "not breaking the prompt cache key"; emotion-robot has no prompt cache mechanism, so L2 is meaningless in this context.

#### L1 Snip -- Every Round, Automatic, Pure Rules

**Scope: Only processes user messages; does not modify AI replies.**

AI replies are controlled by the system prompt (including catchphrases, character personality) and should not be interfered with by cleaning rules.

| Rule | Operation | Example |
|------|-----------|---------|
| Filler word removal | Regex match against configurable word list, delete meaningless words | "um well I wanted to ask about the weather" -> "I wanted to ask about the weather" |
| Consecutive duplicate dedup | Adjacent 2+ similar user messages above threshold, keep only the last one | User said "hello" 3 times -> keep 1 |
| Oversized truncation | Truncate single message exceeding threshold, keep first N tokens + "[truncated]" | User pastes a long article -> keep first 800 tokens |
| System message stripping | Remove non-conversation content (heartbeat, Live2D status sync) | `[heartbeat] alive` -> delete |

**Applied uniformly to all user input** (no distinction between ASR/text input), latency < 1ms, negligible.

Configuration (`memory_config.yaml`):

```yaml
snip:
  filler_words: ["嗯", "啊", "呃", "额", "那个", "就是说", "对对对"]
  similarity_threshold: 0.95
  max_single_message_tokens: 800
```

#### L3 Collapse -- Triggers Every 26 Rounds, Uses LLM

**Trigger condition:** Activated when the current effective round count reaches a multiple of 26.

**Processing flow:**

```
Current 26 rounds of messages (after L1 cleaning)
  |
  +-- Earliest 20 rounds --> Compressor LLM --> block_N (structured summary)
  |                                               |
  |                                         Stored in short_term_memory.json active_blocks
  |
  +-- Earliest 20 rounds --> mem0.add(raw_messages) --> mem0 vector store (long-term facts)
  |
  +-- Latest 6 rounds --> Retained in recent_messages
```

**Compression granularity -- event-level, retaining 4 types of information (by priority):**

| Priority | Retained Content | Example |
|----------|-----------------|---------|
| P0 | User facts & preferences | "User's name is Xiao Ming, has an orange cat named Tuanzi" |
| P1 | Emotional state changes | "User went from happy to frustrated because of overtime" |
| P2 | Unfinished topics & commitments | "User said they have an interview tomorrow, asked me to remind them" |
| P3 | Topic turning points | "Switched from chatting about weather to work stress" |

**Discarded:** Small talk, verbose AI explanations (only conclusions kept), corrected erroneous information, repeated discussions of the same topic.

**Compression prompt template (`prompts/l3_collapse.txt`):**

```
你是一个对话记忆压缩器。请将以下 {N} 轮对话压缩为一段结构化摘要。

要求保留：
1. 用户表达的情感状态变化（开心→沮丧→平静）
2. 用户透露的个人偏好和事实（喜欢猫、住在北京、讨厌加班）
3. 对话中达成的共识或承诺（"明天提醒我"、"下次聊这个话题"）
4. 关键话题转折点

要求丢弃：
1. 寒暄和重复的问候
2. AI 的冗长解释（只保留结论）
3. 已被纠正的错误信息

输出格式：
## 对话摘要 (轮次 {start}-{end})
- 情感轨迹: ...
- 关键事实: ...
- 未完成话题: ...
- 用户偏好: ...
```

**Generated block structure:**

```json
{
  "block_id": "block_003",
  "level": 0,
  "covers_rounds": [41, 60],
  "created_at": "2026-04-17T18:00:00Z",
  "summary": "## 对话摘要 (轮次 41-60)\n- 情感轨迹: 平静→兴奋→平静\n- 关键事实: 用户提到下周要出差去上海\n- 未完成话题: 用户想了解上海美食推荐\n- 用户偏好: 偏好清淡口味",
  "token_count": 350
}
```

**Compression ratio:** 20 rounds of raw conversation (~2000-4000 tokens) -> 1 block (~300-500 tokens), approximately 6:1.

#### L4 Super-Compact -- Triggers Every 4 Accumulated Blocks, Uses LLM

**Trigger condition:** Activated when `active_blocks` accumulates 4 level-0 blocks.

```
block_1 (rounds 1-20)  -+
block_2 (rounds 21-40) -+-> LLM merge -> meta_block_1 (rounds 1-80)
block_3 (rounds 41-60) -+
block_4 (rounds 61-80) -+
```

**Compression granularity -- pattern-level (unlike L3's event-level):**

| Priority | Retained Content | Difference from L3 |
|----------|-----------------|---------------------|
| P0 | Stable user profile | L3 retains individual facts; L4 distills into persistent traits |
| P1 | Emotional change trends | L3 retains "frustrated today"; L4 distills "low mood this past week" |
| P2 | Recurring topics | L3 retains individual topics; L4 identifies "user frequently discusses work stress" |
| P3 | Relationship development stages | L3 lacks this dimension; L4 can see cross-period relationship changes |

**Core logic: L3 records "what happened" (event-level); L4 distills "what it means" (pattern-level).**

**Merge prompt template (`prompts/l4_super_compact.txt`):**

```
你是一个长期记忆整合器。以下是 4 段对话摘要，覆盖 {total_rounds} 轮对话。
请整合为一段更高层的记忆，重点提取：
1. 跨时段的情感变化趋势（而非单次情绪）
2. 反复出现的话题和兴趣
3. 用户性格特征的稳定模式
4. 关系发展的阶段性变化
```

**Compression ratio:** 4 blocks (~1200-2000 tokens) -> 1 meta_block (~400-600 tokens), approximately 3:1.

**Trigger frequency:** Only triggers once every 104 rounds (26 x 4), very low frequency.

### 3.4 Compressor Model Configuration

The compression models for L3/L4 are specified via configuration files, allowing users to choose autonomously:

```yaml
# memory_config.yaml
compressor:
  l3_model: "claude-haiku-4-5"     # L3 is high-frequency, lighter model can be used
  l4_model: "claude-sonnet-4-6"    # L4 is low-frequency, stronger model can be used
  # Or unified configuration:
  # model: "gpt-4o-mini"
  l3_prompt_template: "prompts/l3_collapse.txt"
  l4_prompt_template: "prompts/l4_super_compact.txt"
```

### 3.5 Send Payload Composition

Each LLM call assembles the context in the following order:

```
[1] System Prompt (character settings, catchphrases, etc.)
[2] mem0 long-term memory retrieval results (relevant facts returned by mem0.search)
[3] meta_blocks (L4 output, oldest compression layer)
[4] active_blocks (L3 output)
[5] Latest 6 raw rounds (after L1 cleaning)
[6] Current round user input
```

**Example (round 130):**

```
meta_block_1 (rounds 1-80)       <- L4 output, ~500 tokens
block_5 (rounds 81-100)          <- L3 output, ~350 tokens
block_6 (rounds 101-120)         <- L3 output, ~350 tokens
Latest 6 raw rounds (125-130)    <- After L1 cleaning, ~1200 tokens
Current round user input         <- ~200 tokens
---------------------------------
Total ~2600 tokens (compared to sending 130 raw rounds ~ 26000 tokens)
```

---

## 4. Long-term Memory Design

### 4.1 Overview

Long-term memory is responsible for **cross-session** persistence of user facts, preferences, emotional patterns, and other information. It uses mem0 as the core foundation, only utilizing its `add()` write and `search()` retrieval capabilities, without using mem0's built-in messages table.

### 4.2 mem0 Integration Method

#### Dual-Mode Deployment

| Mode | Implementation Class | Use Case | Configuration |
|------|---------------------|----------|---------------|
| **SDK Cloud** | `MemoryClient(api_key=...)` | Quick verification, no local infrastructure needed | Only requires API key |
| **Local Open-Source** | `Memory(config=...)` | Production deployment, data privacy, customizable | Requires vector store + LLM + Embedding configuration |

Both modes share the same API interface (`add` / `search` / `get_all` / `delete` / `history`), with the business layer switching via a `MODE` configuration item:

```yaml
# memory_config.yaml
mem0:
  mode: "local"  # "cloud" | "local"
  cloud:
    api_key: "${MEM0_API_KEY}"
  local:
    vector_store:
      provider: "qdrant"       # Options: qdrant / chroma / pgvector / faiss, etc.
      config:
        host: "localhost"
        port: 6333
    llm:
      provider: "openai"       # LLM used for fact extraction
      config:
        model: "gpt-4o-mini"
    embedder:
      provider: "openai"
      config:
        model: "text-embedding-3-small"
```

#### Multi-Tenant Mapping

mem0 natively supports `user_id` / `agent_id` / `run_id` three-dimensional isolation, mapped to emotion-robot as follows:

| mem0 Dimension | emotion-robot Meaning | Example |
|----------------|----------------------|---------|
| `user_id` | User identifier | `"alen"` |
| `agent_id` | Character identifier | `"katou"` |
| `run_id` | Session identifier | `"2026-04-17_a3f8"` |

Usage example:

```python
# Write -- when L3 triggers
mem0.add(
    messages=raw_20_rounds,       # Raw 20 rounds of messages (not block)
    user_id="alen",
    agent_id="katou",
    run_id="2026-04-17_a3f8"
)

# Retrieve -- before each LLM call
results = mem0.search(
    query=current_user_input,
    user_id="alen",
    agent_id="katou",
    limit=5
)
```

### 4.3 Write Timing

| Timing | Trigger Condition | Write Content |
|--------|-------------------|---------------|
| **During L3 compression** | Every 26 rounds | Earliest 20 rounds of raw messages |
| **When session closes** | User closes window / timeout disconnect | All remaining messages not yet processed by L3 (even if fewer than 20 rounds) |

**Key decision: What is fed to mem0 is raw messages, not blocks.**

Rationale:
- mem0 v3's fact extraction algorithm is designed for raw conversations
- Feeding blocks (second-hand summaries) causes mem0 to extract "summaries of summaries," distorting facts
- mem0 and the block system extract independently, without interfering with each other

Session close handling:

```python
def on_session_close(session):
    remaining = session.get_uncompressed_messages()
    if remaining:
        mem0.add(
            messages=remaining,
            user_id=session.user_id,
            agent_id=session.agent_id,
            run_id=session.session_id
        )
    # chat_history.json has been written in real-time each round, no additional action needed
```

### 4.4 Retrieval Timing and Injection

Before each LLM call, a semantic retrieval is performed using the current user input:

```python
def build_llm_context(user_input, short_term_memory, session):
    # 1. Retrieve long-term memory
    long_term = mem0.search(
        query=user_input,
        user_id=session.user_id,
        agent_id=session.agent_id,
        limit=5
    )

    # 2. Assemble context
    messages = []
    messages.append({"role": "system", "content": system_prompt})

    if long_term:
        memory_text = "\n".join([m["memory"] for m in long_term])
        messages.append({"role": "system", "content": f"关于这位用户，你记得：\n{memory_text}"})

    for mb in short_term_memory["meta_blocks"]:
        messages.append({"role": "system", "content": mb["summary"]})

    for ab in short_term_memory["active_blocks"]:
        messages.append({"role": "system", "content": ab["summary"]})

    for msg in short_term_memory["recent_messages"]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": user_input})
    return messages
```

### 4.5 Not Using mem0 messages Table

mem0's internal `messages` table (`SQLiteManager.save_messages`) is a cache that retains only the latest 10 raw messages, with a hardcoded eviction policy that is not configurable.

**Decision: Ignore this table.** Rationale:
- Our short-term memory system (layered block + recent_messages) already fully covers this need
- The messages table does not participate in `mem0.search()` vector retrieval, having no impact on long-term memory
- An additional storage point only increases consistency maintenance complexity

Implementation: When calling `mem0.add()`, `save_messages()` is not triggered (`save_messages` is an independent call, not automatically triggered by `add()`).

---

## 5. Storage Layout

### 5.1 Directory Structure

```
data/
  characters/
    katou/
      sessions/
        2026-04-17_a3f8.json       <- chat_history (archived)
        2026-04-18_b7c2.json
      short_term_memory.json       <- Short-term memory for the current active session
    shizuku/
      sessions/
        ...
      short_term_memory.json
  config/
    memory_config.yaml             <- Compression config, mem0 config, L1 rules
    prompts/
      l3_collapse.txt              <- L3 compression prompt template
      l4_super_compact.txt         <- L4 compression prompt template
```

### 5.2 chat_history.json -- Conversation History (Archive File)

**Responsibility:** Stores the complete record of all raw conversation messages. The frontend reads this file to render historical messages.

**Rules:**
- One file per session, filename = `{session_id}.json`
- Append-only writes, never modify existing content
- Not involved in LLM calls

**Field Definitions:**

```json
[
  {
    "role": "metadata",
    "timestamp": "2026-04-17T18:00:00Z",
    "session_id": "2026-04-17_a3f8",
    "character": "katou"
  },
  {
    "role": "human",
    "timestamp": "2026-04-17T18:00:05Z",
    "content": "今天天气真好",
    "raw_input": "嗯那个今天天气真好啊",
    "name": "Alen"
  },
  {
    "role": "ai",
    "timestamp": "2026-04-17T18:00:08Z",
    "content": "我是高性能的！确实适合出去走走呢",
    "name": "Katou",
    "avatar": "katou.png"
  },
  {
    "role": "system",
    "timestamp": "2026-04-17T18:01:00Z",
    "content": "[Interrupted by user]"
  }
]
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `role` | string | Yes | `"metadata"` / `"human"` / `"ai"` / `"system"` |
| `timestamp` | ISO 8601 | Yes | Message timestamp |
| `content` | string | Yes | Text after L1 cleaning (the version sent to the LLM) |
| `raw_input` | string | No | Retains the original ASR output for ASR input, used for accuracy analysis and model evaluation. Not stored for text input. Has `raw_input` = ASR input, no = text input |
| `name` | string | Yes | Speaker name |
| `avatar` | string | No | AI character avatar filename (AI characters only) |
| `session_id` | string | metadata only | Session ID, format `{date}_{uuid_short_code}` |
| `character` | string | metadata only | Character identifier |

### 5.3 short_term_memory.json -- Short-term Memory (Active File)

**Responsibility:** Stores all content currently to be sent to the LLM -- block hierarchy + recent raw messages.

**Rules:**
- One active file per character
- Backend Memory Manager reads and writes
- Assembled in `meta_blocks -> active_blocks -> recent_messages` order during LLM calls

**Complete Structure:**

```json
{
  "session_id": "2026-04-17_a3f8",
  "character": "katou",
  "updated_at": "2026-04-17T19:30:00Z",
  "total_rounds": 130,

  "meta_blocks": [
    {
      "block_id": "meta_001",
      "level": 1,
      "covers_rounds": [1, 80],
      "created_at": "2026-04-17T19:00:00Z",
      "summary": "## 长期模式摘要\n- 用户性格：内向偏乐观...",
      "token_count": 500,
      "source_blocks": ["block_001", "block_002", "block_003", "block_004"]
    }
  ],

  "active_blocks": [
    {
      "block_id": "block_005",
      "level": 0,
      "covers_rounds": [81, 100],
      "created_at": "2026-04-17T19:10:00Z",
      "summary": "## 对话摘要 (轮次 81-100)\n- 情感轨迹: 平静→兴奋...",
      "token_count": 350
    },
    {
      "block_id": "block_006",
      "level": 0,
      "covers_rounds": [101, 120],
      "created_at": "2026-04-17T19:20:00Z",
      "summary": "## 对话摘要 (轮次 101-120)\n...",
      "token_count": 340
    }
  ],

  "recent_messages": [
    {"round": 125, "role": "human", "content": "今天天气真好"},
    {"round": 125, "role": "ai", "content": "我是高性能的！确实，适合出去走走"},
    {"round": 126, "role": "human", "content": "你觉得去哪好"},
    {"round": 126, "role": "ai", "content": "..."},
    {"round": 127, "role": "human", "content": "..."},
    {"round": 127, "role": "ai", "content": "..."},
    {"round": 128, "role": "human", "content": "..."},
    {"round": 128, "role": "ai", "content": "..."},
    {"round": 129, "role": "human", "content": "..."},
    {"round": 129, "role": "ai", "content": "..."},
    {"round": 130, "role": "human", "content": "..."},
    {"round": 130, "role": "ai", "content": "..."}
  ]
}
```

### 5.4 Session Lifecycle

```
[New Session]
  -> Create chat_history.json (metadata row)
  -> Create short_term_memory.json (empty structure)
  -> mem0.search() available (cross-session long-term memory)

[Conversation In Progress]
  -> Each round: L1 cleaning -> write to chat_history -> update short_term_memory.recent_messages
  -> Every 26 rounds: L3 triggers -> generate block + mem0.add(raw)
  -> Every 4 blocks: L4 triggers -> generate meta_block

[Session Close]
  -> Remaining uncompressed messages -> mem0.add() (even if fewer than 20 rounds)
  -> short_term_memory.json retained (for next resume)
  -> chat_history.json retained (for frontend rendering)

[Resume Session]
  -> Frontend: read chat_history.json and render historical messages to the window
  -> Backend: read short_term_memory.json to restore block structure + recent_messages
  -> Continue counting from the previous total_rounds

[New Session (Same Character)]
  -> Create new chat_history.json (new session_id)
  -> Create new short_term_memory.json (empty structure)
  -> mem0 long-term memory still available (user_id + agent_id unchanged)
```

---

## 6. Collaborative Architecture Overview

### 6.1 Data Flow Panorama

> **Revision Note (2026-04-19, aligned with Phase 3 implementation + Phase 4 ChatAgent planning)**
>
> Compared to the early blueprint, there are two key changes:
>
> 1. **L1 Snip internalized from "independent entry node" into `MemoryManager.on_round_complete`**
>    (manager.py L552-553). Responsibility attribution is clearer: L1 belongs to the memory layer, not exposed as a public API.
> 2. **Introduction of `ChatAgent` composition layer** (Phase 4, `src/agent/chat_agent.py`) as the unified entry point for
>    calling LLM and MemoryManager.
>
> Data consistency remains unchanged: chat_history / recent_messages / mem0 index are all based on L1-cleaned versions;
> the current round's `user_input` passes raw to LLM position [6] (preserving the fresh context of the current round).

```
User Input (text / ASR, raw text)
  |
  v
ChatAgent (Phase 4 composition layer)
  |  Holds: persona + LLMInterface(role=chat) + MemoryManager
  |
  +-- (1) await mgr.build_llm_context(raw user_input, persona)
  |        |
  |        v Internal payload assembly (strictly per section 3.5 order):
  |        +------------------------------------------------------------+
  |        | [1] system                : persona                        |
  |        | [2] Long-term facts       : search_long_term(raw)          |
  |        |     +-> mem0.search(query=raw, user_id, agent_id)         |
  |        |        -> Wrapped "关于这位用户，你记得：\n- ..."            |
  |        | [3] meta_blocks   (cleaned; L4 output)                     |
  |        | [4] active_blocks (cleaned; L3 output)                     |
  |        | [5] recent_messages (cleaned; section 3.2 valid rounds)    |
  |        | [6] Current round user_input (raw, passed through as-is)  |
  |        +------------------------------------------------------------+
  |
  +-- (2) async for chunk in llm.chat_completion_stream(messages):
  |        yield chunk   (LLM native language text, e.g., zh)
  |            |
  |            v Downstream consumers (all independent plugin-style modules, start/stop + consumption source determined by config):
  |            +-> Frontend (default consumes LLM raw text; configurable to consume translated text)
  |            +-> Translation module (optionally enabled; form: output text -> translate -> translated,
  |            |              when enabled, its downstream consumers = frontend / TTS / both, determined by config)
  |            +-> TTS module (optionally enabled; consumption source = LLM raw text / translated text, determined by config)
  |
  v stream ends (all chunks merged into reply)
  |
  +-- (3) await mgr.on_round_complete(
             user_msg={role:"human", content: raw, raw_input: ASR raw?},
             ai_msg  ={role:"ai",    content: reply},
         )   <- ChatAgent automatically calls (S1b decision)
          |
          v MemoryManager.on_round_complete internals:
          |
          +-- L1 Snip (only applies to user_msg; AI reply untouched)
          |   -> cleaned_user
          |
          +-- chat_history.append_human(cleaned.content, raw_input=raw_input?)
          +-- chat_history.append_ai(reply)
          |     (Error round S4 goes through append_system_note, not append_ai)
          |
          +-- recent_messages += [{human: cleaned}, {ai: reply}]
          |
          +-- total_rounds++ (only when _is_valid_round: content non-empty &
          |                    does not start with "Error"; section 3.2)
          |
          +-- Check total_rounds % 26 == 0?
          |     +-- Yes -> L3 Collapse
          |              +-> Earliest 20 rounds cleaned -> compression LLM -> block -> active_blocks
          |              +-> Same window -> long_term.add()
          |                 v mem0 internally calls LLM to extract facts -> fact sentence embeddings indexed
          |
          +-- Check active_blocks >= 4?
                +-- Yes -> L4 Super-Compact
                         +-> 4 blocks -> compression LLM -> meta_block -> meta_blocks
```

**Key Facts (corresponding to implementation)**:

1. **Where raw text goes**: The current round's `user_input` takes two "raw paths" -- direct to LLM position [6], and as the query for `search_long_term`; all other persistence paths (chat_history.content / recent_messages / mem0.add's window) go through L1 inside `on_round_complete` to get cleaned.

2. **The nature of mem0 indexing** (see `docs/projects-docs/mem0_架构文档.md` section 3.2/3.3 for details): `mem0.add` internally calls an LLM once to extract fact sentences; what is indexed is the **fact sentence embedding** (e.g., "user loves bubble tea"), not the embedding of the add input messages. This means the raw vs. cleaned difference of the search query is absorbed at the index dimension.

3. **Translation module and TTS**: Both are **independent plugin-style modules**, jointly serving as bypass consumers of the LLM stream -- **they do not enter chat_history** and **do not affect on_round_complete**.
   - **Translation module**: Optionally enabled (config switch), form `output text -> translate module -> translated text`. When enabled, its downstream consumers are determined by config (frontend / TTS / both); **it does not determine who consumes**.
   - **TTS module**: Similarly independently optional, consumption source determined by config -- LLM raw text (default) or translation module output.
   - **Frontend**: Default consumes LLM raw text; configurable to consume translated text.
   - chat_history always records LLM native language; the language consistency of memory/compression is not affected by translation/TTS enable/disable.

4. **Error path (S4)**: When LLM throws `LLMError`, ChatAgent yields error text to the caller and calls `mgr.append_system_note("[LLM call failed: ...]")` to write a `role=system` row in chat_history -- **not counted as a round, does not trigger L3, does not enter recent_messages**.

### 6.2 Three-Layer Storage Responsibility Division

```
+-----------------------------------------------------------+
|              Short-term Memory (File)                      |
|  short_term_memory.json                                   |
|  +-----------+  +-----------+  +------------------------+ |
|  |meta_block |  |  blocks   |  |   recent_messages      | |
|  | (L4 output)|  |(L3 output)|  |  (latest 6 cleaned)   | |
|  +-----------+  +-----------+  +------------------------+ |
|  Purpose: Build context for the current LLM call          |
|  Lifecycle: Within session (recoverable across sessions)   |
+-----------------------------------------------------------+
|              Long-term Memory (mem0 Vector Store)          |
|  mem0.add() write / mem0.search() retrieval               |
|  Purpose: Cross-session retrieval of relevant facts,       |
|           preferences, emotional patterns                  |
|  Lifecycle: Permanent                                      |
+-----------------------------------------------------------+
|              Conversation Archive (File)                    |
|  chat_history.json                                        |
|  Purpose: Frontend renders historical messages /           |
|           debugging / ASR accuracy analysis                |
|  Lifecycle: Permanent                                      |
+-----------------------------------------------------------+
```

---

## 7. Configuration File Summary

### memory_config.yaml Complete Structure

```yaml
# ============================================================
# Emotion-Robot Memory System Configuration
# ============================================================

# --- Short-term Memory ---
short_term:
  # L1 Snip Rules
  snip:
    filler_words: ["嗯", "啊", "呃", "额", "那个", "就是说", "对对对"]
    similarity_threshold: 0.95       # Deduplication similarity threshold
    max_single_message_tokens: 800   # Max tokens per single message

  # L3 Collapse Configuration
  collapse:
    trigger_rounds: 26               # Trigger every N rounds
    compress_rounds: 20              # Compress earliest M rounds
    keep_recent_rounds: 6            # Keep latest K raw rounds

  # L4 Super-Compact Configuration
  super_compact:
    trigger_blocks: 4                # Trigger every N accumulated blocks

  # Compressor Models
  compressor:
    l3_model: "claude-haiku-4-5"
    l4_model: "claude-sonnet-4-6"
    l3_prompt_template: "prompts/l3_collapse.txt"
    l4_prompt_template: "prompts/l4_super_compact.txt"

# --- Long-term Memory (mem0) ---
mem0:
  mode: "local"                      # "cloud" | "local"
  cloud:
    api_key: "${MEM0_API_KEY}"
  local:
    vector_store:
      provider: "qdrant"
      config:
        host: "localhost"
        port: 6333
    llm:
      provider: "openai"
      config:
        model: "gpt-4o-mini"
    embedder:
      provider: "openai"
      config:
        model: "text-embedding-3-small"
  search:
    limit: 5                         # Number of results per retrieval
    # threshold: 0.1                 # To be tuned
    # rerank: false                  # To be tuned
```

---

## 8. Pending Items Checklist

The following items have been architecturally pre-provisioned with interfaces, pending further discussion or empirical testing:

| # | Pending Item | Current Status | Impact Scope |
|---|-------------|----------------|--------------|
| 1 | mem0 vector store selection (Qdrant / Chroma / Faiss) | Closed (section 8.1) | Deployment complexity |
| 2 | Embedding model selection | Closed (section 8.2) | Semantic matching quality |
| 3 | `mem0.search()` parameter tuning (limit / threshold / rerank) | Defaults set, awaiting empirical testing | Retrieval precision vs. latency |
| 4 | Whether to enable mem0 Graph Memory (Neo4j) | Closed (section 8.4) | Entity relationship reasoning |
| 5 | L3/L4 compression prompt template effectiveness validation | Closed (section 8.6), awaiting empirical fine-tuning | Summary quality |
| 6 | L1 filler word list refinement | Closed (section 8.7), awaiting empirical expansion | ASR cleaning quality |
| 7 | Long-term memory section content in readme | To be added after implementation | Requirement completeness |
| 8 | short_term_memory integrity validation on session resume | Closed (section 8.5) | Exception recovery |

> The following are decision supplements from in-depth discussion of each item. This checklist is an "incremental" record: the table above describes the initial state, and the subsections below cover decisions reached. In case of conflict, the decisions below take precedence.

### 8.1 Item #1 Vector Store Selection

**Decision:** Local **Qdrant** (dual mode: embedded default + Server optional); cloud **mem0 SaaS SDK**. Multi-character isolation is handled by mem0's native `agent_id` filter, no need for application-level collection separation.

**Comparison of Qdrant's two deployment modes:**

| Dimension | Embedded (File Mode) | Server Mode (Docker) |
|-----------|---------------------|----------------------|
| Nature | Python library runs in main process, data stored locally | Standalone service process, HTTP/gRPC connection |
| Analogy | SQLite | PostgreSQL |
| Startup | `QdrantClient(path="./qdrant_data")` | `docker run qdrant/qdrant` + `QdrantClient(host=...)` |
| Install Cost | `pip install qdrant-client` | Requires Docker |
| Concurrent Writes | Not supported (process lock) | Supported |
| Remote Access | Not supported | Supported |
| Cloud Migration | Data needs import/export | Just change host address |
| Code Difference | Only change `QdrantClient` constructor params, business logic identical | Same as left |

**Final Selection Rationale:**
- MVP/personal use defaults to embedded, zero configuration, out-of-the-box
- Switch to Server mode for cloud or multi-user concurrency, zero code changes (mem0's `vector_store.provider` abstraction)
- In `sdk` mode this setting is not effective (mem0 SaaS hosts the vector store)

---

### 8.2 Item #2 Embedding / LLM / Deployment Structure

**Core Insight:** `mode` represents "mem0's usage form," orthogonal to code deployment location (local can run `sdk`, VPS can run `local_deploy`).

**Final Configuration Structure (replacing original examples in sections 4.2 and 7):**

```yaml
mem0:
  mode: "local_deploy"    # "sdk" | "local_deploy"

  # --- Mode A: mem0 SaaS (Hosted) ---
  sdk:
    api_key: "${MEM0_API_KEY}"
    # Embedding / LLM / vector store all managed by mem0, transparent to user, no configuration needed

  # --- Mode B: Local / Self-hosted ---
  local_deploy:
    vector_store:
      provider: "qdrant"
      config:
        path: "./data/qdrant"         # Embedded default
        # host: "localhost"            # Server mode switch
        # port: 6333

    embedder:
      backend: "ollama"                # "ollama" | "api", default ollama
      ollama:
        model: "bge-m3"                # 1024 dimensions, multilingual SOTA
        base_url: "http://localhost:11434"
      api:
        provider: "openai"             # OpenAI / compatible API (Zhipu/Ali/DeepSeek)
        model: "text-embedding-3-small"
        api_key: "${OPENAI_API_KEY}"
        base_url: "https://api.openai.com/v1"

    llm:
      reuse_main_llm: false            # Default independent configuration (cold/hot model separation)
      backend: "ollama"                # "ollama" | "api", default ollama
      ollama:
        model: "qwen2.5:7b"
        base_url: "http://localhost:11434"
      api:
        provider: "openai"
        model: "gpt-4o-mini"
        api_key: "${OPENAI_API_KEY}"
        base_url: "https://api.openai.com/v1"
```

**Key Design Points:**

1. **Embedder three backends**: `ollama` (local unified, recommended) / `api` (OpenAI compatible, cloud/no GPU scenarios) / fallback HuggingFace direct. mem0 natively supports all of the above.
2. **Embedding dimension alignment**: bge-m3=1024, OpenAI small=1536. Changing models requires rebuilding the vector store (mem0 requires vector_store and embedder dimensions to match).
3. **bge-m3 performance on local GPU**: RTX 3060/4060+ single item 5-15ms, 20-round batch compression only 200-500ms, completely effortless.
4. **LLM `reuse_main_llm` defaults to false**: Default independent configuration; main chat can use Claude/GPT, fact extraction uses cheaper qwen2.5/gpt-4o-mini; change to `true` when unification is needed to reuse the main LLM client.
5. **mem0 native Embedder Providers**: `openai` / `ollama` / `huggingface` / `vertexai` / `gemini` / `aws_bedrock` / `together` / `langchain`.
6. **Ollama vs. HuggingFace direct**: Ollama as an independent daemon, embedder+LLM unified management, independent VRAM; HuggingFace direct depends on `sentence-transformers` + `torch`, sharing VRAM with the main process.

**4 LLM call exits within the project** (note during design):
1. Main chat (user->AI)
2. L3 compression (every 26 rounds)
3. L4 super-compact (every 4 blocks)
4. mem0 fact extraction (every `mem0.add()`)

When `reuse_main_llm: true`, #4 reuses #1; when default false, #4 is independent; #2/#3 are separately specified by `short_term.compressor`.

---

### 8.3 Item #3 `mem0.search()` Parameters

**Decision (MVP initial values):** `limit=5 / threshold=0.3 / rerank=false` (balanced version)

**Parameter Selection Reasoning:**

| Parameter | Value | Reasoning |
|-----------|-------|-----------|
| `limit` | 5 | Each memory averages ~40 tokens, total ~200 tokens injected into context; does not dilute the system prompt's character settings |
| `threshold` | 0.3 | Emotional conversation queries are short (20-50 tokens), semantics tend to generalize; lower threshold prevents missing weakly associated emotional memories ("tired today" <-> "last time working overtime") |
| `rerank` | false | MVP stage reduces latency and API call costs; enable later if recall precision is insufficient |

**Configuration Placement:**

```yaml
mem0:
  # ... (mode / sdk / local_deploy config see section 8.2)
  search:
    limit: 5
    threshold: 0.3
    rerank: false
  retrieval:
    enabled: true
    policy: hybrid              # always | interval | triggered | hybrid
    interval_turns: 10
    min_query_chars: 6
    trigger_keywords: ["记得", "还记得", "之前", "上次", "我说过", "我的偏好", "我的信息"]
    cache:
      enabled: true
      backend: memory
      ttl_seconds: 1800
      max_entries: 512
```

**Compatibility Notes:** `limit` / `threshold` parameters have consistent semantics in both `sdk` and `local_deploy` modes; `rerank` on the SaaS side may be replaced by mem0's internal algorithm (not user-controllable), while `local_deploy` requires additional reranker provider configuration to enable.

**Retrieval Quota Control:**
- When `mem0.retrieval` is missing, old behavior is preserved: retrieve every round.
- Default `hybrid`: keyword match triggers immediate retrieval; otherwise falls back to retrieval at `interval_turns`; short input below `min_query_chars` is skipped.
- `cache.backend=memory` is an in-process TTL cache, only reducing duplicate queries within the same process; not cross-process, not cross-restart.

**Tuning Trigger Conditions** (left for post-launch empirical testing):
- User feedback "AI can't remember what I said" -> lower threshold or increase limit
- Injected long-term memory is irrelevant to current topic -> raise threshold or enable rerank
- High response latency -> lower limit, disable rerank

---

### 8.4 Item #4 Graph Memory

**Decision:** MVP **temporarily not enabled**; `memory_config.yaml` reserves a `graph_store` configuration point. Users can one-click switch `enabled: true` + fill in Neo4j connection to enable, **zero code changes** (mem0 natively supports it).

**Configuration Placement (reserved skeleton):**

```yaml
mem0:
  local_deploy:
    # ... (vector_store / embedder / llm see section 8.2)
    graph_store:
      enabled: false                # Disabled by default
      provider: "neo4j"             # neo4j | memgraph
      config:
        url: "bolt://localhost:7687"
        username: "neo4j"
        password: "${NEO4J_PASSWORD}"
      # When enabled, each add() will additionally call an LLM to extract entity relationships
```

**Capability Boundary: Enabled vs. Not Enabled:**

| Scenario | Vector Only | Graph Memory |
|----------|-------------|--------------|
| Semantic similarity retrieval ("how's my mom") | Supported | Supported |
| Relationship aggregation ("what animals do I have") | May miss recalls | Precise traversal |
| Multi-hop reasoning ("who in the family has a chronic illness") | Query too abstract, likely misses | Two-hop query hits |
| Relationship changes (breakup/move/job change) | Old memories still recalled | Can explicitly delete edges |

**Rationale for Not Enabling:**
1. MVP stage vector store already covers 80% of core value (user facts, preferences, emotional state)
2. An additional LLM call would block L3 triggers for 2-5s
3. An additional Neo4j Docker service is not cost-effective for initial deployment complexity
4. The feedback signal for enabling is clear (user complains "forgot family members" / "broke up but still thinks we're dating") -> enable after empirical testing

**Future Enable Trigger Conditions:**

- User feedback "AI can't distinguish my family relationships"
- User feedback "AI can't remember my pet/friend's specific information"
- Need to track long-term relationship evolution (dating -> breakup, friend -> distant)

**In SaaS mode:** This configuration is not effective; whether mem0 SaaS has built-in Graph capability is determined by the mem0 team, no user configuration needed.

---

### 8.5 Item #8 Session Resume Integrity Validation

**Decision:** Lightweight approach -- use `chat_history.json` as the source of truth, validate `short_term_memory.json` consistency on resume, rebuild from chat_history if inconsistent. No WAL logs or write transactions introduced.

**Design Principle:** "Fill in data + check if compression should be triggered"; resume logic is consistent with normal conversation flow, no additional resume-specific code paths introduced.

#### Three Crash Scenarios and Impact Analysis

| Scenario | Trigger Condition | Impact | Recovery Strategy |
|----------|-------------------|--------|-------------------|
| **L3 write mid-crash** | During L3 trigger, three things happen: (a) LLM compression generates block, (b) `mem0.add()` writes to long-term memory, (c) updates `short_term_memory.json`. Process crashes mid-step | `short_term_memory.json` may be truncated/corrupted; `chat_history.json` not affected (independent append); mem0 may or may not have written | Rebuild short_term_memory from chat_history; mem0 repeated add is harmless (ADD-only idempotent) |
| **chat_history and short_term_memory inconsistency** | Crash during normal conversation (not during L3 trigger), short_term_memory's `total_rounds` lags behind chat_history's actual round count | short_term_memory missing several rounds of recent_messages | Fill back missing rounds from chat_history |
| **mem0 write failure** | `mem0.add()` fails during L3 trigger (Qdrant not started, network timeout, etc.), but block generation succeeds | These 20 rounds of long-term facts missing from mem0 vector store | Session close's fallback write (section 4.3 `on_session_close`) will retry; mem0 ADD-only, repeated writes are harmless |

#### Resume Flow

```
When resuming a session:

1. Read short_term_memory.json
   +-- json.load() fails (file corrupted/truncated) -> Go to [Full Rebuild]
   +-- json.load() succeeds -> Go to step 2

2. Validate consistency: short_term_memory.total_rounds vs chat_history actual round count
   +-- Consistent -> Normal resume, no additional action needed
   +-- Inconsistent (chat_history rounds > total_rounds) -> Go to step 3

3. Incremental repair:
   a. From chat_history, extract "rounds not covered by short_term_memory"
   b. Fill into recent_messages, update total_rounds
   c. Check if filling back triggers L3 condition (total_rounds % 26 == 0)
      +-- Yes -> Normally trigger L3 (compression + mem0.add)
      +-- No -> Don't compress, wait for natural trigger in subsequent conversation

[Full Rebuild]:
   a. Create empty short_term_memory structure
   b. Replay from chat_history round by round: L1 cleaning -> accumulate -> trigger L3 at 26 rounds -> trigger L4 at 4 blocks
   c. mem0.add() for all rounds (idempotent, repeated writes harmless)
   d. Normal resume after rebuild completes
```

#### Edge Case Handling

| Edge Case | Handling |
|-----------|----------|
| **Crash during L4 trigger** | On resume, check: active_blocks >= 4 with no corresponding meta_block -> re-trigger L4. L4 input is already persisted blocks, safe to re-run |
| **chat_history itself corrupted** | Append-only JSON array, at most the last entry is half-written. Attempt to parse; on failure, truncate to the last complete `}`, losing at most one message |
| **First startup (no history files)** | Not a resume, but normal initialization: create empty short_term_memory + empty chat_history (with metadata row) |
| **Full rebuild performance** | Requires batch LLM calls for L3 compression on historical rounds. 100 rounds of history needs ~4-5 L3 calls (20 rounds each), taking ~10-20 seconds. Low-frequency operation, acceptable |

#### Key Design Points

1. **chat_history is the source of truth**: It is append-only, inherently more reliable than short-term memory which requires in-place updates
2. **Resume logic = normal logic**: No dedicated resume code paths introduced; instead reuses the normal flow of "fill in data + check trigger conditions"
3. **mem0 is naturally idempotent**: v3 ADD-only algorithm means repeated writes only produce a few redundant facts, no data loss or overwrites
4. **No preventive write optimization**: No WAL, no fsync, no write transactions. In single-user scenarios, crashes are low-probability events; recovery cost (seconds to tens of seconds) is far lower than prevention cost (code complexity)

---

### 8.6 Item #5 L3/L4 Compression Prompt Template Review

**Decision:** Three improvements made to the L3/L4 prompt drafts in section 3.3; design-level closure achieved. Specific parameters (compression ratio, summary quality) to be fine-tuned after implementation with empirical testing.

**Three Improvements:**

1. **Added `<analysis>` draft step**: Let the LLM analyze before outputting summaries, reducing omissions. References Claude Code L4 prompt's `<analysis>` design (section 9.5).
2. **L3 explicitly retains priority P0-P3**: Changed from the original draft's flat list to a prioritized structure, providing clear trade-off criteria during compression.
3. **L4 adds explicit output template**: The original draft only said "integrate into higher-level memory"; now defines an output structure corresponding to L3 but at a different level.

**Improved L3 prompt (replacing the original in section 3.3):**

```
你是一个对话记忆压缩器。请将以下 {N} 轮对话压缩为一段结构化摘要。

首先在 <analysis> 标签内梳理对话中的关键信息（此部分不会出现在最终摘要中）：
<analysis>
- 逐轮扫描，标记：情感变化点、用户事实、未完成事项、话题转折
- 识别哪些内容是重复/寒暄/可丢弃的
- 检查是否有被纠正的错误信息需要排除
</analysis>

然后基于分析，输出最终摘要。

保留优先级（从高到低）：
P0: 用户事实 & 偏好（"用户叫小明，养了一只橘猫叫团子"）
P1: 情感状态变化（"用户从开心变得沮丧，因为加班"）
P2: 未完成话题 & 承诺（"用户说明天要面试，让我提醒"）
P3: 话题转折点（"从聊天气转到聊工作压力"）

丢弃：寒暄、AI 冗长解释（只保留结论）、已被纠正的错误信息、重复讨论的同一话题。

输出格式：
## 对话摘要 (轮次 {start}-{end})
- 情感轨迹: ...
- 关键事实: ...
- 未完成话题: ...
- 用户偏好: ...
```

**Improved L4 prompt (replacing the original in section 3.3):**

```
你是一个长期记忆整合器。以下是 4 段对话摘要，覆盖 {total_rounds} 轮对话。
请整合为一段更高层的模式级记忆。

首先在 <analysis> 标签内分析跨摘要的模式（此部分不会出现在最终输出中）：
<analysis>
- 哪些事实在多个摘要中反复出现？→ 提炼为稳定特征
- 情感变化是否有趋势？→ 从单次情绪提炼为情绪模式
- 哪些话题反复被提起？→ 识别核心兴趣
- 用户与 AI 的互动方式有无变化？→ 判断关系阶段
- 哪些承诺跨多个摘要仍未完成？→ 标记为重要待办
</analysis>

然后基于分析，输出整合后的模式级摘要。

与事件级摘要的区别：不记录"发生了什么"，而是提炼"这意味着什么"。

输出格式：
## 长期模式摘要 (轮次 {start}-{end})
- 用户画像: ...（稳定的性格特征、生活状态）
- 情感趋势: ...（跨时段的情绪变化模式，而非单次情绪）
- 核心话题: ...（反复出现的兴趣和关注点）
- 关系阶段: ...（用户与 AI 的互动模式变化）
- 重要承诺: ...（跨多轮仍未完成的事项）
```

**Output format decision: keep markdown.** Rationale: L3/L4 output has two consumers -- the main chat model (injected into context each round) and the compression model (L4 merges L3 blocks). Both are LLMs; markdown has good readability and can be directly injected without conversion. JSON format would add an unnecessary "JSON -> natural language" conversion layer.

**`<analysis>` draft block handling:** The `<analysis>...</analysis>` portion in the compression model output should be stripped (via regex match deletion) before storing in the block's `summary` field, keeping only the final summary. This prevents increasing the block's token volume.

**Items to fine-tune after implementation:**
- Whether the `<analysis>` step works stably for lightweight models (haiku level)
- Whether compression ratio remains around 6:1 (L3) and 3:1 (L4)
- Whether the output template fields are stably populated (no empty fields or format drift)

---

### 8.7 Item #6 L1 Filler Word List Refinement

**Decision:** Adjusted the initial word list (removed "then", added "um" and "uh"), established the design principle of "better to miss a deletion than to incorrectly delete." Specific word list to be expanded after empirical testing with ASR output.

**Word List Adjustments:**

| Operation | Word | Rationale |
|-----------|------|-----------|
| Remove | "然后" (then) | A meaningful connective in narrative context ("I went to the supermarket first, then went to the bank"), should not be blindly deleted |
| Add | "呃" (um) | One of the most common hesitation sounds in ASR |
| Add | "额" (uh) | One of the most common hesitation sounds in ASR |
| Keep | "嗯", "啊", "那个", "就是说", "对对对" | Pure catchphrases with no semantic value in any context |

**Adjusted word list (already synchronized and updated in sections 3.3 and 7 configuration examples):**

```yaml
filler_words: ["嗯", "啊", "呃", "额", "那个", "就是说", "对对对"]
```

**Design Principle: Better to miss a deletion than to incorrectly delete.**

L1 is positioned as lightweight pure-rule cleaning, not using LLM. The filler word list only includes **pure catchphrases with no semantic value in any context**. Ambiguous words (like "then," "so," "anyway," "just") are not included, left for the LLM to ignore during understanding.

**Rationale:**
- L1 is an irreversible operation (cleaned text is written to chat_history's `content` field; original text is only preserved in `raw_input` for ASR input)
- Incorrectly deleting meaningful words causes LLM understanding deviation and cannot be recovered
- The cost of missing filler words is very low -- LLMs naturally ignore catchphrases, at most wasting a few tokens

**Items to expand after implementation (adjust based on ASR output):**
- Observe high-frequency meaningless words in actual ASR transcription results
- Adjust based on the output characteristics of the ASR engine used (sherpa_onnx / whisper.cpp)
- Consider whether word lists need to be separated by language (Chinese / English / Japanese)

---

## 9. Appendix: Claude Code Compression Source Code Index

> This appendix provides source code references for Section 3 "Short-term Memory Design." All paths are relative to `D:\Coding\GitHub_Resuorse\emotion-robot\cc-haha\src\`. During implementation, these files can be directly consulted as reference templates.

### 9.1 File Map Overview

```
cc-haha/src/
+-- query.ts                              <- Core loop (~1730 lines), trigger entry point for all levels
|
+-- services/
|   +-- compact/                          <- Main compression implementation directory
|   |   +-- snipCompact.ts                <- L1 Snip implementation (enabled by HISTORY_SNIP feature)
|   |   +-- microCompact.ts               <- L2 Micro implementation (not adopted in this project)
|   |   +-- apiMicrocompact.ts            <- L2 API layer wrapper
|   |   +-- autoCompact.ts                <- L4 Auto Compact threshold logic and state
|   |   +-- compact.ts                    <- Common compression logic (prompt_too_long recovery, media stripping, etc.)
|   |   +-- prompt.ts                     <- Compression prompt templates (L4 full summary system prompt)
|   |   +-- sessionMemoryCompact.ts       <- Session memory compression
|   |   +-- postCompactCleanup.ts         <- Post-compression cleanup (file re-read, tool reload)
|   |   +-- compactWarningHook.ts         <- Warning when approaching threshold
|   |   +-- grouping.ts                   <- Message grouping (by API rounds)
|   |   +-- timeBasedMCConfig.ts          <- Time-based Micro configuration
|   |
|   +-- contextCollapse/                  <- L3 context collapse (enabled by CONTEXT_COLLAPSE feature)
|       +-- index.ts
|
+-- utils/
    +-- collapseReadSearch.ts             <- Collapsible tool result identification (works with L3)
```

### 9.2 L1 Snip Compression

| Item | Location |
|------|----------|
| Implementation file | `services/compact/snipCompact.ts` |
| Core function | `snipCompactIfNeeded(messages)` -- returns `{ messages, tokensFreed, boundaryMessage }` |
| Trigger point | `query.ts:401-410` (every round, automatic, before microcompact) |
| Feature flag | `HISTORY_SNIP` |

**Implementation approach:** Pure rules, no LLM involved. Scans historical messages for tool results (repeated file reads, oversized tool outputs), deletes redundant tokens and returns the `tokensFreed` quantity. This quantity is passed to autocompact's threshold logic, making L4's trigger more accurate.

**Lessons for emotion-robot L1:**
- Claude Code's L1 primarily targets tool result deduplication; our L1 targets ASR filler words/repeated messages, with similar implementation form (scan -> replace -> return tokensFreed)
- Can follow `snipCompactIfNeeded`'s signature: `(messages) => { messages, tokensFreed }`

### 9.3 L2 Micro Compression (Not Adopted in This Project)

| Item | Location |
|------|----------|
| Implementation file | `services/compact/microCompact.ts` |
| Core function | `microcompactMessages(messages, toolUseContext, querySource)` |
| Trigger point | `query.ts:413-419` |

**Why not adopted:** L2's core value is "not breaking the prompt cache key" (see `microCompact.ts:305 cachedMicrocompactPath`); emotion-robot has no prompt cache mechanism, making this optimization meaningless in this context.

### 9.4 L3 Context Collapse

| Item | Location |
|------|----------|
| Implementation file | `services/contextCollapse/index.ts` |
| Key method | `contextCollapse.recoverFromOverflow(messages, querySource)` |
| Trigger point | `query.ts:1089-1117` (reactive mode, on prompt_too_long) |
| Feature flag | `CONTEXT_COLLAPSE` |

**Implementation approach:** Staged "draining" of the staged collapse points. The method returns `{ messages, committed }`, where `committed > 0` indicates collapse was actually executed. Not a one-shot full summary, but **progressive** (stage by stage).

**Lessons for emotion-robot L3:**
- `recoverFromOverflow`'s `committed` count is analogous to our block count
- The staged thinking can be applied to refresh strategy when accumulating multiple blocks
- However, Claude Code only triggers L3 on overflow; we change to **periodic trigger every 26 rounds** (Proactive), not reactive

### 9.5 L4 Auto Compact

| Item | Location |
|------|----------|
| Threshold logic | `services/compact/autoCompact.ts` |
| Core function | `shouldAutoCompact(messages, model, snipTokensFreed, ...)` -- returns whether trigger is needed |
| State type | `AutoCompactTrackingState` (`autoCompact.ts:51`) |
| Key constants | `AUTOCOMPACT_BUFFER_TOKENS = 13_000` / `MANUAL_COMPACT_BUFFER_TOKENS = 3_000` |
| Execution function | `compactConversation(...)` at `services/compact/compact.ts:387` |
| Compression prompt | `services/compact/prompt.ts:61` `BASE_COMPACT_PROMPT` |
| Trigger point | `query.ts:1119-1162` (reactive, on 413 error) |

**Compression prompt's 9-section structure (`prompt.ts:66-77`):**

```
1. Primary Request and Intent
2. Key Technical Concepts
3. Files and Code Sections
4. Errors and fixes
5. Problem Solving
6. All user messages
7. Pending Tasks
8. Current Work
9. Optional Next Step
```

**Lessons for emotion-robot L4:**
- The above 9-section structure is designed for coding scenarios; emotion-robot needs an emotional scenario version: `Emotional Trajectory / User Profile / Recurring Topics / Relationship Development`
- `BASE_COMPACT_PROMPT`'s `<analysis>` draft block design (`prompt.ts:31-44`) is worth referencing -- lets the LLM produce an analysis draft first, then generate the summary, avoiding omissions
- Token threshold driven (`getAutoCompactThreshold`) -> we replace with round-driven, logic is simpler (`if rounds % 26 == 0`)

### 9.6 Token Budget Tracking

| Item | Location |
|------|----------|
| Type definition | `AutoCompactTrackingState` @ `autoCompact.ts:51` |
| Threshold calculation | `getAutoCompactThreshold(model)` @ `autoCompact.ts:72` |
| Warning state | `calculateTokenWarningState(...)` @ `autoCompact.ts:93` |
| State field | `query.ts:207` `autoCompactTracking: AutoCompactTrackingState \| undefined` |

**Lessons for emotion-robot:**
- We don't need token tracking, only the `total_rounds` field (already defined in `short_term_memory.json`)
- Threshold logic simplified to: `rounds >= 26 && rounds % 26 == 0` -> trigger L3; `active_blocks.length >= 4` -> trigger L4

### 9.7 6 Recovery Strategies

All located in `query.ts`, marking recovery type via `state.transition.reason` modification then `continue` back to the loop top:

| Strategy | Location | Trigger Condition | Recovery Method |
|----------|----------|-------------------|-----------------|
| `collapse_drain_retry` | `query.ts:1087-1117` | `prompt_too_long` and not yet drained | Call `contextCollapse.recoverFromOverflow` to drain staged collapses |
| `reactive_compact_retry` | `query.ts:1119-1162` | Still `prompt_too_long` or media over limit | Call `reactiveCompact.tryReactiveCompact` to have Claude generate full summary |
| `max_output_tokens_escalate` | `query.ts:1210-1217` | Hit default 8k output limit | Upgrade to 64k limit and retry |
| `max_output_tokens_recovery` | `query.ts:1238-1246` | Hit any output limit | Inject "continue" prompt and retry (max 3 times) |
| `stop_hook_blocking` | `query.ts:1290-1302` | Stop hook blocking | Inject blocking error into context and retry |
| `token_budget_continuation` | `query.ts:1331-1338` | Task budget remaining | Inject budget prompt and continue execution |

**Lessons for emotion-robot:**
- This project's initial MVP does **not** need to implement all 6 recovery strategies, because round-driven is proactive (won't encounter prompt_too_long before triggering L3)
- However, 1 fallback should be retained: **retry mechanism for single LLM call failure** (corresponding to `max_output_tokens_recovery`'s idea -- clean up orphan messages + retry)
- If token fallback is added in the future (pending item #3's hybrid drive), `reactive_compact_retry` equivalent can be supplemented

### 9.8 Implementation Order Recommendation

Based on Claude Code's dependency relationships, emotion-robot's 3-layer compression is recommended to be implemented in the following order:

```
Step 1: L1 Snip pure rule implementation
        Reference services/compact/snipCompact.ts
        Interface: (messages) => { messages, tokensFreed }
        
Step 2: L3 Collapse single compression implementation (no progressive/staging)
        Reference services/compact/compact.ts:387 compactConversation
        Reference services/compact/prompt.ts prompt template design (but adapted for emotional scenarios)
        Interface: (messages_20rounds) => block_summary

Step 3: short_term_memory.json read/write logic
        Reference services/SessionMemory/sessionMemory.ts (if relevant)

Step 4: L4 Super-Compact
        Reference Step 2, but prompt changed to "pattern-level" integration template
        Interface: (blocks_4) => meta_block

Step 5: Trigger logic and scheduling
        Implemented within Memory Manager, no need for Claude Code's complex state machine
        Simple if rounds % 26 == 0 / if len(active_blocks) >= 4 is sufficient
```
