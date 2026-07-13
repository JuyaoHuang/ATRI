---
status: active
owner: frontend
created: 2026-07-09
updated: 2026-07-13
source_documents:
  - ../../module-design/CN/前端设计文档.md
related_code:
  - frontend/src/App.vue
  - frontend/src/router/index.ts
  - frontend/src/pages/index.vue
  - frontend/src/pages/settings/
  - frontend/src/components/live2d/
  - frontend/src/stores/settings.ts
  - frontend/src/stores/live2d.ts
  - frontend/src/stores/user.ts
  - frontend/src/pages/settings/modules/vision.vue
  - frontend/src/components/chat/VisionInput.vue
---

# 舞台与设置

本文说明首页双态布局、Live2D 舞台、设置页结构，以及浏览器本地偏好的长期边界。

## 首页双态布局

`frontend/src/pages/index.vue` 根据 `live2dStore.enabled` 切换首页为两种模式：

| 模式 | 条件 | 主要组件 | 目标体验 |
| --- | --- | --- | --- |
| 默认聊天模式 | `live2dStore.enabled=false` | `Sidebar` + `ChatArea` | 角色选择、聊天历史和消息输入并排展示 |
| 舞台模式 | `live2dStore.enabled=true` | `StageHeader` + `Live2DCanvas` + `StageChatShell` | 以 Live2D 为主视觉，聊天区浮在舞台上层 |

两种模式共享同一套：

- 角色与聊天状态
- WebSocket 连接
- 消息历史
- 音频播放器
- `InputBox` 中的单次语音、VAD 与视觉运行时入口

切换模式只改变页面布局和交互入口，不改变聊天协议。

## 默认聊天模式

默认模式由 `Sidebar.vue` 和 `ChatArea.vue` 组成：

- `Sidebar`：显示项目标题、角色选择器和聊天历史。
- `ChatArea`：显示消息列表、输入框、语音与屏幕视觉入口。
- 右上角固定按钮负责主题切换和进入设置页。

该模式更接近“列表 + 主内容”的工作台布局，适合频繁切换角色和聊天标题。

## 舞台模式

舞台模式在同一首页内渲染：

- `StageHeader`：显示模型名称、主题切换和设置入口。
- `Live2DCanvas`：渲染当前模型，消费位置、缩放和表情请求，并在内部处理模型原生 Idle 与点击动作。
- `StageChatShell`：在舞台上方提供聊天历史、角色切换和输入框。

### 舞台模式的额外职责

1. 根据窗口宽度微调模型偏移，避免桌面端模型过于居中遮挡聊天区。
2. 在 `watch(isLive2dMode)` 时重新拉取模型列表，保证管理员刚放入服务器目录的模型能被首页感知。
3. 让聊天区以浮层方式承载，而不是重建第二套聊天协议。

### StageChatShell 的设计边界

`StageChatShell.vue` 不是新的聊天系统，而是“舞台版容器”：

- 顶部工具栏提供聊天历史与角色面板切换。
- 中间使用 `StageChatHistory` 复用同一套消息状态。
- 底部仍然是 `InputBox variant="stage"`。
- 因为复用同一 `InputBox`，视觉按钮在 Stage 中仍位于 VAD 右侧。
- 连接状态仅展示为 UI pill，不在这里管理 WebSocket 生命周期以外的业务逻辑。

## Live2D 舞台设置边界

`/settings/models` 对应 `ModelSettings.vue`，它把 Live2D 能力拆成两部分：

1. `ModelSettingsPanel`：设置入口。
2. `ModelSettingsPreviewStage`：预览舞台。

设置面当前负责：

- 从后端有效模型列表中选择模型；当没有可用模型时提示联系管理员安装。
- 开启或关闭 Live2D；普通前端用户不能上传、重命名或删除服务器模型。
- 首页舞台总开关。
- 缩放与位置。
- 渲染精度和最大帧率。
- 鼠标跟随、自动眨眼、阴影。
- 单选“默认表情”与既有 LLM 暴露策略。
- 预览帧取色。

模型目录、模型表达列表、默认模型标记和静态资源 URL 仍以后端只读 `live2dApi` 为准；前端只持久化“我选择并怎么展示它”。本地模型 ID 失效时优先回退到后端有效默认模型；不存在有效默认模型时不隐式选择列表第一项。

## 设置路由结构

当前设置页通过 `router/index.ts` 的嵌套路由组织。已落地的主要入口如下：

| 路由 | 页面职责 | 数据所有权 |
| --- | --- | --- |
| `/settings/account` | 认证状态、本地昵称和本地头像文件名 | 认证会话由后端拥有，本地资料由前端拥有 |
| `/settings/airi-card` | 角色卡 CRUD、详情查看、导入导出 | 后端 Persona 与头像托管 |
| `/settings/modules` | 模块入口聚合页，展示 ASR/TTS/Vision 是否已启用 | 前端只汇总状态 |
| `/settings/modules/speech` | TTS provider、自动播放、播放器显示与测试 | 后端配置拥有真相，前端只写白名单字段 |
| `/settings/modules/hearing` | ASR provider、设备选择、自动发送、监控与测试 | 模块配置后端拥有，设备选择前端拥有 |
| `/settings/modules/vision` | 视觉模块唯一持久化开关与当前标签页状态说明 | `enabled` 由后端拥有，MediaStream 由浏览器 controller 拥有 |
| `/settings/scene` | 背景图、透明度、模糊度 | 前端本地偏好 |
| `/settings/models` | Live2D 模型选择、开关与舞台参数 | 管理员维护模型目录，后端只读发现，展示参数前端拥有 |
| `/settings/data` | 聊天删除、短期记忆清理、长期记忆删除提交 | 删除动作通过后端 API 执行 |

路由里仍保留若干占位页，例如 `consciousness`、`providers`、`connection`、`system`。这些入口在没有对应稳定后端能力前，不应被当成已完成模块设计。

视觉设置页只有一个可编辑开关。它不会调用 `getDisplayMedia()`；用户必须回到主页，通过 `VisionInput` 的明确点击选择共享目标。设置页与主页切换不得停止已经活动的 stream。

## 认证与路由守卫

前端认证边界由 `router.beforeEach()` 与 `userStore` 共同维护：

1. 每次路由切换先执行 `userStore.initializeAuth()`。
2. `/login` 与 `/auth/callback` 是公开路由。
3. 若后端声明认证关闭：
   - 访问登录页会被重定向回首页。
   - 前端以本地模式继续工作。
4. 若认证开启且未登录：
   - 非公开路由统一跳转到 `/login?redirect=...`。

当前前端不保存 bearer token。浏览器本地仅保存：

- 登录时间戳，用于 UX 展示与会话过期判断。
- 登录完成后的目标跳转地址。

实际认证凭据由后端 Cookie 会话管理。

## 本地持久化边界

前端会把少量“浏览器偏好”写入本地存储，避免和后端业务配置混淆：

| 存储键 | 位置 | 内容 |
| --- | --- | --- |
| `atri-background-settings` | `localStorage` | 背景图 base64、透明度、模糊度 |
| `atri-live2d-settings` | `localStorage` | 舞台开关、模型 ID、位置、缩放、表情与渲染偏好 |
| `settings/hearing/enabled` | `localStorage` | ASR 模块前端总开关 |
| `settings/hearing/audio-input` | `localStorage` | 当前选择的麦克风设备 ID |
| `ui/chat/settings/send-mode` | `localStorage` | 发送快捷键模式 |
| `atri_user_settings` | `localStorage` | 本地昵称与头像文件名 |
| `atri_auth_signed_in_at` | `localStorage` | 登录完成时间 |
| `ui/chat-history/delete-confirm-skip-until` | `localStorage` | 聊天删除二次确认的跳过到期时间 |
| `atri_auth_redirect` | `sessionStorage` | 登录完成后的目标路由 |

以下内容不应在前端本地自行持久化为业务真相：

- Provider API key
- 聊天标题与聊天消息
- 短期记忆或长期记忆
- 认证 Cookie 或真实访问令牌
- 视觉截图、MediaStream、Base64、data URL 或“已授权”状态

## App 级全局元素

`App.vue` 维护两个全局 UI 能力：

1. 背景层：
   - 只在非 `/settings` 路由显示。
   - 直接读取 `settingsStore.background`。
2. 悬浮音频播放器：
   - 所有路由都可见。
   - 是否在首页显示，受 TTS 后端配置 `show_player_on_home` 控制。

因此，设置页本身不显示全局聊天背景，但仍共享同一套音频播放状态。

## 数据维护页的边界

`/settings/data` 不是通用文件管理器，而是三类明确动作的前端入口：

1. 删除单个聊天标题：
   - 与首页侧边栏删除语义一致。
   - 影响聊天索引与该标题的消息文件。
2. 清理短期记忆：
   - 以“角色 + 聊天标题”为粒度。
   - 由后端删除 `short_term_memory.json` 并重置运行中缓存。
3. 清理长期记忆：
   - 以“当前用户 + 角色”为粒度提交到 mem0。
   - 前端只展示提交结果，不承诺立即完成。

## 扩展约束

新增舞台或设置能力时，应遵守：

1. 本地偏好必须有明确的键名、作用域和回退策略。
2. 后端拥有真相的模块配置，不在前端做第二份长期缓存。
3. 新设置页必须先有稳定 API 或稳定本地偏好边界，再挂到 `settingsEntry`。
4. 舞台模式新增控件时，优先复用既有 `chatStore`、`charactersStore` 和 `live2dStore`，不要复制一套页面专用状态机。
5. 浏览器媒体流必须有跨路由所有者，设置页和展示组件不得在卸载时擅自停止。

## 相关文档

- [README.zh-CN.md](README.zh-CN.md)
- [chat-voice-runtime.zh-CN.md](chat-voice-runtime.zh-CN.md)
- [../../modules/auth/README.zh-CN.md](../../modules/auth/README.zh-CN.md)
- [../../modules/tts/README.zh-CN.md](../../modules/tts/README.zh-CN.md)
- [../../modules/vision/README.zh-CN.md](../../modules/vision/README.zh-CN.md)
