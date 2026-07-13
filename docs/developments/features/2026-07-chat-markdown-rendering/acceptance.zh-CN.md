---
status: accepted
owner: frontend
created: 2026-07-13
updated: 2026-07-13
source:
  - .omc/specs/deep-interview-chat-markdown-rendering-v2.md
---

# 聊天 Markdown 与 KaTeX 渲染验收

验收结论：`deep-interview-chat-markdown-rendering-v2.md` ��本 feature 范围的
要求已经实现并通过自动化与真实浏览器验证。后端分页和精细 UI 仍按规格保持
为非目标。

## 1. 渲染范围

| 要求 | 证据 | 结论 |
|---|---|---|
| typed human | chat Store scope test + MessageItem human test | 通过 |
| ASR human | `addAsrTranscriptMessage` scope test | 通过 |
| completed/interrupted AI | Store scope + interrupted component test | 通过 |
| historical human/AI | history normalization + shared MessageItem | 通过 |
| default/Stage 语义一致 | 同一 `VirtualChatTimeline`/`MessageItem` + 组件和浏览器测试 | 通过 |
| streaming 纯文本 | jsdom + Edge 原文/DOM 检查 | 通过 |
| notice 纯文本 | Store notice scope + `ChatErrorBubble` 原有语义 | 通过 |

## 2. Markdown 与 KaTeX

| 要求 | 证据 | 结论 |
|---|---|---|
| GitHub 风格基础结构 | 标题、强调、删除线、列表、引用、链接、代码、表格测试 | 通过 |
| 只读任务列表 | 2 个 checkbox 均 disabled、无 label/id | 通过 |
| raw HTML 不激活 | DOM 安全 fixture + Edge raw script 文本 | 通过 |
| 图片/media/embed 禁用 | image rule、FORBID_TAGS、DOM 和零资源请求检查 | 通过 |
| 代码不嵌套解析 | code 内 `$not_math_inside_code$` 保持代码 | 通过 |
| soft break 服从 `breaks:false` | generated DOM 无 `<br>`；computed style 为 `normal` | 通过 |
| 四种数学分隔符 | unit + Edge 共 4 个 KaTeX/MathML 节点 | 通过 |
| 主要纯数学类别 | 符号、分式、根式、积分、求和、极限、逻辑、文本测试 | 通过 |
| matrix/aligned/cases | environment fixtures | 通过 |
| unsupported/trust 命令安全降级 | includegraphics/href/htmlClass/htmlStyle/htmlData fixtures | 通过 |
| `maxSize` / `maxExpand` | 500em 限制到 50em；递归宏有限错误输出 | 通过 |
| 消息宏隔离 | 两次独立 renderer 实例测试 | 通过 |
| MathML 保留 | jsdom 与 Edge 节点检查 | 通过 |

## 3. 安全

| 要求 | 证据 | 结论 |
|---|---|---|
| raw source 不进入 `v-html` | source inspection；只有品牌化结果进入组件 | 通过 |
| 唯一消息正文 `v-html` | `rg "v-html" src` 仅命中 `MarkdownContent.vue` | 通过 |
| DOMPurify 是最终字符串阶段 | renderer source + 品牌类型 | 通过 |
| script/style/event/危险协议移除 | renderer security fixtures | 通过 |
| 活动媒体从最终 DOM 缺失 | jsdom + 默认/Stage Edge 检查 | 通过 |
| 异常显示完整转义原文 | DOM 不可用和 render exception tests | 通过 |

允许的安全链接包括 HTTP、HTTPS、mailto 和相对链接。图片 Markdown 在 image
rule 关闭后可显示为 `!` 加普通链接，但不会创建 `img` 或发起资源请求。

## 4. 缓存与隐私

| 要求 | 证据 | 结论 |
|---|---|---|
| hit 跳过 renderer | spy 调用次数测试 | 通过 |
| 只存 SanitizedHtml | branded value 类型与 API | 通过 |
| LRU hit 更新 | recency eviction test | 通过 |
| 条目数/字节双逐出 | 独立预算测试 | 通过 |
| renderer version 隔离 | version namespace test | 通过 |
| logout/account/cleanup 清理 | lifecycle tests + 共享 chat delete action | 通过 |
| 不持久化 | Markdown 路径无 local/session/IndexedDB 引用 | 通过 |

## 5. 虚拟化与滚动

| 要求 | 证据 | 结论 |
|---|---|---|
| 1000 mixed-height 只挂载可见范围 | jsdom `<30`；Edge 默认/Stage 均为 8 | 通过 |
| 动态高度测量 | measureElement + ResizeObserver test | 通过 |
| remount 使用缓存 | cache hit 统计上升 | 通过 |
| 初始到尾部 | 最后一条 key 可见 | 通过 |
| 尾部追加自动跟随 | tail test | 通过 |
| 向上阅读不被拉到底部 | unit + Edge scrollTop/key 保持 | 通过 |
| 宽度/字体/公式重测量保持锚点 | ResizeObserver unit + Edge viewport resize | 通过 |
| default/Stage 共用不变量 | 两布局复用同一组件/composable | 通过 |
| prepend 与 stable key | prepend/duplicate/history ID tests | 通过 |
| 流式行参与测量但绕过 renderer | row model、cache 与 Edge DOM 检查 | 通过 |

## 6. 回归边界

| 要求 | 证据 | 结论 |
|---|---|---|
| TTS 接收原文 | MessageItem click test 检查 exact source | 通过 |
| Live2D expression 顺序 | utility regression + `useWebSocket` 无功能 diff | 通过 |
| interruption/avatar/name/time | MessageItem SSR assertions | 通过 |
| 既有 Store/WebSocket 测试 | 完整 Vitest 102 tests | 通过 |
| 后端 schema 不变 | 前端子模块内实现；无后端代码或协议改动 | 通过 |

## 7. 完整命令结果

```text
npm run type-check  -> pass
npm run lint        -> pass, 0 errors, 2 pre-existing warnings
npm test            -> pass, 24 files / 102 tests
npm run build       -> pass, 1117 modules transformed
git diff --check    -> pass
```

依赖检查：

```text
npm ls --depth=3 markdown-it @mdit/plugin-katex @mdit/plugin-tasklist \
  katex dompurify @tanstack/vue-virtual mermaid markdown-it-video \
  markdown-it-html5-media markdown-it-iframe markdown-it-embed
```

只列出锁定的 Markdown、KaTeX、DOMPurify、TanStack Virtual 依赖；媒体/embed
插件未出现在依赖树。

## 8. 验收后续

不阻塞本功能验收的后续项：

1. 单独设计 Markdown 的最终视觉 token、气泡排版和移动端细节。
2. 如真实历史 payload 成为瓶颈，另开后端 cursor pagination feature。
3. 在依赖升级 feature 中处理仓库既有 audit 链问题，不在本分支使用
   `npm audit fix --force`。

## 9. 独立代码审查

项目要求的 `$omc-code-review` 在当前环境未提供，使用可用的
`$requesting-code-review` 进行独立只读审查。最终范围：

- frontend base：`557060b`
- frontend head：`6d60f7c`
- 本 feature 的长期设计、开发日志与验收文档

最终结论：Critical、Important、Minor 均无未解决问题；`Ready to merge: Yes`。
