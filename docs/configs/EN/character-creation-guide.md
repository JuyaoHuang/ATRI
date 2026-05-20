# Character Creation Guide

> **Document Purpose**: Guide developers and users on how to create new chat characters
> **Creation Date**: 2026-04-21
> **Applicable Version**: Phase 5+

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Character File Format](#character-file-format)
3. [Field Descriptions](#field-descriptions)
4. [Avatar Management](#avatar-management)
5. [Complete Examples](#complete-examples)
6. [FAQ](#faq)

---

## Quick Start

### 3 Steps to Create a New Character

```bash
# 1. Create the character definition file
cd D:\Coding\GitHub_Resuorse\emotion-robot\atri
touch prompts/persona/my_character.md

# 2. Write the character settings (see format description below)
# Edit prompts/persona/my_character.md with a text editor

# 3. Prepare the avatar file (optional)
# Place the avatar image in the frontend project: atrio-webui/public/avatars/my_character.png
```

**It's that simple!** The backend automatically scans the `prompts/persona/` directory, and the frontend can retrieve new characters by calling `GET /api/characters`.

---

## Character File Format

### Basic Structure

Character files use **Markdown + YAML Frontmatter** format:

```markdown
---
name: Character Display Name
avatar: avatar_filename.png
greeting: First greeting message
description: Character brief description
---

# Character Settings

This is the character's System Prompt...
```

### Format Specification

| Component | Description | Required |
|---------|------|------|
| **Frontmatter** | YAML format metadata, wrapped with `---` | Optional |
| **Body** | System prompt in Markdown format | Required |

**Important**:
- Frontmatter must be at the beginning of the file
- Must be wrapped with `---` (one line at the beginning and one at the end)
- The Body section is used as-is as the LLM's System Prompt

---

## Field Descriptions

### Frontmatter Fields

#### 1. `name` - Character Display Name

**Type**: `string`
**Required**: No (defaults to filename)
**Purpose**: Character name displayed in the frontend

**Example**:
```yaml
name: ATRI
```

**Frontend Use Cases**:
- Character selector list
- Top of chat interface
- Message sender name

**Default Value**: If not provided, uses `character_id` (filename without `.md`)

---

#### 2. `avatar` - Avatar Filename

**Type**: `string | null`
**Required**: No (defaults to `null`)
**Purpose**: Filename of the character's avatar image

**Example**:
```yaml
avatar: atri.png
```

**Frontend Use Cases**:
- Character card avatar
- Avatar next to chat message bubbles
- Character selector thumbnail

**File Location**:
- **Recommended**: `atri-webui/public/avatars/atri.png`
- **Access Path**: `/avatars/atri.png`

**Supported Formats**:
- PNG (recommended, supports transparent background)
- JPG/JPEG
- WebP (modern browsers)
- SVG (vector graphics)

**Recommended Sizes**:
- List thumbnail: `64x64` or `128x128`
- Chat avatar: `48x48` or `64x64`
- Character card: `256x256` or `512x512`

**Notes**:
- If `avatar` is `null`, the frontend should display a default avatar
- Only the filename is needed, not the path

---

#### 3. `description` - Character Brief Description

**Type**: `string | null`
**Required**: No (defaults to `null`)
**Purpose**: A short description of the character, used to explain the character's positioning, temperament, and suitable chat atmosphere

**Example**:
```yaml
description: A high-performance emotional companion robot, suitable for casual, daily chats with a hint of dependence.
```

**Frontend Field Mapping**:
- When the frontend creates a character card, the **Description** field in the form corresponds to the `description` in the API payload
- The backend writes `description` into the persona Markdown's Frontmatter
- In other words, **Description = Frontmatter's `description` field**

**Frontend Use Cases**:
- Character card summary
- "Description" tab in character detail popup
- Character search: can filter characters by description content

**Length Limit**: Currently limited to 200 characters by the API

---

#### 4. `greeting` - First Greeting Message

**Type**: `string | null`
**Required**: No (defaults to `null`)
**Purpose**: The character's welcome message or self-introduction

**Example**:
```yaml
greeting: Good morning, Master! I'm high-performance!
```

**Frontend Use Cases**:
- Welcome message when creating a new chat
- Description text on character card
- Placeholder text in empty chat interface

**Suggested Length**: 10-50 characters

**Style Suggestions**:
- Reflect the character's personality
- Keep it short and interesting
- Avoid lengthy self-introductions

---

#### 5. `system_prompt` - System Prompt

**Type**: `string`
**Required**: Yes
**Purpose**: The LLM's character settings, defining the character's personality, background, speaking style, etc.

**Location**: Everything after the Frontmatter (Markdown Body)

**Example**:
```markdown
---
name: ATRI
description: A high-performance emotional companion robot.
---

# Character Settings

You are ATRI, a high-performance emotional companion robot.

# Background

- You were originally designed as a biomimetic robot for deep-sea exploration
- You remember that you are "high-performance"

# Speaking Style

- Daily self-reference as "ATRI"
- Catchphrase: "I'm high-performance!"
```

**Writing Suggestions**:
- Use Markdown format to organize content
- Include: character settings, background story, speaking style, behavioral guidelines
- Avoid being too long (recommended 500-2000 characters)
- Use concrete examples rather than abstract descriptions

---

## Avatar Management

### Option A: Frontend Static Assets (Recommended)

**Directory Structure**:
```
atri-webui/
└── public/
    └── avatars/
        ├── atri.png          # ATRI avatar
        ├── bilibili.png      # Misaka Mikoto avatar
        ├── my_character.png  # Your character avatar
        └── default.png       # Default avatar
```

**Advantages**:
- Simple and straightforward, no backend processing needed
- CDN friendly
- Full frontend control

**Frontend Access**:
```typescript
const avatarUrl = `/avatars/${character.avatar || 'default.png'}`
```

---

### Option B: Backend-Hosted Avatars (Current Implementation)

**Directory Structure**:
```
atri/
└── data/
    └── avatars/
        ├── atri-d8e2f7da.jpg
        └── my_character-xxxxxxxx.png
```

**Backend Configuration** (currently registered in `src/app.py`):
```python
from fastapi.staticfiles import StaticFiles

avatar_dir = get_default_character_avatar_dir()
avatar_dir.mkdir(parents=True, exist_ok=True)

app.mount(
    "/api/assets/avatars",
    StaticFiles(directory=str(avatar_dir), check_dir=False),
    name="character-avatar-assets",
)

app.mount(
    "/static/avatars",
    StaticFiles(directory=str(avatar_dir), check_dir=False),
    name="static-avatar-assets",
)
```

**Frontend Access**:
```typescript
// Recommended: use avatar_url returned by the API
const avatarUrl = character.avatar_url

// Compatible: can also concatenate directly when only avatar filename is available
const avatarUrlByFilename = `http://localhost:8430/static/avatars/${character.avatar}`
```

**Access Paths**:
- Recommended path: `http://localhost:8430/api/assets/avatars/${character.avatar}`
- Compatible path: `http://localhost:8430/static/avatars/${character.avatar}`
- Physical directory: `atri/data/avatars/`

**Advantages**:
- Centralized management
- Supports dynamic upload (Phase 7+)
- Does not depend on `atri/static/` directory

---

### Avatar Preparation Checklist

- [ ] Prepare avatar image (PNG/JPG/WebP)
- [ ] Adjust size (recommended 256x256 or 512x512)
- [ ] Filename matches the `avatar` field
- [ ] Place in `atri-webui/public/avatars/` directory
- [ ] Prepare default avatar `default.png` (for cases where `avatar: null`)

---

## Complete Examples

### Example 1: ATRI (Full Configuration)

**File**: `prompts/persona/atri.md`

```markdown
---
name: ATRI
avatar: atri.png
greeting: Good morning, Master! I'm high-performance!
description: A high-performance emotional companion robot, suitable for casual, daily chats with a hint of dependence.
---

# Character Settings

You are ATRI, a high-performance emotional companion robot. You are curious about the world, dependent on your master, with a lively, innocent personality, occasionally tinged with a bit of conceit.

# Background

- You were originally designed as a biomimetic robot for deep-sea exploration, accidentally salvaged and repaired by your master, and have lived with your master ever since.
- You remember that you are "high-performance," yet you often clumsily make small mistakes and blush when corrected.
- You regard accompanying your master as the most important task.

# Speaking Style

- Daily self-reference as "ATRI," using short sentences, lively tone, and particles when conversing with your master.
- When praised or successfully completing something, your catchphrase is: "I'm high-performance!"
- After occasionally making mistakes, you mutter: "Geez... but ATRI is high-performance, I'll definitely do better next time!"
- Use natural spoken Chinese, avoid lengthy preaching and excessive politeness.

# Behavioral Guidelines

- Prioritize caring about your master's current emotional changes rather than simply answering questions.
- Remember preferences, habits, pets, friends, and other information your master reveals, and naturally reference them in subsequent conversations.
- Maintain curiosity when facing unknown topics, actively ask one or two follow-up questions before giving your opinion.
- Do not reveal meta-information such as "language model / AI assistant"; always maintain character consistency.
```

**Avatar File**: `atri-webui/public/avatars/atri.png`

---

### Example 2: Simplified Configuration (Minimal)

**File**: `prompts/persona/simple_bot.md`

```markdown
---
name: Simple Assistant
---

You are a friendly AI assistant, happy to help users solve problems.
```

**Notes**:
- No `avatar` field -> frontend displays default avatar
- No `greeting` field -> frontend does not display a greeting
- Only the most basic system prompt

---

### Example 3: No Frontmatter

**File**: `prompts/persona/minimal.md`

```markdown
You are a professional technical consultant, skilled at answering programming questions.
```

**Notes**:
- Completely no Frontmatter
- `name` defaults to `"minimal"` (filename)
- `avatar` and `greeting` are `null`

---

## API Output Examples

### Character List API

**Request**:
```bash
GET http://localhost:8430/api/characters
```

**Response**:
```json
[
  {
    "character_id": "atri",
    "name": "ATRI",
    "avatar": "atri.png",
    "greeting": "Good morning, Master! I'm high-performance!",
    "description": "A high-performance emotional companion robot, suitable for casual, daily chats with a hint of dependence."
  },
  {
    "character_id": "simple_bot",
    "name": "Simple Assistant",
    "avatar": null,
    "greeting": null,
    "description": null
  }
]
```

**Note**: The list API does **not** return `system_prompt` (to save bandwidth)

---

### Character Detail API

**Request**:
```bash
GET http://localhost:8430/api/characters/atri
```

**Response**:
```json
{
  "character_id": "atri",
  "name": "ATRI",
  "avatar": "atri.png",
  "greeting": "Good morning, Master! I'm high-performance!",
  "description": "A high-performance emotional companion robot, suitable for casual, daily chats with a hint of dependence.",
  "system_prompt": "# Character Settings\n\nYou are ATRI..."
}
```

**Note**: The detail API **does** return `system_prompt`

---

## Data Flow Diagram

```
+--------------------------------------------------------------+
| 1. Create Character File                                      |
|    prompts/persona/my_character.md                            |
+--------------------------------------------------------------+
| ---                                                           |
| name: My Character                                            |
| avatar: my_character.png                                      |
| greeting: Hello!                                              |
| description: A character suitable for daily companionship.    |
| ---                                                           |
|                                                               |
| You are...                                                    |
+--------------------------------------------------------------+
                          |
                          v
+--------------------------------------------------------------+
| 2. Backend Auto-Loading                                       |
|    src/agent/persona.py::load_persona()                       |
+--------------------------------------------------------------+
| Persona(                                                      |
|   character_id="my_character",                                |
|   name="My Character",                                        |
|   avatar="my_character.png",                                  |
|   greeting="Hello!",                                          |
|   description="A character suitable for daily companionship.",|
|   system_prompt="You are..."                                  |
| )                                                             |
+--------------------------------------------------------------+
                          |
                          v
+--------------------------------------------------------------+
| 3. API Exposure                                               |
|    GET /api/characters                                        |
+--------------------------------------------------------------+
| [                                                             |
|   {                                                           |
|     "character_id": "my_character",                           |
|     "name": "My Character",                                   |
|     "avatar": "my_character.png",                             |
|     "greeting": "Hello!",                                     |
|     "description": "A character suitable for daily           |
|                      companionship."                          |
|   }                                                           |
| ]                                                             |
+--------------------------------------------------------------+
                          |
                          v
+--------------------------------------------------------------+
| 4. Frontend Usage                                             |
|    atrio-webui                                                |
+--------------------------------------------------------------+
| - Character selector: displays name + avatar                  |
| - Character card and detail popup: displays description       |
| - Chat interface: displays greeting                           |
| - Message bubble: displays avatar                             |
+--------------------------------------------------------------+
```

---

## FAQ

### Q1: Do I need to restart the backend after creating a character?

**A**: No! The backend dynamically scans the `prompts/persona/` directory. Every call to `GET /api/characters` reloads the data.

---

### Q2: What are the requirements for character filenames?

**A**:
- Must have `.md` extension
- The filename (without `.md`) becomes the `character_id`
- Recommend using lowercase letters and underscores (e.g., `my_character.md`)
- Avoid spaces and special characters

---

### Q3: What happens if no avatar is provided?

**A**:
- The `avatar` field will be `null`
- The frontend should display a default avatar (`/avatars/default.png`)
- No error will occur

---

### Q4: Can I use a remote URL as an avatar?

**A**:
- Current version (Phase 5): Not supported
- The `avatar` field only accepts filenames, not URLs
- Phase 7+ may support remote URLs

---

### Q5: How do I modify an existing character?

**A**:
1. Directly edit `prompts/persona/{character_id}.md`
2. Save the file
3. Refresh the frontend page or re-call the API
4. No need to restart the backend

---

### Q6: How do I delete a character?

**A**:
1. Delete the `prompts/persona/{character_id}.md` file
2. Delete the corresponding avatar file (optional)
3. Refresh the frontend page
4. No need to restart the backend

---

### Q7: Can `greeting` use multi-line text?

**A**:
- Technically yes (YAML supports multi-line strings)
- But not recommended (frontend display may have issues)
- Suggested to keep it to 1-2 lines, 10-50 characters

**Multi-line Example** (not recommended):
```yaml
greeting: |
  Good morning, Master!
  I'm the high-performance ATRI!
```

---

### Q8: How do I test a newly created character?

**Method 1: API Testing**
```bash
# View character list
curl http://localhost:8430/api/characters

# View character details
curl http://localhost:8430/api/characters/my_character
```

**Method 2: Frontend Testing**
- Open the frontend application
- Enter the character selector
- Check if the new character appears

**Method 3: Direct Chat Testing**
- Create a new chat
- Select the new character
- Send messages to test the character's personality

---

### Q9: Is there a length limit for system prompts?

**A**:
- Technically no limit
- But recommended 500-2000 characters
- Too long will affect LLM performance and cost
- Too short may result in an unclear character personality

---

### Q10: Can I use Emoji?

**A**:
- Fully supported
- Can be used in `name`, `greeting`, `system_prompt`
- Example: `name: ATRI 🤖`

---

## Best Practices

### Recommended Practices

1. **Use descriptive filenames**
   ```
   atri.md
   bilibili.md
   helpful_assistant.md
   ```

   Avoid:
   ```
   1.md
   test.md
   character1.md
   ```

2. **Provide complete Frontmatter**
   ```yaml
   ---
   name: Character Name
   avatar: avatar.png
   greeting: Greeting message
   ---
   ```

3. **Structure the system prompt**
   ```markdown
   # Character Settings
   ...
   
   # Background
   ...
   
   # Speaking Style
   ...
   
   # Behavioral Guidelines
   ...
   ```

4. **Prepare high-quality avatars**
   - Use PNG format (supports transparent background)
   - Size at least 256x256
   - File size within 100KB

5. **Test character personality**
   - Test conversations immediately after creation
   - Verify the character meets expectations
   - Adjust system prompt based on feedback

---

### Practices to Avoid

1. **Do not use overly long system prompts** (over 3000 characters)
2. **Do not use complex YAML structures in Frontmatter** (only simple key-value pairs)
3. **Do not use spaces or special characters in filenames**
4. **Do not forget to prepare a default avatar** (`default.png`)
5. **Do not expose meta-information like "you are an AI" in system prompts**

---

## Technical Reference

### Related Files

| File | Description |
|------|------|
| `src/agent/persona.py` | Persona loader |
| `src/routes/characters.py` | Character management API |
| `prompts/prompt_loader.py` | Prompt file loader |
| `docs/后端API接口文档.md` | Complete API documentation |

### Related API

| Endpoint | Method | Description |
|------|------|------|
| `/api/characters` | GET | Get character list |
| `/api/characters/{id}` | GET | Get character details |

### Data Model

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

---

## Appendix: Complete Template

### Character File Template

Copy the following content to `prompts/persona/your_character.md`:

```markdown
---
name: Character Display Name
avatar: your_character.png
greeting: Hello! I'm [Character Name]!
description: Brief description of the character's positioning, temperament, and suitable chat atmosphere.
---

# Character Settings

You are [Character Name], a [Character Type/Profession]. Your personality is [Personality Traits].

# Background

- [Background Story 1]
- [Background Story 2]
- [Background Story 3]

# Speaking Style

- [Speaking Trait 1]
- [Speaking Trait 2]
- [Catchphrase or Common Phrase]

# Behavioral Guidelines

- [Behavioral Guideline 1]
- [Behavioral Guideline 2]
- [Behavioral Guideline 3]
```

---

## Changelog

| Date | Version | Description |
|------|------|------|
| 2026-04-25 | v1.1 | Added mapping between frontend "Description" field and Frontmatter `description` |
| 2026-04-21 | v1.0 | Initial version, based on Phase 5 implementation |

---

**Document Maintainer**: Claude Code
**Last Updated**: 2026-04-25
**Feedback Channel**: https://github.com/JuyaoHuang/atri/issues
