---
status: active
owner: agent
created: 2026-07-09
updated: 2026-07-09
source: docs/configs/EN/character-creation-guide.md
related_code:
  - src/agent/persona.py
  - src/routes/characters.py
  - prompts/persona/
---

# Persona Technical Notes

This document captures development-side rules for character Persona files. Character-author-facing guidance remains in [Character Creation Guide](../../../configs/EN/character-creation-guide.md).

## File Format

Persona files use Markdown + YAML Frontmatter:

```markdown
---
name: Character Display Name
avatar: avatar_filename.png
greeting: First greeting message
description: Character brief description
---

# Character Settings

This is the character system prompt.
```

The filename without `.md` becomes `character_id`.

## Data Model

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

Field sources:

| Field | Source | Default behavior |
| --- | --- | --- |
| `character_id` | Filename | Always exists |
| `name` | Frontmatter | Falls back to `character_id` |
| `avatar` | Frontmatter | Defaults to `null` |
| `greeting` | Frontmatter | Defaults to `null` |
| `description` | Frontmatter | Defaults to `null` |
| `system_prompt` | Markdown body | Required |

## Loading Flow

```text
prompts/persona/{character_id}.md
  -> src/agent/persona.py::load_persona()
  -> Persona(...)
  -> src/routes/characters.py
  -> frontend character selector / detail view
```

The backend dynamically scans `prompts/persona/`, so adding or editing a character file usually does not require a backend restart.

## API Output

The character list API does not return `system_prompt`:

```text
GET /api/characters
```

The character detail API returns `system_prompt`:

```text
GET /api/characters/{character_id}
```

The exact API contract should follow the backend route implementation and API documentation.

## Avatar Hosting

There are two avatar sources:

| Option | Path | Use case |
| --- | --- | --- |
| Frontend static assets | `frontend/public/avatars/` | Manual maintenance, simple deployment |
| Backend-hosted avatars | `data/avatars/` | Dynamic upload, backend-managed assets |

Recommended backend-hosted access path:

```text
/api/assets/avatars/{filename}
```

Compatibility path:

```text
/static/avatars/{filename}
```

The frontend should prefer `avatar_url` returned by the API. It should only build a compatibility URL when it only has an `avatar` filename.

## Constraints

- Persona files must use the `.md` extension.
- Frontmatter should use simple key-value pairs.
- `system_prompt` should not be too long, or it increases LLM cost and context pressure.
- Remote avatar URLs are not a stable user-facing capability yet.

## Related Documents

- [Character Creation Guide](../../../configs/EN/character-creation-guide.md)
