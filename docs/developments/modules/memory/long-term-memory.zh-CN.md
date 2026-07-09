---
status: active
owner: memory
created: 2026-07-09
updated: 2026-07-09
related_code:
  - src/memory/long_term.py
  - src/memory/retrieval_policy.py
  - src/memory/search_cache.py
  - src/memory/manager.py
  - src/service_context.py
  - src/routes/data.py
  - config/memory_config.yaml
---

# 长期记忆设计

本文描述当前代码中的长期记忆封装，也就是 `src/memory/long_term.py` 对 mem0 的统一包装。

## 模块定位

长期记忆的职责很窄：

- 构造 mem0 后端连接
- 把项目内消息形态翻译为 mem0 接受的形态
- 提供 `add()`、`search()`、`delete_all()` 和 `close()`
- 在出错时降级，不阻断聊天主流程

它不是：

- 聊天历史的权威存储
- 短期记忆的替代品
- 用户可见消息列表的数据源

## 构造与降级

`ServiceContext` 不会强制长期记忆必须成功初始化。`_safe_build_long_term()` 的行为是：

- 构造成功：返回 `LongTermMemory`
- 构造失败：记录 WARNING，返回 `None`

因此当前系统允许“短期记忆正常工作，但长期记忆关闭”的运行模式。

## 后端模式

`LongTermMemory` 读取 `config/memory_config.yaml` 中的 `mem0.mode`：

| 模式 | 实现 | 说明 |
| --- | --- | --- |
| `sdk` | `mem0.MemoryClient` | 直接使用托管 mem0 服务。 |
| `local_deploy` | `mem0.Memory.from_config(...)` | 本地或自托管部署，配置需先翻译到 mem0 期望的结构。 |

### `local_deploy` 配置翻译

ATRI 的配置支持 provider map，例如：

```yaml
vector_store:
  provider: pgvector
  providers:
    qdrant:
      config: ...
    pgvector:
      config: ...
```

`LongTermMemory` 只会验证并下发当前激活分支。未激活分支里的 `${ENV_VAR}` 占位符可以保持未解析状态，不会阻断启动。

`graph_store` 也已经保留翻译入口，但只有 `enabled: true` 时才会传给 mem0。

## 写入语义

`LongTermMemory.add(messages, user_id, agent_id, run_id)` 由 `MemoryManager` 在两种时机调用：

1. L3 压缩完成后，写入刚被压缩掉的窗口
2. `close_session()` 时，写入本次会话剩余的 dirty tail

当前写入的不是旧文档里那种“直接把原始聊天消息整批扔给 mem0”的抽象说法，而是：

- 输入来自 `MemoryManager` 当前维护的消息窗口
- human/ai/system 会先被翻译为 user/assistant/system
- `content` 保持原样

角色映射在边界上完成，避免把内部词汇 `human` / `ai` 直接交给 mem0。

任何 `add()` 异常都会被吞掉并记录 WARNING，聊天轮次不会因此失败。

## 检索语义

`MemoryManager.search_long_term()` 并不是每轮都无条件调用 mem0。它先经过 `LongTermRetrievalPolicy` 决策。

当前配置支持四种策略：

- `always`
- `interval`
- `triggered`
- `hybrid`

默认配置示例：

```yaml
retrieval:
  enabled: true
  policy: hybrid
  interval_turns: 10
  min_query_chars: 6
  trigger_keywords:
    - 记得
    - 还记得
    - 之前
```

`search()` 的实际行为：

1. 归一化查询文本
2. 用 `{user_id, agent_id}` 作为 filters
3. 通过 `top_k` 请求 mem0
4. 按 `threshold` 过滤得分
5. 返回最多 `limit` 条结果

如果后端报错，则返回 `[]` 并记录 WARNING，让主聊天在没有长期记忆的情况下继续进行。

## 搜索缓存

当 `mem0.retrieval.cache.enabled=true` 时，会启用进程内 `SearchCache`：

- 键：`(user_id, agent_id, query, limit, threshold)`
- 策略：TTL + LRU
- 作用域：单进程内

缓存只服务于 `search()`；一旦 `add()` 或 `delete_all()` 成功，就会失效对应 `(user_id, agent_id)` 作用域下的缓存条目。

## 删除语义

`LongTermMemory.delete_all()` 暴露给数据清理接口：

```text
DELETE /api/data/characters/{character_id}/long-term-memory
```

这条接口只提交 mem0 范围内的删除：

- `user_id`
- `agent_id`
- 可选 `run_id`

托管 mem0 可能返回异步“删除中”结果，因此调用方不能假设删除会立刻反映到控制台或下一次搜索。

## 关闭语义

`close()` 目前只做尽力而为的资源释放：

- `sdk` 模式通常无需额外清理
- `local_deploy` 模式会尝试关闭向量库客户端句柄

这一步由 `ServiceContext.close_all()` 在进程关闭时统一调用。

## 相关文档

- [短期记忆设计](short-term-memory.zh-CN.md)
- [Memory 模块长期设计入口](README.zh-CN.md)
