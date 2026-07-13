---
status: accepted
owner: frontend
created: 2026-07-13
updated: 2026-07-13
branch: feat/chat-markdown-rendering
---

# 实现计划

本计划已于 2026-07-13 完成。精确提交、检查结果和浏览器指标见
[开发日志](dev-log.zh-CN.md)与[验收记录](acceptance.zh-CN.md)。

## Step 1：设计与依赖边界

1. 将访谈 v2 规格沉淀为正式 feature 文档。
2. 锁定 Markdown-It、KaTeX、DOMPurify、TanStack Virtual 与测试依赖。
3. 记录 Node 22 的运行边界，并保持 `package-lock.json` 为唯一锁文件。

验证：依赖树中不存在媒体/embed 插件，`npm install` 无 engine 冲突。

## Step 2：安全渲染器与缓存

1. 新增 `markdownRenderer.ts`，实现品牌类型、资源限制、插件配置、链接策略、
   DOMPurify 和纯文本 fallback。
2. 新增 `markdownRenderCache.ts`，实现双预算内存 LRU、renderer-version key、
   统计与清理 hook。
3. 添加 Markdown、KaTeX、MathML、XSS、媒体禁用、宏隔离和异常 fallback 测试。

验证：定向 Vitest、类型检查、lint。

## Step 3：消息组件接入

1. 新增 `MarkdownContent.vue`，建立唯一消息正文 `v-html` 边界。
2. `MessageItem.vue` 对 human/AI/default/Stage 统一复用该组件。
3. 保持流式预览、notice 和 TTS 原文链路不变。
4. 添加 MessageItem 角色、布局、interrupted 与 TTS 回归测试。

验证：组件测试、类型检查、lint、构建。

## Step 4：动态高度虚拟时间线

1. 新增 `useVirtualChatTimeline.ts`，封装 TanStack Virtual 动态测量和尾部跟随。
2. 定义消息、notice 与流式尾行的稳定 key。
3. 用虚拟行替换 `MessageList.vue` 和 `StageChatHistory.vue` 的全量循环。
4. 移除对未挂载 DOM 查询的滚动依赖。
5. 添加混合高度、尾部跟随、向上滚动、prepend 锚点和 1000 行测试 fixture。

验证：定向 Vitest、类型检查、lint、构建。

## Step 5：生命周期与功能性样式

1. 在登出、账户边界和数据清理动作中清空渲染缓存。
2. 加载 KaTeX CSS/font，并提供最小的 overflow、代码、表格和公式容器规则。
3. 核对默认与 Stage 的语义一致性和移动端不溢出。

验证：安全 fixture、缓存清理测试和浏览器手动检查。

## Step 6：整体验收

依次执行：

```bash
npm run type-check
npm run lint
npm test
npm run build
```

随后检查：

- `git diff --check`
- 运行时依赖与 `package-lock.json`
- 唯一 `v-html` 边界
- 禁止媒体节点和危险协议
- 1000 条消息的挂载数量
- 当前分支中不含 Live2D 并行任务改动

## 提交拆分

建议提交按功能点拆分：

1. `docs(chat-markdown/step 1): define rendering architecture`
2. `chore(chat-markdown/step 1): add rendering dependencies`
3. `feat(chat-markdown/step 2): add safe markdown renderer`
4. `test(chat-markdown/step 2): cover rendering security boundaries`
5. `feat(chat-markdown/step 3): render static chat markdown`
6. `feat(chat-markdown/step 4): virtualize chat timelines`
7. `test(chat-markdown/step 4): cover virtual timeline behavior`
8. `docs(chat-markdown/docs): record acceptance results`
