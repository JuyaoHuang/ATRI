---
status: accepted
owner: frontend
created: 2026-07-13
updated: 2026-07-13
branch: feat/chat-markdown-rendering
related_code:
  - frontend/src/components/chat/
  - frontend/src/components/live2d/StageChatHistory.vue
  - frontend/src/composables/useVirtualChatTimeline.ts
  - frontend/src/utils/markdownRenderer.ts
  - frontend/src/utils/markdownRenderCache.ts
---

# 聊天 Markdown 与 KaTeX 渲染

本目录记录静态聊天消息安全 Markdown、KaTeX 数学渲染和长历史虚拟化的
开发过程。它属于一次 feature 的设计与验收记录，不替代 Frontend 模块长期
设计。

## 当前状态

- 状态：`accepted`
- 根仓库分支：`feat/chat-markdown-rendering`
- 前端仓库分支：`feat/chat-markdown-rendering`
- 产品规格：`.omc/specs/deep-interview-chat-markdown-rendering-v2.md`
- 目标仓库：`frontend/`
- 自动化验收：24 个测试文件、102 个测试全部通过
- 浏览器验收：默认与 Stage 的 1000 消息动态虚拟时间线通过

## 本次目标

1. 对所有已经固化到聊天时间线的 human 和 AI 消息统一渲染安全 Markdown。
2. 使用 KaTeX 渲染四种约定分隔符内的纯数学内容。
3. 使用 DOMPurify 作为所有插件输出之后的最终 HTML 安全边界。
4. 使用有界内存 LRU 避免虚拟消息反复挂载时重复解析。
5. 使用动态高度虚拟时间线约束数百至数千条历史消息的 DOM 和布局成本。
6. 保持流式 AI 预览、错误 notice、TTS 输入和后端协议语义不变。

## 已确认边界

- 原始 `message.content` 始终是唯一事实来源。
- 只有 DOMPurify 完整清洗后的结果可以进入消息正文的 `v-html`。
- Markdown 图片 token、原始 HTML和所有媒体/嵌入节点均被禁用。
- 任务列表只读，不产生持久化交互。
- 数学支持边界是锁定 KaTeX 版本在 `trust:false` 下的纯数学能力，不是完整
  LaTeX 文档、宏包或外部资源执行环境。
- 本 feature 不决定最终 Markdown 字号、颜色、间距和气泡视觉设计。
- 本 feature 不修改后端聊天协议、历史存储格式或分页 API。

## 子文档

| 文档 | 职责 |
|---|---|
| [design.zh-CN.md](design.zh-CN.md) | 渲染、安全、缓存、虚拟化和数据边界 |
| [implementation-plan.zh-CN.md](implementation-plan.zh-CN.md) | 实现步骤、文件落点、检查与提交拆分 |
| [dev-log.zh-CN.md](dev-log.zh-CN.md) | 分阶段实现事实、提交和浏览器验收数据 |
| [acceptance.zh-CN.md](acceptance.zh-CN.md) | 规格逐条验收矩阵和完整命令结果 |

## 相关长期设计

- [Frontend 模块入口](../../modules/frontend/README.zh-CN.md)
- [聊天 Markdown 长期设计](../../modules/frontend/chat-markdown-rendering.zh-CN.md)
- [Frontend 状态管理](../../modules/frontend/state-management.zh-CN.md)
- [聊天、语音与视觉运行时](../../modules/frontend/chat-voice-runtime.zh-CN.md)
- [舞台与设置](../../modules/frontend/stage-and-settings.zh-CN.md)
