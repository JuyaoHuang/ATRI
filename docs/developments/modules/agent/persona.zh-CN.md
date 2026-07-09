---
status: active
owner: agent
created: 2026-07-09
updated: 2026-07-09
source: docs/configs/CN/角色创建指南.md
related_code:
  - src/agent/persona.py
  - src/routes/characters.py
  - prompts/persona/
---

# Persona 技术说明

本文沉淀角色 Persona 的开发侧规则。角色作者使用指南见 [角色创建指南](../../../configs/CN/角色创建指南.md)。

## 文件格式

Persona 文件使用 Markdown + YAML Frontmatter：

```markdown
---
name: 角色显示名称
avatar: avatar_filename.png
greeting: 首次问候语
description: 角色简介
---

# 角色设定

这里是角色系统提示词。
```

文件名去掉 `.md` 后即为 `character_id`。

## 数据模型

```python
@dataclass(frozen=True)
class Persona:
    character_id: str
    name: str
    avatar: str | None
    greeting: str | None
    system_prompt: str
    description: str | None = None
```

字段来源：

| 字段 | 来源 | 默认行为 |
| --- | --- | --- |
| `character_id` | 文件名 | 必定存在 |
| `name` | Frontmatter | 缺省使用 `character_id` |
| `avatar` | Frontmatter | 缺省为 `null` |
| `greeting` | Frontmatter | 缺省为 `null` |
| `description` | Frontmatter | 缺省为 `null` |
| `system_prompt` | Markdown body | 必须存在 |

## 加载流程

```text
prompts/persona/{character_id}.md
  -> src/agent/persona.py::load_persona()
  -> Persona(...)
  -> src/routes/characters.py
  -> frontend character selector / detail view
```

后端会动态扫描 `prompts/persona/`，因此新增或修改角色文件后通常不需要重启后端。

## API 输出

角色列表 API 不返回 `system_prompt`，用于降低列表请求负担：

```text
GET /api/characters
```

角色详情 API 返回 `system_prompt`：

```text
GET /api/characters/{character_id}
```

完整 API 契约仍以后端路由实现和 API 文档为准。

## 头像托管

当前存在两种头像来源：

| 方案 | 路径 | 适用场景 |
| --- | --- | --- |
| 前端静态资源 | `frontend/public/avatars/` | 手工维护、简单部署 |
| 后端托管头像 | `data/avatars/` | 动态上传、后端集中管理 |

后端托管头像的推荐访问路径：

```text
/api/assets/avatars/{filename}
```

兼容路径：

```text
/static/avatars/{filename}
```

前端优先使用 API 返回的 `avatar_url`。只有 `avatar` 文件名时，才按兼容规则拼接。

## 约束

- Persona 文件必须是 `.md`。
- Frontmatter 只建议使用简单键值对。
- `system_prompt` 不应过长，否则会增加 LLM 成本和上下文压力。
- 用户侧远程头像 URL 当前不是稳定能力。

## 相关文档

- [角色创建指南](../../../configs/CN/角色创建指南.md)
