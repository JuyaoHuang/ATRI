---
status: accepted
owner: frontend
created: 2026-07-13
updated: 2026-07-13
source:
  - .omc/specs/deep-interview-chat-markdown-rendering-v2.md
related_code:
  - frontend/src/components/chat/MessageItem.vue
  - frontend/src/components/chat/MessageList.vue
  - frontend/src/components/live2d/StageChatHistory.vue
  - frontend/src/composables/useVirtualChatTimeline.ts
  - frontend/src/utils/markdownRenderer.ts
  - frontend/src/utils/markdownRenderCache.ts
---

# 安全 Markdown、KaTeX 与虚拟聊天时间线设计

## 问题

当前默认聊天布局和 Live2D Stage 都通过 Vue 文本插值显示消息正文。该方式
安全，但不能表达 Markdown 结构或数学公式。直接把第三方渲染结果交给
`v-html` 会引入 XSS、远程媒体加载和插件生成 HTML 的信任问题；同时，数千
条包含 Markdown、HTML 与 MathML 节点的历史消息会造成不可接受的挂载、布局
和重绘成本。

因此，本功能把内容解析、安全清洗、缓存和可见范围挂载视为一个完整工作流，
不能只替换单条消息的模板。

## 渲染范围

| 内容 | 渲染方式 |
|---|---|
| 键盘发送的 human 静态消息 | Markdown + KaTeX |
| ASR 生成的 human 静态消息 | Markdown + KaTeX |
| 完成、被打断后固化的 AI 消息 | Markdown + KaTeX |
| 历史 API 恢复的 human/AI 消息 | Markdown + KaTeX |
| `streamingText` AI 流式预览 | Vue 转义纯文本 |
| generation failure notice | Vue 转义纯文本 |
| 空状态和其他 UI 文案 | 普通文本 |

## 唯一运行时工作流

```text
raw message.content
  -> 动态虚拟时间线选择 visible + overscan 行
  -> MessageItem -> MarkdownContent
  -> rendererVersion + exact source 的有界 LRU 查询
       |-- hit  -> 已清洗 HTML
       `-- miss -> 输入资源限制
                  -> Markdown-It
                  -> 只读任务列表与 KaTeX 插件
                  -> DOMPurify 最终清洗
                  -> 缓存已清洗 HTML
  -> 消息正文唯一 v-html 边界

任何失败
  -> 丢弃所有中间 HTML
  -> Vue 转义显示完整原文
```

渲染 HTML 不得写回 Pinia、REST 历史、WebSocket payload、LocalStorage、
IndexedDB 或后端。TTS 继续消费原始 `message.content`。

## Markdown 基线

第一版使用 Markdown-It 14.x，并固定以下语义：

```ts
{
  html: false,
  breaks: false,
  linkify: true,
  typographer: false
}
```

支持段落、标题、强调、删除线、列表、引用、安全链接、代码、GFM 表格和只读
任务列表。任务列表 checkbox 必须 `disabled`，且不生成用于交互的 label ID。

图片 rule 必须关闭。不安装图片、音频、视频、iframe、embed、Mermaid、语法
高亮或远程媒体插件。代码节点内部不继续解释 Markdown 或数学分隔符。

## 数学边界

使用 `@mdit/plugin-katex` 和 KaTeX 0.17.x，识别：

- `$...$`
- `$$...$$`
- `\(...\)`
- `\[...\]`

配置必须保持 `trust:false`、`throwOnError:false` 和有界 `maxExpand`、
`maxSize`。支持承诺覆盖该版本在 `trust:false` 下支持的全部纯数学符号、
函数和环境；不覆盖完整 LaTeX 文档、系统编译、文件访问、宏包、外部资源、
链接或 HTML 扩展。

每次 cache miss 的数学渲染必须使用隔离的宏状态。一条消息中的宏定义不能
影响另一条消息。

## HTML 安全边界

DOMPurify 必须是最后一个字符串转换阶段。清洗之后不得再拼接 HTML、改写
属性或执行正则替换。

最终节点显式禁止：

- `script`、`style`
- `img`、`picture`
- `video`、`audio`、`source`
- `iframe`、`object`、`embed`

同时删除事件处理属性和危险 URL 协议，并保留 KaTeX 所需的 HTML、MathML、
ARIA 以及 disabled/checked 任务列表状态。若解析、KaTeX 或清洗任一步抛错，
只能返回完整原文的安全文本 fallback，不能暴露清洗前 HTML。

## 缓存设计

渲染缓存是模块级内存 LRU，不依赖 Pinia，也不持久化。

- key：`rendererVersion + exact raw source`
- value：仅完整 `SanitizedHtml`
- 初始最大条目数：1000
- 初始近似内存预算：32 MiB
- 近似字节包含 source、HTML 与条目开销
- 命中时更新最近使用顺序
- 插入后同时按条目数与字节数逐出最旧条目
- renderer/security 版本变化自然改变 key namespace
- 登出、账户切换和聊天数据清理时清空

空文本、超出资源限制的文本和失败结果不进入 HTML 缓存。

## 动态虚拟时间线

默认布局和 Stage 必须复用一个 `useVirtualChatTimeline`。虚拟行由所有
`ChatTimelineItem` 加上可选的流式纯文本尾行构成，只有 visible + overscan
范围挂载真实内容。

虚拟化必须支持：

- 未知高度的初始估算；
- `ResizeObserver`/`measureElement` 动态测量；
- 总高度与绝对偏移；
- `scrollToIndex`；
- 初始定位到最后一行；
- 仅在用户仍跟随尾部时自动跟随新增内容；
- 用户向上滚动后不强制跳到底部；
- 宽度、字体与公式布局变化后的重新测量；
- 为未来 prepend 历史保留可见锚点。

## 稳定行标识

虚拟行 key 必须在当前聊天内唯一，不能来自当前数组索引。历史 API 尚未提供
稳定 message ID，因此历史映射要根据消息中已有稳定字段和同内容 occurrence
生成客户端 key，并在现有对象存活期间保持不变。未来后端提供消息 ID 后应优先
使用后端 ID。

流式尾行使用按 chat ID 限定的保留 key，不进入时间线 Store，也不能与消息或
notice key 冲突。

## 数据与协议边界

第一版继续一次加载后端返回的全部原始历史。虚拟化只解决解析、DOM、布局和
重绘成本，不宣称降低 REST payload 或 Store 原文内存。后端分页属于独立 feature。

本实现不修改：

- REST 或 WebSocket schema；
- Live2D 表情提取顺序；
- TTS 原始文本；
- interruption、头像、名称、时间戳和 notice 语义；
- 聊天持久化格式。

## UI 边界

本 feature 只提供保证内容不溢出的功能性基线，包括宽代码块、表格和块级公式
可在消息内容区域内滚动或换行。最终字体、颜色、标题比例、间距和 human/AI
差异样式由后续 UI 设计决定。
