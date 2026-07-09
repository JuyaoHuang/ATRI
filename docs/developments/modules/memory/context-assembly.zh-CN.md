---
status: active
owner: memory
created: 2026-07-09
updated: 2026-07-09
source:
  - ../../module-design/CN/记忆系统设计讨论.md
  - src/memory/manager.py
  - src/memory/retrieval_policy.py
  - src/memory/search_cache.py
related_code:
  - src/memory/manager.py
  - src/memory/retrieval_policy.py
  - src/memory/search_cache.py
---

# 记忆上下文组装设计

本文专门说明 `MemoryManager.build_llm_context()` 的长期设计。它回答：

1. 每轮调用 LLM 时，记忆模块按什么顺序拼装 payload。
2. 长期记忆检索何时发生、为什么可能跳过。
3. runtime context 如何进入最终 user turn。

## 设计目标

当前上下文组装的长期目标只有两个：

1. 让 LLM 看到的信息顺序稳定、可预测。
2. 把长期记忆检索、短期压缩块和当前输入的拼装责任集中在一处，而不是散给 `ChatAgent` 或路由层。

## 组装顺序

当前实现严格遵循旧设计稿 §3.5 的顺序：

1. `system_prompt`
2. 长期记忆检索结果
3. `meta_blocks`
4. `active_blocks`
5. `recent_messages`
6. 本轮 `user_input`

这不是“推荐顺序”，而是当前代码的真实行为。

## 每一段的来源

### 1. `system_prompt`

来源：

- `ChatAgent` 调 `build_llm_context(user_input, system_prompt=persona.system_prompt, ...)`

长期意义：

- 角色设定在记忆模块里被放到 payload 头部；
- 调用层不再额外 prepend 第二份 `system` 消息；
- Persona 注入和记忆拼装统一在一条路径上闭环。

### 2. 长期记忆检索结果

来源：

- `await self.search_long_term(user_input)`

当前返回结果会被包装成一条：

```text
关于这位用户，你记得：
- fact 1
- fact 2
```

长期意义：

- mem0 命中不直接裸展开成多条 message；
- 统一作为一条 `role=system` 的长期事实提示；
- 未命中时整段跳过，不保留空壳。

### 3. `meta_blocks`

来源：

- `self._state["meta_blocks"]`

当前渲染顺序是：

- 存储时 newest-first
- 渲染时 oldest-first

这条细节很重要。它确保：

- 内部存储利于插入最新元块；
- 发送给 LLM 时仍按时间正序阅读。

### 4. `active_blocks`

来源：

- `self._state["active_blocks"]`

当前直接按列表顺序展开，不再额外倒序。

### 5. `recent_messages`

来源：

- `self._state["recent_messages"]`

这里的角色会做一次最终映射：

- `human -> user`
- `ai -> assistant`
- `system -> system`

这让上游内部仍可以使用 `human/ai` 词汇，而发送给 LLM 的最终格式保持 OpenAI 风格。

### 6. 本轮 `user_input`

来源：

- `ChatAgent.chat(user_input, ...)` 的原始输入

长期约束：

- 当前轮输入保持 raw，不先做 L1；
- L1 清洗只在 `on_round_complete()` 之后影响落盘与后续轮次；
- 这样能保留当前轮次最鲜活的表达细节。

## 长期检索策略

长期记忆并不是每轮必查。`search_long_term()` 内部会先走：

- `LongTermRetrievalPolicy.decide(...)`

当前支持：

- `always`
- `interval`
- `triggered`
- `hybrid`

因此“本轮为什么没查 mem0”本身就是设计的一部分，而不是偶发现象。

## 搜索缓存

若配置开启缓存，搜索结果会先经过 `SearchCache`：

- key = `user_id + agent_id + normalized query + limit + threshold`
- `mem0.add()` 与 `delete_all()` 会主动失效对应 scope

长期意义：

- 缓存只节省重复搜索；
- 不改变长期记忆真相；
- 不把缓存结果写回 short-term state。

## runtime context 注入

当前 `runtime_context` 只正式消费 datetime 模块。

处理顺序是：

1. 从 `runtime_context["datetime"]` 提取：
   - `iso`
   - `local`
   - `time_zone`
   - `utc_offset`
2. 规范化成一段文本
3. 包装为隐藏 `<context>` 片段
4. 追加到最终 `user_input` 尾部

也就是说，runtime context 当前不是单独插入 payload 第 7 段，而是成为最后一条 `user` 消息的一部分。

## 当前明确不做的事

当前上下文组装**不**做这些事：

- 直接把 mem0 命中展开成多条历史消息；
- 在 `ChatAgent` 层重复构造 system prompt；
- 对当前 `user_input` 先做 L1 再发给 LLM；
- 在这里调用 LLM 本身；
- 把翻译结果或 TTS 播放状态混入聊天上下文。

## 与旧设计稿的对齐和差异

与旧设计稿对齐的部分：

- 6 段顺序保持一致；
- 长期事实位于 system prompt 之后；
- L4/L3/近期 raw 在当前输入之前。

与旧设计稿相比，当前实现更明确的地方：

- `meta_blocks` 存储顺序和渲染顺序分离；
- runtime datetime context 以隐藏 user tail 注入，而不是独立新段落；
- 长期检索是否发生由策略决定，不再暗含“每轮都查”。

## 相关文档

- [design.zh-CN.md](design.zh-CN.md)
- [short-term-memory.zh-CN.md](short-term-memory.zh-CN.md)
- [long-term-memory.zh-CN.md](long-term-memory.zh-CN.md)
