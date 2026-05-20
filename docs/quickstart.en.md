## Prerequisites

- Python `>= 3.11`
- [uv](https://docs.astral.sh/uv/) for managing Python dependencies
- Node.js `>= 18`
- npm `>= 9`

It is recommended to use two separate terminals to start the backend and frontend.

## 1. One-Click Installation

> For Docker deployment, see the [Docker Deployment Guide](./configs/Docker部署指南.md)

If you have already cloned the `atri` main repository, run the following in the repository root:

```powershell
.\install.bat --skip-clone
```

Linux / macOS:

```bash
bash install.sh --skip-clone
```

The script will automatically:

- Initialize and pull the `frontend` submodule
- Create `.env` from `.env.example`
- Install backend dependencies using the Tsinghua PyPI mirror
- Install frontend dependencies using the npm China mirror

Default mirrors:

| Dependency | Default Mirror |
|---|---|
| Python / PyPI | `https://pypi.tuna.tsinghua.edu.cn/simple` |
| npm | `https://registry.npmmirror.com` |

Aliyun PyPI fallback mirror:

```text
https://mirrors.aliyun.com/pypi/simple/
```

If you run the script in an empty directory, you can have it clone the repository first:

```powershell
.\install.bat --repo-url https://github.com/JuyaoHuang/atri.git --target-dir atri
```

Linux / macOS:

```bash
bash install.sh --repo-url https://github.com/JuyaoHuang/atri.git --target-dir atri
```

To use different mirrors:

```powershell
.\install.bat --pypi-index https://pypi.tuna.tsinghua.edu.cn/simple --npm-registry https://registry.npmmirror.com
```

Using the Aliyun PyPI mirror:

```powershell
.\install.bat --pypi-index https://mirrors.aliyun.com/pypi/simple/ --npm-registry https://registry.npmmirror.com
```

After installation, edit `.env` to fill in `SILICONFLOW_API_KEY` and `COMPRESS_API_KEY`, then start the backend and frontend separately.

## 2. Manual Code Retrieval

When cloning the main repository for the first time, it is recommended to pull submodules directly:

```powershell
git clone --recurse-submodules https://github.com/JuyaoHuang/atri.git
cd atri
```

If the main repository has already been cloned, initialize the frontend submodule:

```powershell
git submodule update --init --recursive
```

To update the frontend submodule later:

```powershell
git submodule update --remote frontend
```

Current frontend submodule configuration:

| Item | Value |
|---|---|
| Submodule path | `frontend` |
| Submodule repository | `https://github.com/JuyaoHuang/atri-webui.git` |
| Tracked branch | `main` |

## 3. Starting the Backend

Make sure you are in the `atri` main repository root. If you opened a new terminal, navigate to the main repository first:

```powershell
cd path\to\atri
```

Install dependencies:

```powershell
uv sync
```

Copy the environment variable template:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and fill in at least the keys used by the main chat model and the compression model:

```env
SILICONFLOW_API_KEY=sk-xxxx
COMPRESS_API_KEY=sk-xxxx
```

The default configuration uses the OpenAI-compatible interface. Models and endpoints are configured in `config/llm_config.yaml`. You can change `base_url` and `model` to your own provider, such as SiliconFlow, DeepSeek, or any other OpenAI-compatible API.

Start the backend:

```powershell
uv run python -m src.main
```

Default addresses:

| Service | Address |
|---|---|
| HTTP API | `http://localhost:8430` |
| WebSocket | `ws://localhost:8430/ws` |
| Swagger UI | `http://localhost:8430/docs` |
| OpenAPI JSON | `http://localhost:8430/openapi.json` |

When the backend starts successfully, you will see `Server starting | host=0.0.0.0 | port=8430` in the logs.

## 4. Starting the Frontend

Open a second terminal and navigate to the frontend directory:

```powershell
cd path\to\atri\frontend
```

Install dependencies:

```powershell
npm install
```

Make sure `.env.development` points to the local backend:

```env
VITE_API_BASE_URL=http://localhost:8430
VITE_WS_URL=ws://localhost:8430/ws
```

Start the frontend:

```powershell
npm run dev
```

Access:

```text
http://localhost:5200
```

## 5. Minimal Configuration

ATRI uses the root configuration `config.yaml` as the entry point, which then loads sub-configurations under `config/`:

| Config File | Purpose |
|---|---|
| `config/llm_config.yaml` | Chat model, L3 compression model, L4 compression model, title generation model |
| `config/memory_config.yaml` | Three-layer memory compression, mem0 long-term memory, vector retrieval parameters |
| `config/server_config.yaml` | Backend listen address, port, CORS, WebSocket heartbeat |
| `config/storage_config.yaml` | Chat history storage method, default is local JSON |
| `config/asr_config.yaml` | Speech recognition provider |
| `config/tts_config.yaml` | Speech synthesis provider |
| `config/auth.yaml` | GitHub OAuth, JWT, whitelist, and authentication toggle |

For local development, you typically only need to modify:

```text
.env
config/llm_config.yaml
config/memory_config.yaml
config/auth.yaml
```

## 6. Memory System Configuration

The core of ATRI is memory storage. It splits conversation memory into three layers:

| Layer | Trigger | Purpose |
|---|---|---|
| L1 Snip | Every turn | Rule-based cleaning of filler words, duplicate input, and overly long input |
| L3 Collapse | Every 26 turns | Compresses the earlier 20 turns into an event-level summary |
| L4 Super-Compact | Every 4 L3 blocks | Distills multiple event summaries into long-term profiles and patterns |

These parameters are configured in `config/memory_config.yaml`:

```yaml
short_term:
  collapse:
    trigger_rounds: 26
    compress_rounds: 20
    keep_recent_rounds: 6
  super_compact:
    trigger_blocks: 4
```

Long-term memory is provided by mem0. The default mode is `sdk`:

```yaml
mem0:
  mode: sdk
  sdk:
    api_key: ${MEM0_API_KEY}
```

If using mem0 SaaS, fill in the following in `.env`:

```env
MEM0_API_KEY=m0-xxxx
```

If you do not want to connect to the cloud mem0 for now, you can change the mode in `config/memory_config.yaml` to local deployment:

```yaml
mem0:
  mode: local_deploy
```

Local deployment uses `./data/qdrant` as the embedded vector store by default, and reuses the `SILICONFLOW_API_KEY` from `.env` to call the embedding and fact extraction models.

If you are deploying to the cloud but do not want to use mem0 SaaS, you can continue using `mem0.local_deploy` and switch the vector store to Neon PostgreSQL + pgvector:

```yaml
mem0:
  mode: local_deploy
  local_deploy:
    vector_store:
      provider: pgvector
      providers:
        qdrant:
          config:
            path: ./data/qdrant
        pgvector:
          config:
            connection_string: ${DB_MEMORY_URL}
            collection_name: atri_memories
            embedding_model_dims: 1024
            hnsw: true
            diskann: false
            minconn: 1
            maxconn: 5
```

`provider` indicates the currently enabled vector store; `providers` retains multiple configurations. When using `qdrant` by default, `${DB_MEMORY_URL}` in the `pgvector` section will not be forcibly validated. Before switching to `pgvector`, you need to enable the `vector` extension in your Neon database and ensure `DB_MEMORY_URL` is configured in `.env`.

## 7. Authentication Configuration

Authentication is disabled by default for local development:

```yaml
# config/auth.yaml
enabled: false
```

When authentication is disabled, the frontend goes directly to the main page, and the backend uses a default user identity. This is suitable for standalone deployment and local debugging.

For public network deployment, it is recommended to enable authentication:

```yaml
enabled: true
```

Before enabling authentication, configure the following in `.env`:

```env
JWT_SECRET_KEY=replace-with-a-long-random-secret
GITHUB_CLIENT_ID=Iv1.xxxxx
GITHUB_CLIENT_SECRET=github_oauth_client_secret
```

Generate `JWT_SECRET_KEY`:

```powershell
uv run python scripts/generate_jwt_secret.py
```

Recommended settings for the GitHub OAuth App during local development:

| GitHub OAuth Field | Value |
|---|---|
| Homepage URL | `http://localhost:5200` |
| Authorization callback URL | `http://localhost:8430/api/auth/callback` |

The frontend callback in `config/auth.yaml` should also match the port:

```yaml
frontend:
  callback_url: http://localhost:5200/auth/callback
  login_url: http://localhost:5200/login
```

The whitelist controls which GitHub users are allowed to log in:

```yaml
whitelist:
  users:
    - your-github-username
```

The default JWT validity period is 7 days:

```yaml
jwt:
  expire_days: 7
```

## 8. Common Development Commands

Backend:

```powershell
cd path\to\atri

# Start the service
uv run python -m src.main

# Run tests
uv run pytest

# Ruff check
uv run ruff check src tests

# Mypy check
uv run python -m mypy src/ --ignore-missing-imports
```

Frontend:

```powershell
cd path\to\atri\frontend

# Start the dev server
npm run dev

# Type check
npm run type-check

# Production build
npm run build
```

Common submodule commands:

```powershell
cd path\to\atri

# Check submodule status
git submodule status

# Initialize or restore submodule content
git submodule update --init --recursive

# Pull the latest commit from the frontend tracked branch
git submodule update --remote frontend
```

If you committed frontend changes in `frontend/`, you need to commit and push in the submodule repository first, then go back to `atri` to commit the submodule pointer change:

```powershell
cd path\to\atri\frontend
git add .
git commit --no-gpg-sign -m "your frontend change"
git push

cd ..
git add frontend
git commit --no-gpg-sign -m "chore: update frontend submodule"
```

## 9. Data Directory

Runtime data is written to `data/` in the main repository by default:

| Directory | Contents |
|---|---|
| `data/chats` | Chat sessions and message history |
| `data/characters` | Character configurations, avatars, and other resources |
| `data/live2d` | Live2D model assets |
| `data/qdrant` | Local mem0 vector store |

`chat_history` is the source of truth for the memory system. If the short-term memory file is corrupted, it can be rebuilt from the chat history.

## 10. FAQ

### The frontend directory is empty

This means the frontend submodule has not been initialized. Run the following in the `atri` directory:

```powershell
git submodule update --init --recursive
```

### The frontend is not the latest version

Run the following in the `atri` directory:

```powershell
git submodule update --remote frontend
```

If `atri` shows `modified: frontend`, it means the submodule pointer has changed. After confirming the frontend version is correct, you need to commit this pointer change in the main repository.

### The backend exits immediately after starting

This is usually caused by a missing `SILICONFLOW_API_KEY` or `COMPRESS_API_KEY` in `.env`, or the model endpoint in `config/llm_config.yaml` being unavailable. First check the backend logs for `LLM role failed`.

### The frontend won't open or requests fail

Make sure the backend is running and check `frontend/.env.development`:

```env
VITE_API_BASE_URL=http://localhost:8430
VITE_WS_URL=ws://localhost:8430/ws
```

You need to restart `npm run dev` after making changes.

### WebSocket returns 403

If authentication is enabled, the WebSocket must carry a valid JWT. Please log in via the frontend first.
If you are using it locally on a single machine, you can change `config/auth.yaml` to:

```yaml
enabled: false
```

Then restart the backend.

### Still redirected to the login page after logging in

Common causes:

- `JWT_SECRET_KEY` was changed, but the browser still holds the old token
- The GitHub username is not in `whitelist.users`
- The GitHub OAuth callback URL does not match `config/auth.yaml`
- The frontend `VITE_API_BASE_URL` points to the wrong backend

You can clear `atri_auth_token` from the browser's LocalStorage and then log in again.

### Swagger is accessible but chat returns no response

Check:

- Whether the LLM API key in `.env` is valid
- Whether the `base_url` in `config/llm_config.yaml` includes `/v1`
- Whether the model name is supported by the current provider
- Whether the compression model `COMPRESS_API_KEY` is also filled in

## 11. Next Steps

- Read `docs/configs/认证系统使用指南.md` to configure public network login.
- Read `docs/configs/ASR配置说明.md` and `docs/configs/TTS配置说明.md` to enable the voice pipeline.
- Read `docs/configs/角色创建指南.md` to add your own characters, avatars, and greetings.
- View the backend API documentation at `http://localhost:8430/docs`.
