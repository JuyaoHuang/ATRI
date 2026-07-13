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

# 聊天 Markdown 与 KaTeX 渲染开发日志

本文记录 `feat/chat-markdown-rendering` 的实现事实、阶段结论和验收中发现的
问题。长期运行时约束已经沉淀到
[Frontend 聊天 Markdown 长期设计](../../modules/frontend/chat-markdown-rendering.zh-CN.md)。

## 2026-07-13 规格与仓库边界

本功能的产品规格固定为：

- `.omc/specs/deep-interview-chat-markdown-rendering-v2.md`

并行的 Live2D 模型管理规格不属于本分支。根仓库和前端子模块都使用
`feat/chat-markdown-rendering`；未修改 `atri-live2d/` 工作树。

最终范围包括：

- 所有静态 human/AI 消息统一 Markdown + KaTeX；
- streaming preview 和 generation failure notice 保持纯文本；
- 禁止 Markdown 图片和所有活动媒体/embed；
- DOMPurify 作为插件之后的最终安全边界；
- 有界内存 LRU 与动态高度虚拟时间线同时启用；
- TTS、Live2D expression、后端协议和持久化语义不变。

## Step 1：依赖与文档

锁定运行时依赖：

- `markdown-it@14.3.0`
- `@mdit/plugin-katex@1.0.1`
- `@mdit/plugin-tasklist@1.0.1`
- `katex@0.17.0`
- `dompurify@3.4.12`
- `@tanstack/vue-virtual@3.13.31`

测试与类型依赖：

- `@types/markdown-it@14.1.2`
- `jsdom@29.1.1`

`package.json` 记录 Node `>=22`，当前验收 Node 为 `22.14.0`。依赖树检查
没有 Mermaid、Markdown 媒体、iframe 或 embed 插件。

对应提交：

- 根仓库 `4e65e7f` `docs(chat-markdown/step 1): define rendering architecture`
- 前端 `05ebfb9` `chore(chat-markdown/step 1): add rendering dependencies`

## Step 2：安全渲染器

新增 `markdownRenderer.ts`：

1. 检查 200000 字符输入上限。
2. 为每条 cache miss 创建独立 Markdown-It/KaTeX 实例和宏对象。
3. 关闭 raw HTML 和 image rule。
4. 启用四种数学分隔符与只读任务列表。
5. 使用 `trust:false`、`maxExpand=1000`、`maxSize=50`。
6. 检查 2000000 字符渲染输出上限。
7. 由 DOMPurify 最终清洗并品牌化 `SanitizedHtml`。
8. 任一异常返回完整原文 plain fallback。

安全测试覆盖 raw HTML、活动媒体、危险协议、KaTeX trust 命令、宏隔离、
MathML、DOM 不可用以及输入/输出资源上限。

资源上限验收补充确认：

- `\rule{500em}{500em}` 的最终 CSS/MathML 尺寸被限制到 `50em`；
- 递归宏达到 `maxExpand` 后同步降级为 `.katex-error`，保留原文且不产生
  活动节点。

对应提交：

- `f110a1b` `feat(chat-markdown/step 2): add safe markdown renderer`
- `29a48ce` `test(chat-markdown/step 2): cover rendering security boundaries`
- `f136af7` `test(chat-markdown/step 6): cover rendering resource bounds`

## Step 3：静态消息接入

新增 `MarkdownContent.vue`，并把 `MessageItem.vue` 的正文文本插值替换为该
组件。human、AI、默认布局和 Stage 都复用相同正文组件。

保持不变的链路：

- `playMessageSpeech()` 仍把 `props.message.content` 原文传给 TTS；
- interruption badge、头像、名称和时间戳仍由 `MessageItem` 展示；
- streaming row 和 notice 不经过 `MarkdownContent`；
- Live2D expression 提取仍发生在 WebSocket/历史映射的原有位置。

对应提交：

- `2fa9a77` `feat(chat-markdown/step 3): render static chat markdown`
- `c0bb5ea` `test(chat-markdown/step 3): cover message rendering variants`
- `4e8144d` `test(chat-markdown/step 6): cover scope and raw-text regressions`

## Step 4：稳定 key 与动态虚拟时间线

历史 API 没有 message ID，因此新增稳定客户端 ID：

- 输入包含 chat scope 和稳定消息字段；
- 使用 FNV-1a 64-bit digest；
- 完全重复消息从最新边缘计 occurrence；
- prepend 更旧的重复消息不会重编号已存在的新消息。

新增共享 `VirtualChatTimeline.vue` 和 `useVirtualChatTimeline.ts`，默认布局和
Stage 都改为 visible + overscan 挂载。流式预览作为一个保留 key 的纯文本
尾行参与测量。

验收审计发现：TanStack 默认行高补偿会保留最后滚动方向，滚动停止后发生的
字体/宽度/公式高度变化仍可能把逻辑锚点移动一行。最终显式配置“视口上方行
发生尺寸变化时补偿滚动偏移”，并用 ResizeObserver mock 验证同一 key 保持
可见，相对偏移不超过 8px。

对应提交：

- `10e0923` `fix(chat-markdown/step 4): stabilize history message keys`
- `55b89b3` `test(chat-markdown/step 4): cover stable history keys`
- `2d378e3` `feat(chat-markdown/step 4): virtualize chat timelines`
- `08a7308` `test(chat-markdown/step 4): cover virtual timeline behavior`
- `c275edc` `fix(chat-markdown/step 6): preserve anchors during row remeasurement`

## Step 5：缓存与隐私生命周期

LRU 使用双预算：1000 条、约 32 MiB。key 包含 renderer version 和 exact
source，value 类型只能是 `SanitizedHtml`。命中会更新 recency，失败/plain
fallback 不缓存。

缓存容器与重型 renderer 依赖解耦，避免 user Store 导入清理函数时把
Markdown/KaTeX/DOMPurify 拉入全局入口。缓存会在以下边界清空：

- logout；
- 账户 identity 变化；
- 数据清理请求成功。

同账户刷新和失败的数据清理不会误清缓存。

代码审查补充发现侧边栏删除聊天原本直接走 `chatsStore.deleteChat()`，没有经过
设置页的 cleanup composable。最终把成功删除后的缓存清理收敛到共享 Store
action；侧边栏和设置页现在走同一入口，删除请求失败时仍保留缓存。

对应提交：

- `db292fc` `perf(chat-markdown/step 5): decouple cache from renderer`
- `49fea42` `feat(chat-markdown/step 5): clear cache at privacy boundaries`
- `df379f9` `test(chat-markdown/step 5): cover cache lifecycle`

## 代码审查收敛

独立 production-readiness review 发现并验证了以下补充项：

1. 旧纯文本 `.message-text { white-space: pre-wrap }` 会继承到 Markdown DOM，
   在 CSS 层把 `breaks:false` 的 soft break 显示成硬换行。最终 rendered 分支
   显式使用 `white-space: normal`，plain fallback 保持 `pre-wrap`。
2. 将成功聊天删除的 LRU 清理收敛到 `chatsStore.deleteChat()`，覆盖侧边栏与
   设置页，并保留失败不清理语义。
3. prepend 测试改为同时比较 stable key 与 viewport offset；新增 rendered
   HTML 2000000 字符上限 fixture。
4. 虚拟时间线测试不再依赖固定 40ms 猜测初始 RAF；需要人工上滚的用例先
   等待尾部状态连续稳定 3 帧。4 个高风险测试文件共 33 个测试连续运行 5 轮
   全部通过。

对应提交：

- `77cdafd` `fix(chat-markdown/step 6): preserve Markdown soft breaks`
- `d5354cb` `fix(chat-markdown/step 6): clear cache after chat deletion`
- `6d60f7c` `test(chat-markdown/step 6): strengthen acceptance invariants`

项目说明中点名的 `$omc-code-review` 在当前技能目录不可用，因此使用现有
`$requesting-code-review` 流程启动独立只读 reviewer。最终复核范围为前端
`557060b..6d60f7c` 和本 feature 文档；Critical、Important、Minor 均为 None，
结论为 `Ready to merge: Yes`。

最终独立复审结论为 `Ready to merge: Yes`；Critical、Important 和 Minor
均无剩余问题。

## Step 6：完整检查

在 `frontend/` 执行：

```text
npm run type-check
npm run lint
npm test
npm run build
git diff --check
```

结果：

- type-check：通过；
- lint：0 error，保留既有 `TransitionVertical.vue` 两条 `no-explicit-any`
  warning；
- Vitest：24 个文件、102 个测试全部通过；
- production build：通过，1117 个模块完成转换；
- `git diff --check`：通过；
- 全局入口 JavaScript 约 103.91 kB，页面/聊天重型 chunk 约 464.00 kB；
- KaTeX 字体作为构建资产输出。

## 真实浏览器验收

使用 Microsoft Edge + Playwright CLI，启动 Vite 前端并 mock 与本功能无关的
REST 响应。后端和业务 WebSocket 未启动，因此控制台存在预期的 WebSocket、
ASR 和 Vision 连接拒绝；没有 Markdown、KaTeX、DOMPurify 或虚拟时间线异常。

默认布局 1440×1000：

| 指标 | 结果 |
|---|---:|
| Store 静态消息 | 1000 |
| 已挂载 virtual rows / MessageItem | 8 / 8 |
| KaTeX / MathML 节点 | 4 / 4 |
| task checkbox | 2，全部 disabled |
| 正文活动媒体 / script | 0 / 0 |
| `example.invalid` 资源请求 | 0 |
| raw script source | 作为可见文本保留 |
| KaTeX 字体状态 | loaded |
| 页面横向溢出 | false |

向上滚动后追加消息：

- `scrollTop` 保持 `56922`；
- visible key 保持 `browser-message-511`；
- 距离尾部仍超过 56000px，没有被拉到底部。

把 viewport 从 1440×1000 缩至 900×800 后：

- visible key 仍是 `browser-message-511`；
- 行相对 viewport offset 仍为 `-63px`；
- 挂载行数为 18；
- 页面无横向溢出。

Stage 1440×1000：

| 指标 | 结果 |
|---|---:|
| Stage 共享时间线已挂载 | true |
| 已挂载 virtual rows | 8 |
| KaTeX / MathML 节点 | 4 / 4 |
| task checkbox | 2，全部 disabled |
| 正文活动媒体 / script | 0 / 0 |
| KaTeX 字体 | loaded |
| 页面横向溢出 | false |

流式尾行另行验证：完整原文等于输入；DOM 中 `<img>` 被转义为文本；KaTeX、
活动媒体和 `MarkdownContent` 节点均为 0。

soft-break 修复在当前 Markdown 工作树的 Vite 端口另行复验：

- `.markdown-content__rendered` computed `white-space` 为 `normal`；
- `.markdown-content__fallback` computed `white-space` 为 `pre-wrap`；
- 段落 HTML 保留 source newline，但没有 `<br>`，浏览器显示为普通空格折叠。

## 已知边界

- 本功能没有实现后端历史分页，1000 条历史仍一次加载为原始字符串。
- 最终 Markdown 字号、颜色、标题比例和间距属于后续 UI 设计。
- 真实浏览器验收使用 mock REST 和未连接 WebSocket，不替代完整后端 E2E；
  本功能本身没有修改任何后端协议。
- npm 依赖审计中的既有 Axios、Vite、Live2D/Pixi 和 node-vibrant 链问题不在
  本 feature 中强制升级；新增 Markdown/KaTeX/DOMPurify/Virtual 依赖不是
  当前报告中的漏洞来源。
