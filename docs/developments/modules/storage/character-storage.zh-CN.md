---
status: active
owner: storage
created: 2026-07-09
updated: 2026-07-09
related_code:
  - src/storage/character_storage.py
  - src/routes/characters.py
  - src/agent/persona.py
  - prompts/persona/
  - data/avatars/
---

# 角色存储设计

本文描述当前仓库里角色数据的落盘方式，也就是 `CharacterStorage` 如何管理 Persona markdown 与托管头像。

## 模块定位

`CharacterStorage` 负责：

- 列出和读取角色
- 创建、更新、删除可管理角色
- 校验并保存上传头像
- 为托管头像生成后端访问 URL

它不负责：

- 构建 `ChatAgent`
- 管理 Memory 模块下的 `data/characters/...` 目录
- 决定前端如何展示静态头像回退

## 当前存储位置

角色存储分为两块：

| 类型 | 路径 | 说明 |
| --- | --- | --- |
| Persona 文件 | `prompts/persona/{character_id}.md` | 角色正文与 frontmatter 的权威来源。 |
| 托管头像 | `data/avatars/{filename}` | 由 `/api/characters/{character_id}/avatar` 上传和替换。 |

这套存储与 Memory 模块的 `data/characters/{...}` 目录没有关系，不能混为一谈。

## Persona 文件结构

`CharacterStorage` 最终写回的格式与 `src/agent/persona.py` 的解析逻辑一致：

```markdown
---
name: 亚托莉
avatar: atri-1234abcd.png
greeting: 主人，早上好
description: 角色简介
created_at: 2026-07-09T12:34:56Z
updated_at: 2026-07-09T12:40:00Z
managed_by: atri
---

这里是 system prompt 正文。
```

其中：

- frontmatter 由 `render_yaml_mapping()` 生成
- 正文就是 `system_prompt`
- `character_id` 来自文件名，不写进 frontmatter

## 数据模型

运行时对外暴露的是 `CharacterRecord`：

| 字段 | 含义 |
| --- | --- |
| `character_id` | 文件名去掉 `.md` 后的标识。 |
| `name` | 角色显示名。 |
| `avatar` | frontmatter 中的头像文件名。 |
| `greeting` | 首屏问候语。 |
| `description` | 角色简介。 |
| `system_prompt` | markdown 正文。 |
| `created_at` / `updated_at` | frontmatter 时间戳。 |
| `managed_by` | 托管来源。 |

`CharacterRecord.is_system` 的判断规则是：

```text
managed_by != "atri"
```

这表示：

- `managed_by: atri` 的角色视为后端可管理角色
- 其他角色视为系统角色，受删除保护

## 创建与更新规则

### 名称与 ID

创建角色时：

- `name` 不能为空
- `system_prompt` 不能为空
- `name` 必须通过 `_validate_custom_character_name()`，也就是只允许字母与数字
- 名称大小写不敏感去重

`character_id` 的解析顺序：

1. 优先用请求里显式提供的 `character_id`
2. 否则回退到 `name`
3. 再经过 `_normalize_character_id()` 去掉 Windows 非法文件名字符
4. 如有重名则自动追加 `-2`、`-3` 等后缀

### 更新

更新会保留原有 `character_id`，只刷新可变字段与 `updated_at`。

系统角色仍可被读取和更新，但删除会被阻止。

## 头像管理

头像上传入口：

```text
POST /api/characters/{character_id}/avatar
```

当前校验规则：

- 仅支持 PNG / JPG / WEBP
- 最大 2 MB
- 新头像落盘后会删除旧的托管头像文件

保存后的文件名格式：

```text
{character_id}-{8hex}.{ext}
```

`build_avatar_url()` 只会为“确实位于 `data/avatars/` 且文件存在”的托管头像生成 URL：

```text
/api/assets/avatars/{filename}
```

如果角色 frontmatter 里写的是前端静态头像名，而不是托管头像，`build_avatar_url()` 会返回 `None`，调用方应走自己的兼容回退逻辑。

## REST 边界

`src/routes/characters.py` 当前提供：

| 接口 | 作用 |
| --- | --- |
| `GET /api/characters` | 返回角色摘要列表，不改变旧读取形态。 |
| `GET /api/characters/{character_id}` | 返回角色详情，包含完整 `system_prompt`。 |
| `POST /api/characters` | 创建角色。 |
| `PUT /api/characters/{character_id}` | 更新角色。 |
| `DELETE /api/characters/{character_id}` | 删除托管角色。 |
| `POST /api/characters/{character_id}/avatar` | 上传或替换托管头像。 |

异常会被路由层映射为 HTTP 错误，例如：

- `CharacterNotFoundError` -> `404`
- `CharacterNameConflictError` -> `400`
- `CharacterSystemDeleteError` -> `400`
- `AvatarValidationError` -> `400`

## 相关文档

- [Persona 技术说明](../agent/persona.zh-CN.md)
- [Storage 模块长期设计入口](README.zh-CN.md)
