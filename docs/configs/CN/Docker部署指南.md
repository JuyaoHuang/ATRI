# Docker 部署指南

本文说明如何使用 Docker 部署 ATRI。当前推荐的生产部署方式是：

- 后端运行在 Docker 容器中，对宿主机 `127.0.0.1:8430` 暴露。
- 前端构建为静态文件，由前端容器内的 Nginx 提供服务，对宿主机 `127.0.0.1:5200` 暴露。
- 公网入口由宿主机 Nginx 负责 HTTPS、域名和反向代理。
- 前后端使用同一个域名，通过路径区分服务。

推荐访问结构：

```text
https://你的域名/              -> 前端页面
https://你的域名/api/*         -> 后端 API
https://你的域名/ws            -> 后端 WebSocket
https://你的域名/static/*      -> 后端静态资源兼容路径
https://你的域名/health        -> 后端健康检查
```

## 1. 相关文件

Docker 部署相关文件位于 `atri` 主仓库：

| 文件 | 作用 |
|---|---|
| `Dockerfile` | 后端镜像定义，安装 Python 依赖并启动 FastAPI |
| `docker-compose.prod.yml` | 生产环境编排，启动后端和前端容器 |
| `.dockerignore` | 排除虚拟环境、密钥、运行时数据和构建产物 |
| `docker/frontend.Dockerfile` | 前端构建镜像，构建 Vite 产物并交给 Nginx |
| `docker/frontend-nginx.conf` | 前端容器内部 Nginx 配置 |
| `docker/host-nginx.same-domain.conf` | 宿主机同域反向代理示例 |

## 2. 环境要求

服务器需要提前安装：

- Docker
- Docker Compose v2
- Nginx
- HTTPS 证书，例如 Let's Encrypt / Certbot 生成的证书

确认 Docker Compose 可用：

```bash
docker compose version
```

## 3. 获取代码

首次部署建议直接拉取子模块：

```bash
git clone --recurse-submodules https://github.com/JuyaoHuang/atri.git
cd atri
```

如果已经克隆过仓库，初始化或更新前端子模块：

```bash
git submodule update --init --recursive
```

前端子模块位于：

```text
frontend/
```

如果该目录为空，前端镜像会构建失败。

## 4. 配置环境变量

从模板创建 `.env`：

```bash
cp .env.example .env
```

至少需要填写：

```env
SILICONFLOW_API_KEY=sk-xxxx
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V3.2
COMPRESS_API_KEY=sk-xxxx
JWT_SECRET_KEY=replace-with-a-long-random-secret
```

如果使用 mem0 SaaS，需要填写：

```env
MEM0_API_KEY=m0-xxxx
```

如果启用 GitHub OAuth，需要填写：

```env
GITHUB_CLIENT_ID=xxxx
GITHUB_CLIENT_SECRET=xxxx
```

`.env` 包含密钥，不要提交到 Git。

## 5. 认证配置

如果 `config/auth.yaml` 中启用了认证：

```yaml
enabled: true
```

需要把 OAuth 回调地址改成生产域名：

```yaml
github:
  callback_url: https://你的域名/api/auth/callback

frontend:
  callback_url: https://你的域名/auth/callback
  login_url: https://你的域名/login
```

GitHub OAuth App 中的 Authorization callback URL 必须保持一致：

```text
https://你的域名/api/auth/callback
```

如果是本地或内网部署，可以保持：

```yaml
enabled: false
```

关闭认证时，不需要配置 GitHub OAuth。

## 6. 前端构建参数

`docker-compose.prod.yml` 默认使用同域路径：

```yaml
args:
  VITE_API_BASE_URL: /
  VITE_WS_URL: /ws
```

这意味着前端会请求：

```text
/api/...
/ws
```

因此更换生产域名时，通常不需要重新构建前端镜像。只要宿主机 Nginx 仍然把 `/api/` 和 `/ws` 转发到后端即可。

如果未来改成前后端不同域名，再把构建参数改成完整地址：

```yaml
args:
  VITE_API_BASE_URL: https://api.example.com
  VITE_WS_URL: wss://api.example.com/ws
```

不同域名部署还需要额外配置 CORS。

## 7. 启动服务

在 `atri` 根目录执行：

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

查看容器状态：

```bash
docker compose -f docker-compose.prod.yml ps
```

查看后端日志：

```bash
docker compose -f docker-compose.prod.yml logs -f backend
```

查看前端日志：

```bash
docker compose -f docker-compose.prod.yml logs -f frontend
```

停止服务：

```bash
docker compose -f docker-compose.prod.yml down
```

## 8. 持久化目录

`docker-compose.prod.yml` 挂载了以下目录：

| 宿主机路径 | 容器路径 | 作用 |
|---|---|---|
| `./data` | `/app/data` | 聊天记录、角色记忆、头像、Live2D 模型、Qdrant 本地数据 |
| `./models` | `/app/models` | ASR 等本地模型文件 |
| `./prompts/persona` | `/app/prompts/persona` | 角色人设文件 |

这些目录会在容器重建后保留。备份项目数据时，优先备份：

```text
data/
models/
prompts/persona/
.env
config/
```

`.env` 和 `config/` 可能包含敏感配置，备份时注意权限。

## 9. 宿主机 Nginx 配置

复制示例配置：

```bash
sudo cp docker/host-nginx.same-domain.conf /etc/nginx/conf.d/atri.conf
```

编辑 `/etc/nginx/conf.d/atri.conf`：

- 把 `example.com` 替换为你的域名。
- 把 `ssl_certificate` 改成证书路径。
- 把 `ssl_certificate_key` 改成私钥路径。

核心转发规则：

```nginx
location /ws {
    proxy_pass http://127.0.0.1:8430;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
}

location /api/ {
    proxy_pass http://127.0.0.1:8430;
}

location / {
    proxy_pass http://127.0.0.1:5200;
}
```

检查并重载 Nginx：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 10. 更新部署

更新主仓库和前端子模块：

```bash
git pull
git submodule update --init --recursive
```

重新构建并启动：

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

如果只修改了 `.env` 或 `config/`，通常不需要重新构建镜像，直接重启后端即可：

```bash
docker compose -f docker-compose.prod.yml restart backend
```

如果修改了前端代码或前端环境变量，需要重新构建前端镜像。

## 11. 常见问题

### 11.1 前端能打开，但接口请求失败

检查宿主机 Nginx 是否把 `/api/` 转发到后端：

```bash
curl https://你的域名/health
```

也可以直接在服务器上检查后端：

```bash
curl http://127.0.0.1:8430/health
```

如果后端不可用，查看日志：

```bash
docker compose -f docker-compose.prod.yml logs -f backend
```

### 11.2 WebSocket 连接失败

确认 Nginx 中 `/ws` 配置了 Upgrade 头：

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
```

如果启用了认证，WebSocket 需要携带有效 JWT。请先在前端完成登录。

### 11.3 OAuth 登录后跳转失败

检查三处地址是否一致：

- `config/auth.yaml` 的 `github.callback_url`
- GitHub OAuth App 的 Authorization callback URL
- 宿主机 Nginx 的 `/api/` 转发规则

同域生产环境推荐：

```text
https://你的域名/api/auth/callback
```

### 11.4 修改域名后前端仍请求旧地址

当前生产配置使用：

```yaml
VITE_API_BASE_URL: /
VITE_WS_URL: /ws
```

这种配置不会写死域名。如果你手动改成完整域名，则需要重新构建前端镜像。

### 11.5 构建前端失败

先确认子模块存在并且不是空目录：

```bash
git submodule update --init --recursive
ls frontend/package.json
```

然后重新构建：

```bash
docker compose -f docker-compose.prod.yml build frontend
```

### 11.6 容器启动后数据丢失

确认 `docker-compose.prod.yml` 中存在数据挂载：

```yaml
volumes:
  - ./data:/app/data
  - ./models:/app/models
  - ./prompts/persona:/app/prompts/persona
```

不要只备份镜像。运行时数据在宿主机挂载目录中。
