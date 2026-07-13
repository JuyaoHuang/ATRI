# ATRI 代码安全 Review 与风险评估报告

报告日期：2026-07-12  
报告状态：最终版  
总体风险：Critical  
合并建议：不建议合并或上线

## 1. 执行摘要

本次审查发现 3 项 Critical、7 项 High 和 6 项 Medium 风险。

其中，多项漏洞已经在当前代码上完成无外部副作用的运行复现。复现仅使用进程内存或系统临时目录，没有攻击外部目标。

当前最危险的组合攻击链如下：

1. 默认配置关闭认证，或攻击者利用 Host 请求头绕过认证。
2. 攻击者上传包含伪造嵌套 `metadata.json` 的 Live2D ZIP。
3. 攻击者使用编码反斜杠调用 Live2D 删除接口。
4. 后端信任伪造元数据中的路径，并对 models 目录外执行 `shutil.rmtree()`。

在 Windows 原生部署中，该链路可删除应用进程有权限访问的目录。临时目录复现已经确认目标目录会被实际删除。

此外，默认无认证、任意 CORS Origin、WebSocket 无 Origin 校验、上传解析 DoS、ZIP bomb、VAD 无界缓冲和断连任务泄漏可以组合造成：

- 未授权聊天数据访问或修改；
- 角色提示词和其他 Markdown 文件泄露；
- 应用目录、数据目录或模型目录被删除；
- 聊天记录丢失或出现半轮数据；
- 屏幕共享跨用户会话复用；
- 内存、CPU、磁盘和连接资源耗尽；
- LLM、ASR 和 TTS API 配额或费用消耗；
- Windows 服务账户 NTLMv2 challenge-response 泄露。

完整测试通过不能覆盖这些问题。现有测试主要验证正常功能，没有覆盖畸形 Host、Windows 路径语义、并发写、磁盘失败、恶意压缩包和断连时序。

## 2. 审查范围

### 2.1 根仓库

- 仓库：`atri`
- 分支：`feat/visual-understanding`
- 基线：`ee5919be18b35abb1a6e95d6482b6d971b663be5`
- 审查终点：`1a7c3dbf0902814c5230222be18c2b1e3a1b952f`
- 相对 `origin/main`：27 个提交
- 非 Markdown 变更：46 个文件
- 变更规模：3565 行新增，236 行删除

### 2.2 前端子模块

- 子模块：`atri-webui`
- 基线：`5fbc96755caaa06f6db053308e058cbb7f895c76`
- 审查终点：`d65d9ed6e9c4aee0820bd5c70f0784e89b8aaac7`
- 非 Markdown 变更：38 个文件
- 变更规模：3550 行新增，140 行删除

审查过程中，前端新增并推送了提交 `d65d9ed`。该提交修复了等待屏幕捕获期间切换聊天时的跨聊天显示问题，并已纳入最终审查范围。

### 2.3 排除范围

本次不审查仓库内 `.md` 文件的内容。

路径穿越复现使用系统临时目录中的临时 `.md` 文件作为安全哨兵。该操作用于验证代码漏洞，不代表审查了仓库 Markdown 内容。

本次未执行以下操作：

- 未连接攻击者 SMB 服务；
- 未对外部系统发送攻击请求；
- 未调用真实付费 LLM、ASR 或 TTS API；
- 未修改或修复仓库源码；
- 未清理用户已有工作区改动；
- 未执行会写入前端 `dist/` 的生产构建。

## 3. 审查方法

本次使用 `$choose-code-context-tools` 和 `$requesting-code-review` 工作流。

具体方法如下：

1. 使用 `rg`、直接源码读取、Git diff、测试和类型检查确认文件级事实。
2. 使用 GitNexus 梳理调用图、影响范围和跨模块执行流。
3. 所有重要结论都回到当前源码和运行行为验证。
4. 使用独立 reviewer 对根仓和前端范围进行交叉复核。
5. 对依赖公告进行调用路径校准，避免机械照抄上游严重度。
6. 对高风险问题使用内存或临时目录进行最小复现。

两个初始专项 reviewer 因服务端 `429 Too Many Requests` 失败。独立 reviewer、后端专项复核和依赖专项复核均已成功完成。

## 4. 严重度标准

### Critical

无需高权限即可绕过核心信任边界，或可造成灾难性数据破坏、广泛未授权访问。

### High

可造成敏感数据泄露、持久数据破坏、显著资源耗尽、隐私边界失效或高额费用消耗。

### Medium

需要特定前提，或主要造成局部资源消耗、内部服务滥用、部署故障和防御边界弱化。

### Low

当前调用路径不可达，或主要属于开发工具、传递依赖和代码质量维护风险。

## 5. Critical Findings

### ATRI-SEC-001：Starlette Host 请求头认证绕过（赞同）

严重度：Critical  
置信度：高  
状态：已运行复现

受影响位置：

- `uv.lock:2369-2370`
- `src/middleware/auth.py:15-35`
- `src/app.py:153`
- `src/routes/vision.py:32-48`
- `src/routes/chat_ws.py:361-367`

问题描述：

项目锁定 `starlette 1.0.0`，命中 `CVE-2026-48710`、`GHSA-86qp-5c8j-p5mr` 和 `PYSEC-2026-161`。

认证中间件使用 `request.url.path` 判断请求是否属于公开路径：

```python
if not auth_service.enabled or request.method == "OPTIONS" or _is_public_path(request.url.path):
    return await call_next(request)
```

Starlette 1.0.0 会使用未经验证的 Host 构造 URL。畸形 Host 可以改变 `request.url.path` 的解释，而实际路由仍然依据 ASGI `scope["path"]`。

攻击者可以让认证中间件看到 `/api/auth`，同时让路由进入 `/api/vision/config` 等受保护 handler。

运行证据：

```text
正常无凭证访问 /api/vision/config：401
加入畸形 Host 后访问同一接口：200
受保护 handler 已实际执行：true
```

可利用前提：

- 畸形 Host 能到达 Uvicorn 或 Starlette；
- 上游代理没有严格拒绝非法 Host；
- 目标路由只依赖全局认证中间件。

主要影响：

- 绕过启用后的认证；
- 访问或修改 Vision、ASR、TTS、Characters 和 Live2D 管理接口；
- 上传恶意资源；
- 调用付费 provider；
- 与 ATRI-SEC-002、ATRI-SEC-006 和 ATRI-SEC-007 串联。

`chats` 和 `data` 部分路由会再次调用 `get_request_user_id()`。这些路由不一定受到完全相同的影响。

修复建议：

1. 将 Starlette 升级到至少 `1.3.1`。
2. 增加 `TrustedHostMiddleware` 或等价 Host allowlist。
3. 让反向代理拒绝非法 Host。
4. 安全判断改用可信的 ASGI `scope["path"]`。
5. 对高价值管理路由增加路由级认证依赖。
6. 增加畸形 Host 回归测试。

验收标准：

- 正常无凭证请求返回 401；
- 所有畸形 Host 变体在路由执行前被拒绝；
- 管理路由在绕过全局中间件的测试中仍返回 401。

### ATRI-SEC-002：Windows Live2D 任意目录删除（赞同）

严重度：Critical  
置信度：高  
状态：已运行完整利用链复现

受影响位置：

- `src/routes/live2d.py:96-109`
- `src/routes/live2d.py:154-165`
- `src/storage/live2d_storage.py:150-169`
- `src/storage/live2d_storage.py:193-201`
- `src/storage/live2d_storage.py:336-345`
- `src/storage/live2d_storage.py:402-409`

问题描述：

Live2D 上传会解压归档中的所有普通文件，包括嵌套 `metadata.json`。

`get_model(model_id)` 没有验证 `model_id` 是单个安全路径分量：

```python
model_dir = self._model_dir(model_id)
metadata_path = model_dir / "metadata.json"
```

读取元数据后，代码继续信任攻击者可控的 `data["id"]`：

```python
return Live2DModelRecord(id=data["id"], ...)
```

删除时，代码使用记录中的 ID 重新构造路径并执行递归删除：

```python
record = self.get_model(model_id)
model_dir = self._model_dir(record.id)
shutil.rmtree(model_dir)
```

Windows 将反斜杠视为路径分隔符。URL 编码反斜杠仍可作为单个 FastAPI path 参数进入 handler。

攻击路径：

1. 上传合法 Live2D ZIP。
2. ZIP 内包含必需的模型 JSON。
3. ZIP 内额外包含嵌套 `metadata.json`。
4. 嵌套元数据的 `id` 指向 models 目录外。
5. 对“服务器生成 ID + 编码反斜杠 + 嵌套目录”调用 DELETE。
6. 后端读取伪造元数据，并对外部目录执行 `shutil.rmtree()`。

运行证据：

```text
DELETE 响应：204
目标目录删除前存在：true
目标目录删除后存在：false
原上传模型目录仍存在：true
```

复现目标位于系统临时目录，没有触碰仓库或外部目录。

可利用前提：

- Windows 原生部署；
- 攻击者能调用 Live2D 上传和删除接口；
- 进程对目标目录有删除权限。

当前默认关闭认证。即使开启认证，也可与 ATRI-SEC-001 串联。

主要影响：

- 删除聊天数据、模型、配置或项目目录；
- 造成不可恢复的数据损坏；
- 破坏应用启动和运行；
- 删除进程有权限访问的其他目录。

修复建议：

1. `model_id` 只允许匹配 `^live2d-[0-9a-f]{8}$`。
2. `model_id` 必须是单个路径分量。
3. 禁止 `/`、`\`、`.`、`..`、盘符和绝对路径。
4. 不要从磁盘元数据信任 `id` 决定文件系统路径。
5. 使用请求中已验证的服务端 ID 作为记录 ID。
6. 删除前对目标执行 `resolve()`。
7. 使用 `Path.is_relative_to(models_dir.resolve())` 验证 containment。
8. 进一步要求目标的直接父目录等于 `models_dir`。
9. 拒绝上传归档中的任何业务无关 `metadata.json`。
10. 删除操作前拒绝 symlink、junction 和 reparse point。

验收标准：

- 编码反斜杠和编码斜杠均返回 400；
- 嵌套伪造元数据无法改变记录 ID；
- 删除目标始终是 models 根目录的直接子目录；
- Windows 路径穿越测试不能删除临时 models 根目录之外的哨兵目录。

### ATRI-SEC-003：默认信任边界公开（忽略）

严重度：Critical  
置信度：高  
状态：源码确认，HTTP 和 WebSocket 已运行验证

受影响位置：

- `config/auth.yaml:6`
- `config/server_config.yaml:8`
- `config/server_config.yaml:12-14`
- `src/main.py:144-146`
- `src/app.py:140-150`
- `src/auth/dependencies.py:28-59`
- `src/routes/chat_ws.py:361-367`

问题描述：

当前默认配置同时具备以下条件：

- 认证关闭；
- 服务监听 `0.0.0.0`；
- CORS 允许任意 Origin；
- CORS 允许 credentials；
- WebSocket 不校验 Origin；
- 认证关闭时统一使用 `default` 用户。

独立复核证据：

```text
Origin: https://evil.example 的 WebSocket 被接受
连接发送 ping 后收到 pong
恶意 Origin 的 HTTP 请求获得跨域允许响应
带 Cookie 请求获得 Access-Control-Allow-Credentials: true
```

可利用前提：

- 直接运行默认 `src.main`，或通过代理暴露服务；
- 攻击者能访问服务端口；
- 浏览器攻击还取决于 Private Network Access、Mixed Content 和 SameSite 等策略。

浏览器策略只能缓解部分跨站场景。局域网客户端和直接 HTTP/WebSocket 客户端不受这些浏览器限制。

主要影响：

- 未授权创建、读取、修改或删除默认用户聊天；
- 修改全局 ASR、TTS、VAD 和 Vision 配置；
- 上传角色头像和 Live2D 模型；
- 调用 LLM、ASR 和 TTS；
- 消耗付费 API 配额；
- 放大本报告其他所有可达漏洞。

修复建议：

1. 认证关闭时默认绑定 `127.0.0.1`。
2. 认证关闭且绑定非 loopback 时拒绝启动。
3. 生产配置必须启用认证。
4. CORS 使用明确 Origin allowlist。
5. WebSocket 在 `accept()` 前校验 Origin。
6. 全局配置修改接口单独要求管理员授权。
7. 增加连接数、请求速率、并发和用户配额限制。

验收标准：

- 无认证非 loopback 配置无法启动；
- 非 allowlist Origin 的 HTTP 请求不能读取响应；
- 非 allowlist Origin 的 WebSocket 在 accept 前关闭；
- 配置写接口要求管理员身份。

## 6. High Findings

### ATRI-SEC-004：Windows StaticFiles UNC/SMB 凭据泄露（忽略）

严重度：High  
置信度：高  
状态：依赖、平台和调用路径匹配；未触发真实 SMB

受影响位置：

- `uv.lock:2369-2370`
- `src/app.py:123-135`
- `src/app.py:182-186`
- `src/middleware/auth.py:15-18`

问题描述：

Starlette 1.0.0 命中 `CVE-2026-48818` 和 `GHSA-wqp7-x3pw-xc5r`。

应用公开挂载三处 `StaticFiles`：

- `/api/assets/avatars`
- `/api/assets/live2d`
- `/static/avatars`

Windows 下，恶意 UNC 路径可能在 containment 检查前触发 `os.path.realpath()` 访问 SMB。

即使最终返回 404，系统也可能已经向攻击者控制的 SMB 服务发送 NTLM 身份验证数据。

可利用前提：

- Windows 原生部署；
- 攻击请求到达 StaticFiles；
- 服务器允许出站 TCP 445。

Debian Linux Docker 镜像不受该 Windows 专属问题影响。

主要影响：

- 泄露服务账户 NTLMv2 challenge-response；
- 支持离线破解；
- 在特定网络环境中支持 NTLM relay。

修复建议：

1. Starlette 升级到至少 `1.3.1`。
2. 防火墙阻止应用服务器出站 SMB。
3. 对静态资源路径增加规范化测试。
4. Windows 服务使用低权限、不可交互账户。

### ATRI-SEC-005：CharacterStorage Windows 路径穿越（忽略）

严重度：High  
置信度：高  
状态：已运行复现

受影响位置：

- `src/routes/characters.py:109-125`
- `src/routes/characters.py:153-210`
- `src/storage/character_storage.py:188-199`
- `src/storage/character_storage.py:290-315`
- `src/storage/character_storage.py:356-357`

问题描述：

创建角色时会规范化 ID，但读取、更新、删除和头像路径没有统一验证原始 `character_id`。

`_character_path()` 直接拼接：

```python
return self.persona_dir / f"{character_id}.md"
```

Windows 反斜杠可作为路径分隔符。

运行证据：

```text
请求 ID：..\secret
读取 persona 根目录之外文件：true
返回 system_prompt 包含临时哨兵内容：true
```

删除逻辑还会对相同穿越路径执行 `unlink()`。

可利用前提：

- Windows 原生部署；
- 攻击者能调用角色 API；
- 目标文件路径可猜测；
- 目标扩展名为 `.md`。

主要影响：

- 读取目录外的提示词或其他 Markdown 文件；
- 删除目录外 Markdown 文件；
- 头像路径可写入 avatar 目录之外的随机后缀文件；
- 与默认无认证或 Host 绕过串联。

修复建议：

1. 使用统一单路径分量验证器。
2. 拒绝 `/`、`\`、`.`、`..`、绝对路径和 Windows 保留名。
3. 对最终路径执行 `resolve()`。
4. 使用 `Path.is_relative_to(persona_dir.resolve())`。
5. 所有 get、update、delete 和 avatar 操作复用同一验证器。

### ATRI-SEC-006：Live2D ZIP bomb 与同源活动内容托管（忽略）

严重度：High  
置信度：高  
状态：已运行复现

受影响位置：

- `src/routes/live2d.py:96-109`
- `src/storage/live2d_storage.py:172-191`
- `src/storage/live2d_storage.py:322-345`
- `src/app.py:130-135`

问题描述：

Live2D 上传和解压没有以下限制：

- 上传总字节数；
- ZIP 文件数量；
- 单文件解压大小；
- 总解压大小；
- 压缩比；
- 允许扩展名；
- 活动内容类型。

代码先执行 `payload = await archive.read()`，然后解压所有条目。

运行证据：

```text
ZIP 大小：2439 字节
解压后大小：2097410 字节
膨胀比：859.9 倍
active.html 响应：200
Content-Type：text/html; charset=utf-8
```

解压目录通过应用同源 `StaticFiles` 公开。

可利用前提：

- 攻击者能调用模型上传；
- 同源脚本执行还需要受害者打开构造 URL；
- 默认认证关闭，或可利用 ATRI-SEC-001。

主要影响：

- 内存耗尽；
- 磁盘耗尽；
- 解压 CPU 消耗；
- 应用同源持久化 HTML 或 JavaScript；
- 使用受害者 Cookie 调用并读取 API。

修复建议：

1. 流式读取并限制上传字节数。
2. 检查 `ZipInfo.file_size` 和 `compress_size`。
3. 限制文件数、单文件大小、总解压量和压缩比。
4. 只允许 Live2D 必需扩展名。
5. 拒绝 HTML、JavaScript、SVG 和其他活动内容。
6. 静态资源使用独立、无凭证域名。
7. 设置 `X-Content-Type-Options: nosniff`。
8. 设置严格 CSP。
9. containment 使用 `Path.is_relative_to()`。

### ATRI-SEC-007：表单解析和上传链路资源耗尽（只进行升级）

严重度：High  
置信度：高  
状态：依赖公告和应用路径确认

受影响位置：

- `uv.lock:1985-1986`
- `pyproject.toml:14`
- `src/routes/asr.py:140-168`
- `src/storage/character_storage.py:307-320`
- `src/storage/live2d_storage.py:172-191`

问题描述：

项目锁定 `python-multipart 0.0.26`。

直接适用的主要公告包括：

- `CVE-2026-42561`：multipart part header 数量和大小无界；
- `CVE-2026-53539`：特制 urlencoded 输入可触发二次方 CPU 消耗；
- Starlette `CVE-2026-54283`：urlencoded 表单限制被忽略。

Starlette 1.0.0 中，即使调用 `request.form(max_fields=1, max_part_size=1)`，urlencoded 输入仍可超过限制完成解析。

FastAPI 的 File/Form 路由在返回业务校验错误前已经解析请求体。

应用层还存在以下全量读取：

- ASR：`await audio.read()`；
- Live2D：`await archive.read()`；
- 头像：先 `await file.read()`，再检查 2 MB 上限。

可利用前提：

- 攻击者能连接任一 File/Form 路由；
- 不要求请求最终成功进入业务 handler。

主要影响：

- 同步 CPU 消耗；
- 内存和临时磁盘消耗；
- 事件循环响应延迟；
- 服务拒绝响应。

修复建议：

1. Starlette 升级到至少 `1.3.1`。
2. python-multipart 升级到至少 `0.0.31`。
3. 增加 ASGI 层请求体总量限制。
4. 限制字段数、字段名长度、单字段大小和单文件大小。
5. 使用流式文件处理。
6. 不只依赖 `Content-Length`。
7. 代理和应用同时实施限制。

`CVE-2026-53540` 仅影响直接调用特定 `parse_form()` API 的场景。Starlette/FastAPI 当前路径不直接适用，不作为本项目独立漏洞上报。

### ATRI-SEC-008：聊天存储并发不安全且 durable commit 非原子（没理解）

严重度：High  
置信度：高  
状态：已运行多项复现

受影响位置：

- `src/storage/json_storage.py:122-135`
- `src/storage/json_storage.py:375-417`
- `src/routes/chat_ws.py:1571-1667`
- `src/routes/chat_ws.py:499-513`
- `src/routes/chat_ws.py:341-349`

问题一：并发写丢数据。

所有写操作共享：

```python
tmp = path.with_suffix(".tmp")
```

消息追加采用无锁的 session 读、改、写，再单独执行 index 读、改、写。

运行证据：

```text
请求追加：24
成功返回调用：5
最终保存消息：1
异常数量：19
异常类型：FileNotFoundError
```

多轮专项复现还出现过 `PermissionError`。

问题二：存储失败仍报告成功。

持久化异常只被记录，之后代码继续提交 memory，并继续发送 `output:chat:complete`。

独立复核证据：

```text
append_message_for_user 抛出 OSError("disk full")
聊天存储写入：0 条
memory round：1 次
前端事件：output:chat:chunk + output:chat:complete
```

问题三：断连可留下半轮。

human 和 AI 使用两次独立 append。连接在两次写之间失效时，代码可能只保存 human。

独立复核证据：

```text
最终角色序列：["human"]
AI 消息：未保存
memory round：0
终态事件：无
```

主要影响：

- 消息永久丢失；
- 只保存半轮；
- index 与 session 计数分裂；
- UI 显示成功，但刷新后内容消失；
- JSON 存储和 memory 状态分裂；
- 重试无法判断是否会重复。

修复建议：

1. 增加 per-chat 和 per-index `asyncio.Lock`。
2. 每次写使用唯一临时文件。
3. 提供原子 `append_round_for_user()`。
4. human、AI 和 index 在一个事务中提交。
5. 更适合并发场景时改用 SQLite 或数据库事务。
6. 存储失败时不得发送 complete。
7. durable storage 成功后才提交 memory。
8. 进入 commit 后，不因 transport 断开中止半轮写入。

### ATRI-SEC-009：WebSocket 任务与实时音频资源无界

严重度：High  
置信度：高  
状态：任务行为已复现，资源流已源码确认

受影响位置：

- `src/routes/chat_ws.py:282-294`
- `src/routes/chat_ws.py:341-349`
- `src/routes/chat_ws.py:499-513`
- `src/routes/chat_ws.py:1769-1849`
- `src/routes/chat_ws.py:2022-2031`
- `src/vad/service.py:88-153`
- `src/vad/providers/silero_vad.py:127-149`
- `config/vad_config.yaml:3-4`

问题一：断连任务没有取消。

代码已经提供 `cancel_current_chat_task()`，但 endpoint 的 `finally` 没有调用它。

`release()` 只丢弃任务引用并失效 generation。

运行证据：

```text
release 后任务引用为空：true
原任务已完成：false
原任务已取消：false
```

问题二：音频累计缓冲没有上限。

单个 frame 有大小限制，但连接可无限发送 frame。

`_coerce_audio_array()` 会复制整个 JSON 数组。speech 状态下，`audio_buffer.extend()` 没有最大样本数或最大语音时长。

问题三：VAD provider 和模型缺少全局约束。

VADService 为每个 session 创建 provider。当前启用 Silero VAD，每个 provider 都可能加载并持有模型。

系统没有以下边界：

- 用户级连接数；
- 全局连接数；
- 每秒消息数；
- 每秒累计字节数；
- 最大语音时长；
- 最大 VAD 模型实例数；
- 最大并发 LLM、ASR 和 TTS 调用数。

主要影响：

- 客户端断开后继续调用付费 API；
- 后台任务积累；
- 内存和 CPU 耗尽；
- 模型重复加载；
- API 配额和费用消耗。

修复建议：

1. 断连时取消并 await pre-commit 任务。
2. durable commit 使用有界 shield 和 shutdown 策略。
3. 不要先丢弃任务引用。
4. 限制单 chunk 样本数。
5. 限制累计语音时长和样本数。
6. 超限后清理状态并关闭连接。
7. 共享只读模型，或限制模型实例数。
8. 增加用户级和全局连接、速率、并发、字节及费用配额。

### ATRI-SEC-010：屏幕共享跨身份会话复用（忽略）

严重度：High  
置信度：高  
状态：源码生命周期确认

受影响位置：

- `frontend/src/utils/visionSessionController.ts:185`
- `frontend/src/composables/useVision.ts:106-127`
- `frontend/src/stores/user.ts:175-190`
- `frontend/src/pages/index.vue:30-38`

问题描述：

`visionSessionController` 是进程级单例。

页面离开聊天页时只断开 WebSocket，不停止 MediaStream。

logout 只清除认证状态，也不停止 MediaStream。

WebSocket 新连接建立后，只要旧流仍 active，前端会自动发送：

```text
input:vision:state enabled=true
```

风险场景：

1. 用户 A 开启屏幕共享。
2. 用户 A 进入设置页并退出。
3. MediaStream 仍保持存活。
4. 用户 B 在同一浏览器登录。
5. 新 WebSocket 自动声明视觉 active。
6. 后续捕获可能把 A 的共享画面发送到 B 的会话和第三方 provider。

> **不可能在同一浏览器登录**

主要影响：

- 屏幕内容跨账号泄露；
- 画面发送到错误后端用户；
- 画面发送到第三方 LLM provider；
- 用户不再获得新的浏览器授权提示。

修复建议：

1. logout 前调用 `visionSessionController.destroy()`。
2. 收到 401 或认证过期时销毁视觉会话。
3. 认证用户名变化时销毁视觉会话。
4. 页面间持久化可以保留，但身份边界必须强制清理。
5. 增加“共享、退出、另一用户登录、连接”的集成测试。

## 7. Medium Findings

### ATRI-SEC-011：后端 JPEG 校验只检查首尾标记（忽略）

严重度：Medium  
置信度：高  
状态：已运行复现

受影响位置：

- `src/vision/validation.py:69-142`
- `src/vision/config.py:117-126`
- `src/routes/chat_ws.py:656-690`
- `config/vision_config.yaml:11-16`

问题描述：

后端仅检查：

- Base64 严格解码；
- 解码后字节数；
- 开头 `FF D8 FF`；
- 结尾 `FF D9`。

后端没有解析 JPEG 结构、SOF、宽高和总像素。

配置中的 `max_long_edge` 只发送给前端，没有进入后端验证函数。

运行证据：

```text
输入字节：FF D8 FF 00 00 FF D9
总长度：7
校验结果：code="ok"
is_valid：true
```

主要影响：

- 伪 JPEG 被转发给 provider；
- 小文件可声明极端像素尺寸；
- 本地 provider 解码时可能消耗大量 CPU 和内存；
- 第三方 provider 产生失败但计费的请求。

修复建议：

1. 使用有边界的 JPEG parser。
2. 验证完整结构和有效 SOF。
3. 强制 `max_long_edge`。
4. 增加总像素上限。
5. 配置 decompression-bomb 防护。
6. CPU 密集解析移出事件循环。

### ATRI-SEC-012：generation_id 日志放大

严重度：Medium  
置信度：高  
状态：源码确认

受影响位置：

- `src/routes/chat_ws.py:611-666`
- `src/utils/logger.py:65-73`
- `src/vision/config.py:25-26`
- `config/vision_config.yaml:21-22`

问题描述：

capture-result 的 `generation_id` 只要求是非空字符串。

未知、inactive、failed 和 invalid 路径都会把完整 ID 写入日志。

默认 WebSocket frame 上限约为 8 MiB，配置最大允许 128 MiB。

DEBUG 文件日志配置为：

- 每 10 MB rotation；
- 保留 30 天；
- 没有磁盘总量上限。

主要影响：

- 高频日志轮转；
- 30 天内积累大量日志；
- JSON 解析和字符串格式化消耗；
- 磁盘耗尽导致服务失败。

修复建议：

1. generation ID 严格要求 32 位小写十六进制（赞同）
2. 日志只记录固定长度前缀或哈希。（赞同，保留后 id 16 位）
3. 增加消息速率和字节速率限制。
4. 增加日志目录总量和文件数上限。

### ATRI-SEC-013：TTS 任意 options 进入内部 provider

严重度：Medium  
置信度：中高  
状态：源码数据流确认

受影响位置：

- `src/models/tts.py:87-96`
- `src/routes/tts.py:167-191`
- `src/tts/service.py:223-284`
- `src/tts/providers/cosyvoice3_tts.py:153-180`
- `src/tts/providers/gpt_sovits_tts.py:105-149`

问题描述：

请求 schema 接受任意 `dict[str, Any]` options，并允许客户端选择任意已注册 provider。

Service 直接执行：

```python
audio = await tts.synthesize(text, voice_id=voice_id, **(options or {}))
```

CosyVoice 允许覆盖：

- `prompt_wav_upload_url`
- `prompt_wav_record_url`

这些值进入 `gradio_client.handle_file()`。HTTP URL 和本地存在路径都可能被接受。

GPT-SoVITS 允许覆盖：

- `ref_audio_path`
- `text_lang`
- `prompt_text`
- 其他内部 provider 参数。

客户端不能直接覆盖 provider backend URL，因此不能无条件定性为任意目标 SSRF。

主要影响：

- 驱动配置好的内部服务；
- blind URL fetch；
- 将已知本地文件上传到配置的 Gradio 服务；
- 内部 provider 参数滥用；
- 请求费用和资源消耗。

修复建议：

1. 每个 provider 建立运行时 options allowlist。
2. 禁止客户端覆盖文件路径和 URL。
3. provider 选择按部署策略限制。
4. URL 使用 scheme 和 host allowlist。
5. 阻止 loopback、link-local 和私有地址。
6. 为文本长度、并发和费用设置上限。

### ATRI-SEC-014：视觉开关未持久化到容器卷

严重度：Medium  
置信度：高  
状态：部署数据流确认

受影响位置：

- `config/vision_config.yaml:8`
- `src/vision/config.py:20-21`
- `src/vision/config.py:188-203`
- `Dockerfile:19-20`
- `docker-compose.prod.yml:10-13`

问题描述：

VisionConfigStore 把运行时开关写入镜像内 `config/vision_config.yaml`。

Compose 只持久化：

- `/app/data`
- `/app/models`
- `/app/prompts/persona`

`/app/config` 没有持久卷。

镜像内默认配置为 `enabled: true`。

主要影响：

- 用户关闭视觉后，容器重建会丢失选择；
- 升级或 recreate 后视觉模块恢复启用；
- 隐私设置在用户不知情时回退。

修复建议：

1. 运行时设置写入已挂载 data 目录或数据库。
2. 如果继续使用 YAML，挂载整个可写配置目录。
3. 不建议只 bind 单文件，因为当前写入流程可能执行原子替换。
4. 增加容器 recreation 验收测试。

### ATRI-SEC-015：Compose 前端缺少自包含 API 和 WebSocket 代理

严重度：Medium  
置信度：高  
状态：部署配置确认

受影响位置：

- `docker-compose.prod.yml:28-36`
- `docker/frontend-nginx.conf:1-10`
- `docker/host-nginx.same-domain.conf:22-36`
- `frontend/src/api/client.ts:5-8`
- `frontend/src/composables/useWebSocket.ts:54`

问题描述：

Compose 构建参数设置：

```text
VITE_API_BASE_URL=/
VITE_WS_URL=/ws
```

前端 Nginx 只有 SPA `try_files`，没有：

- `/api/` 的 `proxy_pass`；
- `/ws` 的 Upgrade 代理。

只运行 Compose 并访问 5200 端口时，REST 请求会落到前端 SPA，WebSocket 不会升级。

仓库另有 host Nginx 示例。额外部署该配置后，链路可以工作。

主要影响：

- Compose 文件本身不是自包含生产部署；
- 登录、聊天、视觉配置和 WebSocket 无法工作；
- 部署者容易误判服务已正常上线。

修复建议：

1. 在 frontend Nginx 内增加 `/api/` 和 `/ws` 代理；或
2. 把 host Nginx 明确设为强制部署前置条件；
3. 增加通过 5200 或正式入口执行的 REST 和 WebSocket smoke test。

### ATRI-SEC-016：依赖安全门禁未通过

严重度：Medium  
置信度：高  
状态：审计和 bundle 可达性校准完成

受影响位置：

- `uv.lock:21-23`
- `uv.lock:895-897`
- `uv.lock:1985-1987`
- `uv.lock:2369-2371`
- `uv.lock:2511-2513`
- `frontend/package-lock.json:2849-2857`
- `frontend/package-lock.json:3977-3997`
- `frontend/package-lock.json:5349-5364`
- `frontend/package-lock.json:6569-6585`

Python 审计去重后发现 5 个有效受影响包、23 个唯一 advisory。

前端 `npm audit --omit=dev` 报告 11 个受影响 package 节点：

- 2 Critical；
- 3 High；
- 6 Moderate。

这些数字不等于 11 个可直接利用的应用漏洞。

依赖版本在审查基线中已经存在，不是当前分支新引入的版本回退。

详细校准见第 8 节。

## 8. 依赖风险校准

### 8.1 Python 依赖

#### Starlette 1.0.0

建议版本：`>=1.3.1`  
应用严重度：Critical / High

直接适用：

- Host URL 解析导致认证绕过；
- Windows StaticFiles UNC/SMB 凭据泄露；
- urlencoded 表单限制被忽略。

只升级到 1.0.1 不足以覆盖当前全部有效公告。

#### python-multipart 0.0.26

建议版本：`>=0.0.31`  
应用严重度：High

直接适用：

- multipart header 数量和大小 DoS；
- 特制 urlencoded 输入二次复杂度 DoS。

条件性或当前不可达：

- 分号参数走私当前没有形成业务权限提升；
- 负 Content-Length 的特定低层 API 路径不被 Starlette/FastAPI 使用。

#### aiohttp 3.13.5

建议版本：`>=3.14.1`  
应用严重度：Low / 条件性

当前主要通过 Edge TTS 作为客户端访问固定 Microsoft 服务。

多数公告要求 aiohttp 服务端、CookieJar.load、自定义 SNI、DigestAuth 或用户可控 multipart header。当前调用路径没有命中这些前提。

#### idna 3.11

建议版本：`>=3.15`  
应用严重度：Low / 条件性

项目没有直接调用 idna。主要 provider host 来自固定配置。

超长恶意 Unicode host DoS 需要额外的用户可控 host 数据流。

#### urllib3 2.6.3

建议版本：`>=2.7.0`  
应用严重度：Low / 条件性

当前仅经 qdrant-client、requests 和 mem0 传递。项目源码没有直接使用相关危险低层 API。

### 8.2 前端依赖

依赖复核使用不写入 `dist/` 的内存构建分析。

浏览器产物包含：

- Axios；
- Pixi Live2D；
- browser 版本 node-vibrant；
- qs。

浏览器产物不包含：

- gh-pages；
- Node form-data；
- `@vibrant/image-node`；
- file-type。

#### Axios 1.15.1

建议版本：`>=1.16.0`  
应用严重度：Medium

Axios 是直接浏览器依赖。

实际 bundle 只包含 XHR 和 fetch adapter，没有 Node HTTP adapter。多数 Node proxy、Proxy-Authorization 和 NO_PROXY 公告不适用于当前浏览器运行时。

剩余浏览器 gadget 还需要先行原型污染源，或攻击者控制 Axios 配置。

#### Vite 8.0.9

建议版本：`>=8.0.16`  
应用严重度：Medium，仅开发环境

相关问题主要针对 Windows 开发服务器和 launch-editor tooling。

正式 Nginx 静态镜像不包含 Vite runtime。

#### pixi-live2d-display 0.4.0 / gh-pages 4.0.0

应用严重度：Low，供应链卫生

`pixi-live2d-display` 把 `gh-pages` 错误放入 production dependencies。

项目实际只导入 `pixi-live2d-display/cubism4`。gh-pages 不进入浏览器 bundle，也不被构建脚本执行。

不要直接运行可能把 Pixi 降级到 0.3.1 的 `npm audit fix --force`。

建议使用经过验证的 override、fork、上游修复或维护中的替代库。

#### node-vibrant / file-type

应用严重度：Low，不进入浏览器运行路径

项目显式导入 `node-vibrant/browser`。Node image backend 和 file-type 没有进入浏览器 bundle。

#### form-data 4.0.5

建议版本：`>=4.0.6`  
应用严重度：Low，不进入浏览器运行路径

当前前端使用浏览器原生 FormData。Node form-data 没有进入浏览器 bundle。

#### qs 6.15.1

建议版本：`>=6.15.2`  
应用严重度：Low

qs 进入浏览器 bundle，但当前只用于字符串 URL resolve。没有发现公告要求的特殊 stringify 调用形态。

## 9. 验证结果

### 9.1 后端

```text
uv run pytest tests/ -v
550 passed, 4 deselected
```

```text
uv run python -m mypy src/ --ignore-missing-imports
Success: no issues found in 108 source files
```

```text
uv run ruff check .
All checks passed
```

```text
uv run ruff format --check .
14 files would be reformatted
```

需要格式化的文件：

- `src/auth/exceptions.py`
- `src/auth/jwt.py`
- `src/auth/oauth.py`
- `src/auth/service.py`
- `src/auth/whitelist.py`
- `src/llm/factory.py`
- `src/middleware/__init__.py`
- `src/tts/providers/siliconflow_tts.py`
- `src/tts/service.py`
- `tests/auth/test_jwt.py`
- `tests/routes/test_auth.py`
- `tests/routes/test_data.py`
- `tests/routes/test_tts.py`
- `tests/vad/test_service.py`

```text
uv lock --check
通过
```

### 9.2 前端

当前最终提交 `d65d9ed` 的结果：

```text
npm test -- --reporter=verbose
13 test files passed
46 tests passed
```

```text
npm run type-check
通过
```

```text
npx eslint src --ext ".vue,.js,.jsx,.cjs,.mjs,.ts,.tsx,.cts,.mts"
0 errors
2 warnings
```

两个警告位于：

- `frontend/src/components/airi-ui/TransitionVertical.vue:74`
- `frontend/src/components/airi-ui/TransitionVertical.vue:75`

警告内容为 `@typescript-eslint/no-explicit-any`。

### 9.3 Git 完整性

排除 `.md` 后，根仓和前端范围均通过 `git diff --check`。

本次审查没有修改源码。

报告创建前，根仓只显示 frontend 子模块有本地状态。前端子模块只剩用户已有的 `.gitignore` 和 `AGENTS.md` 修改。

## 10. 已确认的正面控制

视觉理解实现包含以下有效安全控制：

- Base64 在解码前检查编码长度；
- 解码后再次检查真实字节数；
- 图片数据从 dataclass `repr` 隐藏；
- 无效图片日志不记录原始 payload；
- LLM provider 异常转换为安全的项目异常；
- 多模态只复制并修改当前 user message；
- 图片不写入聊天存储；
- 图片不写入短期或长期 memory；
- capture coordinator 使用服务端 generation ID 关联请求；
- timeout、cancel、stop 和 late result 均有清理逻辑；
- 前端 canvas 重编码会移除原始文件元数据；
- 前端执行图片字节预算和长边缩放；
- Vision 配置 API 只允许严格 boolean `enabled`；
- 协议区分 generation error 和普通 protocol error。

前端提交 `d65d9ed` 还增加了跨聊天显示保护：

- `chatStore.addMessage()` 只把消息加入当前聊天 timeline；
- 新增 pending capture 期间切换聊天的回归测试；
- 当前 46 个前端测试全部通过。

这些控制值得保留，但不能抵消认证、文件系统和资源边界问题。

## 11. 修复优先级

### P0：立即阻断合并和上线

1. Starlette 升级到至少 `1.3.1`。
2. 修复 Host 信任边界。
3. 修复 Live2D 任意目录删除。
4. 认证关闭时禁止非 loopback 监听。
5. CORS 和 WebSocket Origin 使用 allowlist。

### P1：修复文件系统和上传边界

1. 修复 CharacterStorage 路径穿越。
2. python-multipart 升级到至少 `0.0.31`。
3. 增加应用级请求体和表单限制。
4. Live2D ZIP 增加文件数、大小和压缩比限制。
5. 禁止同源托管活动内容。

### P1：修复数据一致性

1. JSONChatStorage 增加锁和唯一临时文件。
2. human、AI 和 index 使用原子 round 提交。
3. 存储失败时不发送 complete。
4. memory 只在 durable storage 成功后提交。
5. 增加磁盘失败和断连时序测试。

### P1：增加 WebSocket 和费用边界

1. 断连时取消并等待生成任务。
2. 限制音频 chunk 和累计语音时长。
3. 限制连接、消息、字节和并发。
4. 限制 LLM、ASR 和 TTS 用户配额。
5. 共享 VAD 模型或限制实例数量。

### P2：修复隐私和输入校验

1. logout、401 和身份变化时销毁屏幕共享。
2. 后端解析 JPEG 结构并限制像素。
3. generation ID 严格限制格式和长度。
4. TTS options 使用 provider allowlist。

### P2：修复部署和供应链

1. Vision 配置写入持久卷或数据库。
2. 补齐 frontend Nginx 代理或强制 host Nginx。
3. Axios 升级到至少 `1.16.0`。
4. Vite 升级到至少 `8.0.16`。
5. 更新 aiohttp、idna、urllib3、qs 和 form-data。
6. 对不可达传递依赖记录有期限的审计例外。

## 12. 建议新增测试

上线前至少新增以下安全和并发测试：

1. 畸形 Host 不能改变认证判断。
2. 未认证请求不能进入管理 handler。
3. 非 allowlist WebSocket Origin 在 accept 前被拒绝。
4. Windows 编码反斜杠不能穿越角色目录。
5. Live2D 嵌套伪造 metadata 不能影响删除目标。
6. Live2D 删除目标始终位于 models 根目录内。
7. ZIP 文件数、单文件、总大小和压缩比超限被拒绝。
8. HTML、JavaScript 和 SVG 不能作为同源活动内容托管。
9. 并发追加消息不会丢数据或抛临时文件异常。
10. 存储失败不会发送 `output:chat:complete`。
11. 断连发生在 human 和 AI 写入之间时仍保持 round 原子性。
12. WebSocket 断连后生成任务被取消或有界完成。
13. 超长持续语音触发限额并释放缓冲。
14. 伪 JPEG、畸形 JPEG 和极端像素图片被拒绝。
15. 超长 generation ID 在日志前被拒绝。
16. 屏幕共享后退出，所有 MediaStreamTrack 都被停止。
17. 用户 A 退出并由用户 B 登录后，不会重新声明旧视觉状态。
18. 容器重建后 Vision 隐私设置保持不变。
19. 正式入口同时通过 REST 请求和 WebSocket ping smoke test。

## 13. 合并与发布门槛

满足以下条件前，不建议合并或发布：

- 所有 Critical finding 已修复并加入回归测试；
- 所有 High finding 已修复，或有经过批准的书面风险接受；
- Starlette 和 python-multipart 已升级并锁定；
- Windows 路径测试在 Windows CI 上执行；
- JSON 并发和磁盘失败测试通过；
- WebSocket 断连和资源限额测试通过；
- 前端 logout 屏幕共享测试通过；
- 后端 pytest、mypy、Ruff check 和 Ruff format 全部通过；
- 前端测试、类型检查和 ESLint 全部通过；
- 生产入口 REST 和 WebSocket smoke test 通过；
- `pip-audit` 和 `npm audit` 的剩余告警都有可达性说明和到期日。

## 14. 最终结论

当前实现具有较好的视觉 payload 最小化、generation 关联和正常路径测试覆盖。

但是，认证边界、Windows 文件系统边界、上传资源边界和聊天持久化语义存在上线阻断问题。

尤其是 Host 认证绕过和 Windows Live2D 任意目录删除可以直接串联。默认无认证配置进一步降低了攻击门槛。

最终判断：当前版本不适合合并到生产分支，也不适合面向不可信网络上线。
