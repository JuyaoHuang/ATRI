---
status: accepted
owner: frontend
created: 2026-07-13
updated: 2026-07-13
source_documents:
  - ../../features/2026-07-chat-markdown-rendering/README.zh-CN.md
  - ../../features/2026-07-chat-markdown-rendering/design.zh-CN.md
related_code:
  - frontend/src/components/chat/MarkdownContent.vue
  - frontend/src/components/chat/MessageItem.vue
  - frontend/src/components/chat/VirtualChatTimeline.vue
  - frontend/src/composables/useVirtualChatTimeline.ts
  - frontend/src/utils/markdownRenderer.ts
  - frontend/src/utils/markdownRenderCache.ts
---

# 聊天 Markdown、数学渲染与长历史时间线

本文记录聊天正文渲染的长期运行时约束。一次开发中的提交、测试数量和浏览器
验收数据保留在对应 feature 文档；本文件只描述后续修改仍必须维持的边界。

## 内容分类

| 内容类型 | 展示方式 |
|---|---|
| 已进入时间线的 human 消息 | Markdown + KaTeX |
| 已完成或被打断后固化的 AI 消息 | Markdown + KaTeX |
| REST 历史恢复的 human/AI 消息 | Markdown + KaTeX |
| AI `streamingText` 预览 | Vue 转义纯文本 |
| generation failure notice | Vue 转义纯文本和既有 alert 语义 |

键盘输入、ASR、完成、打断和历史恢复只是静态消息的不同来源，不得产生不同
的正文解释规则。原始 `message.content` 始终是业务事实，渲染 HTML 只是可丢弃
的展示派生物。

## 渲染工作流

```text
raw message.content
  -> 动态虚拟时间线选择 visible + overscan 行
  -> 以内存 rendererVersion + exact source 查询有界 LRU
       |-- hit  -> 已清洗 SanitizedHtml
       `-- miss -> 输入长度限制
                  -> 独立 Markdown-It 实例
                  -> 只读任务列表 + KaTeX
                  -> 输出长度限制
                  -> DOMPurify 最终清洗
                  -> 缓存 SanitizedHtml
  -> MarkdownContent 的唯一消息正文 v-html

任一阶段异常
  -> 丢弃全部中间 HTML
  -> Vue 文本插值显示完整原文
```

DOMPurify 之后不得再做字符串拼接、属性补写或正则改写。渲染结果不得进入
Pinia 业务状态、REST/WebSocket payload、LocalStorage、IndexedDB 或后端。

## Markdown 和数学边界

Markdown 基线由 Markdown-It 提供：

- 原始 HTML关闭；自动链接开启；软换行不强制变成 `<br>`；typographer 关闭。
- 支持标题、段落、强调、删除线、列表、引用、链接、代码、表格和任务列表。
- 图片 token 关闭；任务 checkbox 必须 disabled，且没有可交互 label/id。
- 不安装图片、视频、音频、iframe、embed、Mermaid 或语法高亮插件。
- 代码节点中的 Markdown 和数学分隔符保持代码文本。

数学边界是锁定 KaTeX 版本在 `trust:false` 下支持的纯数学功能，不是系统
LaTeX。支持四种分隔符：

- `$...$`
- `$$...$$`
- `\(...\)`
- `\[...\]`

KaTeX 必须保持有限的 `maxExpand` 和 `maxSize`。每次 cache miss 使用隔离的
宏对象，消息之间不能共享可变宏。MathML 必须在最终清洗后保留。

## 安全边界

最终消息 DOM 显式禁止：

- `script`、`style` 和事件处理属性；
- `img`、`picture`、`video`、`audio`、`source`；
- `iframe`、`object`、`embed`、`foreignObject`、`use`；
- `src`、`srcset`、`poster`、`xlink:href` 等资源属性；
- JavaScript、data、ftp 等未批准协议。

KaTeX 的 `\includegraphics`、`\href` 和 HTML 扩展不能成为外部资源或活动
HTML。任何库升级、插件变化或 sanitizer 配置变化都必须提升 renderer version
并重新运行安全 fixtures。

## 性能和滚动边界

缓存与虚拟化解决不同问题，二者都必须保留：

- LRU 避免虚拟行重新挂载时重复执行 Markdown-It、KaTeX 和 DOMPurify。
- 默认预算是 1000 条、约 32 MiB，同时受条目数和字节数约束。
- 缓存仅存完整 `SanitizedHtml`，登出、账户切换和成功的数据清理会清空。
- 成功删除聊天必须在共享 `chatsStore.deleteChat()` 入口清空缓存，使侧边栏和
  设置页具有相同隐私语义；删除失败不得误清缓存。
- 动态高度时间线只挂载 visible + overscan 行，使用 ResizeObserver 重新测量。
- 初始加载到尾部；用户在尾部时跟随新增；向上阅读时不得被拉回尾部。
- 视口上方行高变化要补偿滚动位置，保持同一逻辑行锚点。
- prepend 历史必须依赖稳定 key 保持可见锚点，不能使用当前数组 index。
- 流式预览只是一个受测量的纯文本尾行，不进入 renderer 或 LRU。

默认聊天布局和 Live2D Stage 必须复用同一个 `VirtualChatTimeline`，不能各自
演化出不同的正文语义或滚动算法。

## 原文消费者和协议边界

- 手动与自动 TTS 继续读取原始文本，不读取 DOM、HTML 或 Markdown AST。
- Live2D expression metadata 在正文进入消息 Store 前按既有顺序提取；剩余
  文本仍作为原始 Markdown source 保存。
- interruption、头像、角色名称和时间戳不属于 Markdown 文档，继续由
  `MessageItem` 单独展示。
- 后端聊天协议、历史 schema 和持久化格式不因前端渲染而改变。
- 当前仍一次性加载全部历史原文。后端 cursor pagination 是独立优化项。

## 修改检查

修改该链路时至少检查：

1. `src/utils/markdownRenderer.spec.ts` 的 Markdown、KaTeX 和安全 fixtures。
2. `MarkdownContent` 仍是唯一消息正文 `v-html`，且只接收品牌化清洗结果。
3. 缓存双预算、版本隔离和隐私生命周期测试。
4. 1000 条混合高度消息、尾部跟随、向上滚动、resize 和 prepend 锚点测试。
5. human/AI、默认/Stage、流式预览、notice、TTS 和 Live2D 表情回归测试。
6. `npm run type-check`、`npm run lint`、`npm test` 和 `npm run build`。
