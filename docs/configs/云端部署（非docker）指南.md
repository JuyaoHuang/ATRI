# 云端部署（非 Docker）指南

本文说明如何在服务器上直接部署 ATRI，不使用 Docker。推荐生产结构是：

- 后端 FastAPI 使用 `systemd` 托管，监听 `127.0.0.1:8430`。
- 前端使用 Vite 构建为静态文件，由宿主机 Nginx 直接提供。
- 公网入口只开放 Nginx 的 `80/443`。
- 前后端使用同一个域名，通过路径分流。

推荐访问结构：

```text
https://你的域名/              -> 前端页面
https://你的域名/api/*         -> 后端 API
https://你的域名/ws            -> 后端 WebSocket
https://你的域名/static/*      -> 后端静态资源兼容路径
https://你的域名/health        -> 后端健康检查
```

## 1. 环境要求

服务器需要提前安装：

- Python `>= 3.11`
- [uv](https://docs.astral.sh/uv/)
- Node.js `>= 18`
- npm `>= 9`
- Nginx
- HTTPS 证书，例如 Let's Encrypt / Certbot 生成的证书

建议部署目录：

```text
/opt/atri
```

## 2. 获取代码

首次部署：

```bash
cd /opt
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

如果该目录为空，前端无法构建。

## 3. 配置环境变量

创建 `.env`：

```bash
cp .env.example .env
```

至少需要填写：

```env
OPENAI_API_KEY=sk-xxxx
OPENAI_BASE_URL=https://api.siliconflow.cn/v1
OPENAI_MODEL=deepseek-ai/DeepSeek-V3.2
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

## 4. 安装后端依赖

在 `atri` 根目录执行：

```bash
uv sync
```

测试后端能否启动：

```bash
uv run python -m src.main
```

看到服务监听 `8430` 后，可以按 `Ctrl+C` 停止，继续配置 `systemd`。

## 5. 使用 systemd 托管后端

创建服务文件：

```bash
sudo nano /etc/systemd/system/atri.service
```

写入：

```ini
[Unit]
Description=ATRI FastAPI Backend
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/atri
EnvironmentFile=/opt/atri/.env
ExecStart=/usr/local/bin/uv run python -m src.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

如果你的 `uv` 不在 `/usr/local/bin/uv`，先确认路径：

```bash
which uv
```

然后把 `ExecStart` 中的路径替换为实际路径。

启用并启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable atri
sudo systemctl start atri
sudo systemctl status atri
```

查看日志：

```bash
journalctl -u atri -f
```

验证后端：

```bash
curl http://127.0.0.1:8430/health
```

预期返回：

```json
{"status":"ok"}
```

## 6. 构建前端

进入前端子模块：

```bash
cd /opt/atri/frontend
npm ci
```

生产环境推荐使用同源路径构建：

```bash
VITE_API_BASE_URL=/ VITE_WS_URL=/ws npm run build
```

构建产物位于：

```text
/opt/atri/frontend/dist
```

同源路径的含义是：

```text
/api/...  -> 后端 API
/ws       -> 后端 WebSocket
```

因此更换域名时，通常不需要重新构建前端，只要 Nginx 仍然按路径分流即可。

如果你使用 Windows PowerShell 在服务器上构建，环境变量写法不同：

```powershell
$env:VITE_API_BASE_URL="/"
$env:VITE_WS_URL="/ws"
npm run build
```

## 7. 配置宿主机 Nginx

创建 Nginx 配置：

```bash
sudo nano /etc/nginx/conf.d/atri.conf
```

写入并替换域名与证书路径：

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 80;
    server_name 你的域名;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name 你的域名;

    client_max_body_size 100m;

    ssl_certificate /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;

    root /opt/atri/frontend/dist;
    index index.html;

    location /ws {
        proxy_pass http://127.0.0.1:8430;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8430;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        proxy_pass http://127.0.0.1:8430;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        proxy_pass http://127.0.0.1:8430;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

检查并重载 Nginx：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 8. 认证配置

如果 `config/auth.yaml` 中启用了认证：

```yaml
enabled: true
```

生产环境需要修改回调地址：

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

如果是个人本地部署或内网部署，可以关闭认证：

```yaml
enabled: false
```

修改 `config/auth.yaml` 或 `.env` 后，重启后端：

```bash
sudo systemctl restart atri
```

## 9. 数据与备份

非 Docker 部署时，运行时数据直接保存在项目目录下：

| 路径 | 作用 |
|---|---|
| `data/` | 聊天记录、角色记忆、头像、Live2D 模型、Qdrant 本地数据 |
| `models/` | ASR 等本地模型文件 |
| `prompts/persona/` | 角色人设文件 |
| `.env` | 环境变量和密钥 |
| `config/` | 分层配置文件 |

建议定期备份：

```bash
tar -czf atri-backup.tar.gz data models prompts/persona config .env
```

注意：`.env` 可能包含 API Key、OAuth Secret、JWT Secret，备份文件需要妥善保存。

## 10. 更新部署

拉取更新：

```bash
cd /opt/atri
git pull
git submodule update --init --recursive
```

更新后端依赖：

```bash
uv sync
sudo systemctl restart atri
```

更新前端：

```bash
cd /opt/atri/frontend
npm ci
VITE_API_BASE_URL=/ VITE_WS_URL=/ws npm run build
sudo systemctl reload nginx
```

如果只修改了 `.env` 或 `config/`，通常只需要：

```bash
sudo systemctl restart atri
```

## 11. 常见问题

### 11.1 前端页面能打开，但接口请求失败

先检查后端：

```bash
curl http://127.0.0.1:8430/health
```

再检查 Nginx 反代：

```bash
curl https://你的域名/health
```

如果后端不可用，查看日志：

```bash
journalctl -u atri -f
```

### 11.2 WebSocket 连接失败

确认 Nginx 中 `/ws` 配置了：

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
```

如果启用了认证，前端必须先完成登录，WebSocket 才会携带有效 JWT。

### 11.3 OAuth 登录后跳转失败

检查三处地址是否一致：

- `config/auth.yaml` 的 `github.callback_url`
- GitHub OAuth App 的 Authorization callback URL
- Nginx 的 `/api/` 反向代理规则

同域生产环境推荐：

```text
https://你的域名/api/auth/callback
```

### 11.4 前端仍然请求旧域名

如果前端构建时使用了完整域名，例如：

```bash
VITE_API_BASE_URL=https://old.example.com
```

则构建产物会写死旧地址。推荐重新使用同源路径构建：

```bash
VITE_API_BASE_URL=/ VITE_WS_URL=/ws npm run build
```

### 11.5 访问刷新后出现 404

确认 Nginx 的前端路由配置是：

```nginx
location / {
    try_files $uri $uri/ /index.html;
}
```

这是 Vue Router 前端路由在生产环境中的必要配置。

### 11.6 端口暴露到公网

生产环境建议只开放 Nginx 的 `80/443`。后端 `8430` 应只允许本机访问。

可以用防火墙限制，或确保后端只由 Nginx 通过 `127.0.0.1:8430` 访问。

