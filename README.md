<h1 align="center">ATRI</h1>

![](data/atri-logo.jpg)

<p align="center">
  <b> 高性能萝卜子！基于claude code记忆压缩方式的情感伴侣</b>
</p>
<p align="center">
  <a href="https://github.com/JuyaoHuang/atri/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-CC%20BY--NC%204.0-orange" alt="license"></a>
  <img src="https://img.shields.io/badge/python-%3E%3D3.11-blue?logo=python&logoColor=white" alt="python">
  <img src="https://img.shields.io/badge/Vue-3-4FC08D?logo=vuedotjs&logoColor=white" alt="vue3">
  <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="fastapi">
  <img src="https://img.shields.io/badge/Live2D-supported-FF6699?labelColor=222" alt="Live2D">
</p>



<p align="center">
  <a href="README.en.md">English</a> ·
  <a href="#-快速上手">快速上手</a> ·
  <a href="#-功能亮点">功能亮点</a> ·
  <a href="#-技术栈">技术栈</a> ·
  <a href="#-项目文档">文档</a> ·
  <a href="#license">License</a>
</p>

---

## 👀 效果预览

| 深色模式 | 浅色模式 |
|:---:|:---:|
| ![](data/readme/dark-home.jpg) | ![浅色主题首页](data/readme/light-home.jpg) |
| ![](data/readme/dark-custom.jpg) | ![](data/readme/light-custom.jpg) |

---

## ⭐ 项目简介

大多数 AI 聊天工具每次打开都像失忆了一样 —— 你昨天刚说过最喜欢珍珠奶茶，今天它又问你"你喜欢喝什么？"

**ATRI** 不一样。它的核心是一套仿人脑记忆的三层压缩系统：每轮对话自动清洗噪声，每 26 轮生成事件级摘要，每 4 个摘要再提炼出长期画像。配合 [mem0](https://github.com/mem0ai/mem0) 的跨会话向量检索，你聊过的偏好、情绪变化、未完成话题，它都能记住并在合适的时刻想起。

简单来说：**聊得越久，它越懂你。**

ATRI 同时也是一个功能完整的 AI 角色伴侣平台 —— Live2D 形象、语音对话、角色定制、多用户隔离，开箱即用。

> 项目名称取自游戏《ATRI -My Dear Moments-》的女主角亚托莉，也是我最喜欢的高性能萝卜子

---

## ✨ 功能亮点

### 🧠 记忆系统

- **三层压缩**：L1 规则清洗 → L3 事件级摘要 → L4 模式级画像，上下文永不丢失
- **长期记忆**：通过 mem0 保存跨会话的用户事实、偏好和情感趋势
- **可恢复**：`chat_history` 是 source of truth，`short_term_memory` 损坏时可自动重建
- **会话隔离**：每个角色、每个用户独立记忆空间

### 💬 对话体验

- **流式输出**：WebSocket 实时推送 LLM 分片，逐字显示，无等待感
- **聊天管理**：ChatGPT 风格的侧边栏 —— 历史列表、自动标题、新建 / 删除
- **角色切换**：多角色人设，每个角色拥有独立记忆和问候语
- **实时时间感知**：AI 知道"现在几点"，对话更自然

### 🎨 界面与交互

- **Live2D 舞台**：后端托管模型资源，前端 PixiJS 渲染，支持表情和待机动画
- **双布局**：支持普通聊天模式与 Live2D 舞台模式，两种布局共享同一套聊天、语音和播放器运行时
- **双主题**：深色 / 浅色一键切换
- **自定义背景**：上传喜欢的图片，调节透明度
- **AIRI 风格 UI**：参考 [AIRI](https://github.com/moeru-ai/airi) 的青绿色调设计语言

### 🎙️ 语音链路

- **ASR 语音输入**：支持 Sherpa-ONNX SenseVoice / Faster Whisper / Whisper.cpp / OpenAI Whisper / 浏览器原生 Web Speech API
- **TTS 流式语音输出**：支持 Edge TTS / GPT-SoVITS / SiliconFlow / CosyVoice3
- **VAD 实时打断**：通过 WebSocket 持续上传麦克风音频，支持用户开口打断 LLM 流式回复和当前 TTS 播放
- **自动语音接管**：用户说完后可由后端 ASR 自动转写，并直接进入新一轮聊天
- **浮动播放器**：自定义进度条、拖动 seek、队列显示
- **模块化开关**：ASR、TTS 和 VAD 均为可选插件，按需启用

### 🔐 部署与认证

- **本地友好**：关闭认证即可单机使用，零配置上手
- **公网就绪**：GitHub OAuth + HttpOnly Cookie 会话 + 白名单，开启后多用户数据隔离
- **配置分层**：`config.yaml` 引用各子配置，模块化管理
- **OAuth 状态校验**：防止 OAuth 登录流程被 CSRF、旧回调或跨账号串号混淆
- **会话保护**：使用后端签发的 JWT 会话并放入 HttpOnly Cookie，避免令牌暴露在 URL、日志或前端可读存储中

---

## 🚀 快速上手

请阅读 [快速上手指南](docs/quickstart.md) 开始安装和配置。

欢迎参与 ATRI 的开发，请先阅读 [开发文档导航](docs/developments/README.md)。

后端启动后也可以访问自动生成的 API 文档：

- Swagger UI: `http://localhost:8430/docs`
- OpenAPI JSON: `http://localhost:8430/openapi.json`

---

## 🛠️ 技术栈

| 层 | 技术 |
|---|---|
| **后端框架** | FastAPI + Uvicorn |
| **LLM** | OpenAI 兼容接口（DeepSeek、SiliconFlow 等） |
| **记忆** | 三层压缩 + mem0（SaaS / Qdrant 本地部署） |
| **存储** | 本地 JSON（可扩展数据库） |
| **认证** | GitHub OAuth + JWT 会话 + HttpOnly Cookie |
| **前端框架** | Vue 3 + TypeScript + Vite |
| **状态管理** | Pinia |
| **样式** | UnoCSS |
| **Live2D** | PixiJS + pixi-live2d-display |
| **语音** | ASR / TTS 多提供商工厂模式 |

---

## 📖 项目文档

| 文档 | 说明 |
|---|---|
| [快速上手指南](docs/quickstart.md) | 安装、启动、基础配置与常见问题 |
| [开发文档导航](docs/developments/README.md) | 开发侧总入口：架构、模块、feature、wiki、归档 |
| [项目架构文档](docs/developments/项目架构设计.md) | 项目级架构、核心数据流与当前实现事实 |
| [认证系统使用指南](docs/configs/CN/认证系统使用指南.md) | GitHub OAuth 配置与白名单管理 |
| [ASR 配置说明](docs/configs/CN/ASR配置说明.md) | 语音识别提供商配置 |
| [TTS 配置说明](docs/configs/CN/TTS配置说明.md) | 语音合成提供商配置 |
| [VAD 配置说明](docs/configs/CN/VAD配置说明.md) | 实时语音活动检测、Silero 参数和 ASR 衔接说明 |
| [实时语音模式使用说明](docs/configs/CN/实时语音模式使用说明.md) | VAD button 使用、WebSocket 联调和验收路径 |
| [角色创建指南](docs/configs/CN/角色创建指南.md) | 角色人设、头像与问候语 |
| [Wiki 开发复盘入口](docs/developments/wiki/development-blogs/README.zh-CN.md) | 已整理的开发 blog，适合后续迁移到 GitHub Wiki |

---

## 🏗️ 项目结构

```
atri/
├── src/                # 后端源码
│   ├── agent/          #   ChatAgent + Persona
│   ├── memory/         #   三层记忆压缩 + 会话管理
│   ├── llm/            #   LLM 调用层（工厂模式）
│   ├── asr/            #   ASR 提供商
│   ├── tts/            #   TTS 提供商
│   ├── vad/            #   VAD 实时语音活动检测
│   ├── auth/           #   认证系统
│   ├── storage/        #   存储抽象层
│   ├── routes/         #   FastAPI 路由
│   └── utils/          #   配置加载 + 日志
├── config/             # 分层配置文件
├── prompts/            # 角色人设 + 压缩 Prompt
├── data/               # 运行时数据 / 头像 / Live2D 模型
├── tests/              # 后端测试
└── frontend/           # 前端（子模块）
```

---

## ✍️开发路线

ATRI 当前已经具备完整的 Web 对话体验：持久化记忆、角色管理、ASR/TTS、Live2D 舞台、认证与部署基础。后续开发会围绕“更自然的交互、更丰富的感知、更完整的部署形态”持续推进。

**已完成**

- 三层记忆压缩与持久化存储：支持会话历史、短期记忆、长期记忆和角色隔离。
- Web 端基础体验：支持聊天、角色切换、设置页、Live2D 舞台和普通聊天模式。
- 语音链路：已接入 ASR 与 TTS 多提供商配置，并完成 WebSocket 分段流式 TTS 输出。
- VAD 实时语音打断：支持实时麦克风输入、打断 LLM 流式输出、停止当前 TTS 播放、ASR 自动接管。
- TTS 分段流式化：自动朗读已升级为“文本切段 -> 小音频段 -> WebSocket 下发 -> 前端按序播放”，并保留 REST fallback 与历史消息手动播放路径。
- 部署与认证基础：支持本地部署、云端部署、GitHub OAuth、JWT 和白名单访问控制。

**下一方向**

- 开发 PC 客户端，提供更稳定的桌面端使用体验。
- 添加视觉理解能力，让 ATRI 可以接收并理解图像、屏幕或摄像头输入。
- 接入 MCP 工具调用能力，为 ATRI 连接外部工具、文件和自动化能力。
- 增加实时获取外部知识的能力，让对话可以在保持角色体验的同时接入更新鲜的外部信息。
- 持续完善 Live2D 与普通聊天模式下的界面一致性和交互细节。

**长期方向**

- Android 移动端，补齐移动设备上的原生体验。
- 更完整的多模态链路与外部能力编排，在角色体验、记忆系统和工具调用之间建立更自然的协同。

---

## 🤝贡献

欢迎参与 ATRI 的开发！请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解：

- 开发环境搭建
- 分支与 PR 流程
- 代码规范
- **开发文档导读** — 根据你参与的模块（后端 / 前端 / TTS / ASR / Live2D）优先从 [docs/developments/README.md](docs/developments/README.md) 进入，再定位到对应 `modules/`、`features/` 或 `wiki/`

---

## 🙏 致谢

ATRI 的诞生离不开以下优秀项目的启发和参考：

- [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) — ASR / TTS 工厂模式参考
- [AIRI](https://github.com/moeru-ai/airi) — 前端 UI 设计、Live2D 集成参考
- [mem0](https://github.com/mem0ai/mem0) — 长期记忆基座

---

## 🪪License

[CC BY-NC 4.0](./LICENSE)
