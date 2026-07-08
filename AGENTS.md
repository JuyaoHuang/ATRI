> 本文档定义 agents 在本项目中编写代码时必须遵循的流程和规范。每次编写/修改代码后，按此清单执行。

---

## 项目上下文

- **项目名**: emotion-robot (atri)
- **技术栈**: Python 3.11+ / FastAPI / uv / loguru
- **Python 环境**: 当前工作目录存在 uv 创建的 `.venv`，执行 Python、测试、格式化、类型检查时优先使用 `uv run ...`
- **正式设计文档位置**: `docs/`
  - `developments/项目架构设计.md` — 目录结构、技术选型、日志方案
  - `developments/module-design/CN/记忆系统设计讨论.md` — 记忆系统的完整设计蓝本
  - `developments/module-design/CN/LLM调用层设计讨论.md` — LLM 调用层的接口、工厂、配置设计
  - `developments/module-design/CN/ASR模块设计文档.md` — ASR 模块接口、工厂、配置设计
  - `developments/module-design/CN/TTS模块设计文档.md` — TTS 模块接口、工厂、配置设计
  - `developments/module-design/CN/VAD语音唤醒模块设计.md` — VAD 模块参考设计
- **VAD 文档位置**: `docs/developments/wiki/VAD/`
  - `vad-design.md` — VAD、ASR、TTS 链路设计
  - `vad-implement.md` — VAD 开发边界与架构说明
  - `vad-implementation-plan.md` — VAD 分阶段实施计划
- **TTS 文档位置**: `docs/developments/wiki/TTS/`
  - `tts-stream-design.md` — TTS 流式链路设计
  - `tts-stream-implement.md` — TTS 开发边界与架构说明
- **实现前必读**: 修改某个模块前，先阅读对应的设计文档章节

---

## 项目结构

项目的设计思想是：模块化、高解耦、工厂流水线、工作流、热插拔。

- 模块化：系统可拆分为多个模块（子系统） module/ subsystem，如 LLM calling module，ASR module；每一个 module 可存在多个独立的子 module。以 多 module 形式解耦系统。
- 工厂流水线：对每一个 module，抽象出通用类和方法（factory），以注册的形式新增工人 provider。
- 工作流（workflow）：以数据为核心驱动。以用户的输入信息为开始，系统构建一条明确、清晰的数据流，最终输出清晰的相应数据。系统对输入数据进行的加工要足够简洁、清晰、可视化，开发者可以从用户的输入数据开始，追踪整条数据流，清晰看到系统的每个 module 处于 workflow 的什么位置和环节（node）。
- 热插拔：系统的核心module：LLM calling 返回的 response text 可供多个消费者 module （TTS、frontend、translation）使用，多条输出链路互不影响，可独立运行和使用

总的来说，项目规定命名（层级划分）为：

```
# System
## modules
LLM-calling ASR TTS Translation Live-2d Route 
### submodules
#### LLM-calling
##### LLM-calling-providers
##### LLM-calling-factory
#### ASR
##### ASR-providers
##### ASR-factory
#### TTS
```

*上述只列出部分 module*

## 提交规范

- 在开始子系统的实现前（如 LLM 调用模块），执行`git checkout -b feat/...` 切换分支，在新分支上开发，分支命名应准确、简洁、清晰。例如开发 LLM calling 模块，分支命名为：`feat/llm_calling`；开发 TTS 流式时：`feat/tts-streaming`

- 每个功能点一个 commit，不要把多个不相关的改动混在一起

- commit message 标准格式：`<type>(<scope>): <subject>`

- `type` 必填，允许值：
  - `feat`：新功能
  - `fix`：Bug 修复
  - `docs`：文档变动
  - `refactor`：重构（不改功能不改 bug）
  - `perf`：性能优化
  - `test`：测试相关
  - `style`：代码格式（不改逻辑）
  - `chore`：杂项（依赖、配置、CI 等）
  - `revert`：回滚
  
- `scope` 必填，命名标准为：`branch-name/step`，例：1. 处在开发 LLM 调用模块的分支时，进行到第 4 步时，`llm-calling/step 4`；2. 在 ASR module 开发分支（`feat/asr`）时的第五步：`asr/step 5`，后续跟随具体的改动内容，简洁清晰。

  而不属于步骤内容（分支开发的收尾工作）时使用操作名，例如 `ci`、`docs`、`frontend`。

- `subject` 使用英文祈使句，首字母小写，句末不加句号，单行不超过 72 个字符。

- 示例：
  - `feat(vad/step 2): add audio chunk message dispatch`
  - `fix(vad/step 2): prevent duplicate interrupt on continuous speech`
  - `test(vad/step 2): add audio message protocol tests`
  - `docs(vad/step 3): update realtime voice input plan`
  - `chore(vad/ci): update GitHub Actions runner version`
  
- 如改动涉及多个文件的协调变更、技术决策或权衡，commit body 可选但建议填写；body 与 subject 之间空一行，每行不超过 72 个字符。

- 不在 commit message 里写 TODO；未完成的工作拆到后续 commit。

- 提交前至少通过当前改动范围对应的 basic check。

- **注意**：commit 内容应该简洁，重点描述做了什么，不附带任何 AI 协助信息，例如"aaaa@claude.com<cooperate by claude>"。

- 提交 commit 时如果触发 GPG 签名验证，前往`.env`文件获取密码`GPG_VERIFY_KEY`

- **一个branch对应一次大的功能开发，一个 commit 对应功能开发里的一个 step 里的一个小点 point**

- 验收结束后，执行`git push` 推送到上游仓库，并且执行`gh pr`进 PR 的提交 

## 代码编写后的检查清单

每次编写或修改代码后，按顺序执行以下步骤：

### 1. 类型检查
```bash
# 确保没有类型错误
uv run python -m mypy src/ --ignore-missing-imports
```

### 2. 代码格式化
```bash
uv run ruff format .
uv run ruff check . --fix
```

### 3. 导入检查

- 确认新增的 import 都在 `pyproject.toml` 的依赖中
- 如果引入了新依赖：`uv add <package>`

### 4. 日志规范
- 使用 `from loguru import logger`，不使用标准 `logging`
- INFO 级别：用户可见的关键事件（启动、触发压缩、会话创建）
- DEBUG 级别：开发调试信息（token 数、chunk 内容）
- WARNING 级别：可恢复的异常（mem0 写入失败、重试）
- ERROR 级别：不可恢复的错误

### 5. 设计一致性
- 检查实现是否与设计文档一致
- 如果实现中发现设计需要调整，先更新设计文档，再改代码
- 不要偏离设计文档中已确定的决策（如注册表工厂、双接口等）

### 6. 测试验证
```bash
# 运行已有测试
uv run pytest tests/ -v
```
- 新增模块时，至少写一个基础测试验证核心逻辑
- 进行两部分测试：
  1. LLM 调用相关的测试用 mock，不实际调用 API，注意边界测试
  2. 调用 API 测试和验证，从 `.env` 中读取环境变量

### 7. 提交改动

执行`git commit ` 进行当前 step 的一个 point 的提交


---

## 编码规范

### 命名
- 文件名：`snake_case.py`
- 类名：`PascalCase`
- 函数/变量：`snake_case`
- 常量：`UPPER_SNAKE_CASE`

### 模块结构
每个模块遵循三层结构（参考项目架构设计 §2.4）：
```
module/
├── interface.py      # 抽象基类（ABC）
├── factory.py        # 注册表工厂
├── exceptions.py     # 模块专用异常（如需要）
└── providers/        # 具体实现
    └── xxx.py        # @Factory.register("xxx")
```

### 配置
- 所有可配置项放在 `config/` 下的 YAML 文件中
- 代码中不硬编码配置值
- 使用环境变量存储敏感信息（API key 等），YAML 中用 `${ENV_VAR}` 引用

### 异步
- IO 操作（LLM 调用、文件读写、mem0 调用）一律用 async
- 接口方法统一用 `async def`

---

## 代码审查

在提交 PR 前，启动内置 skill `$omc-code-review`，进行综合代码审查，按严重度分级反馈。

## 实现顺序

1. 在开始实现前，执行 `git checkout -b feat/...` 切换分支，在新分支上开发。分支命名必须对应本次大的功能开发，例如 `feat/tts-streaming`。
2. 修改某个模块前，先阅读对应设计文档和实施文档；如果实现中发现设计需要调整，先更新设计文档，再改代码。
3. 将一个大的功能开发拆成多个 step；每个 step 可以再拆成多个 point。
4. 每完成一个 point 一个 commit，不要把多个不相关的改动混在一起。
5. commit scope 使用 `branch-name/step N`，例如 `feat(tts-streaming/step 1): add streaming config`。
6. 每个 point 完成后，按“代码编写后的检查清单”执行当前改动范围内的 basic check，然后提交。
7. 验收结束后再执行 `git push`，并使用 `gh pr` 提交 PR。

当前主线任务为 TTS 分段流式化。按 `docs/developments/wiki/TTS/tts-stream-design.md` 和 `docs/developments/wiki/TTS/tts-stream-implement.md` 的 steps 计划推进：

```text
Step 0: 文档与范围冻结
  ├── 明确 TTS 是 LLM 文本回复的下游消费者
  ├── 明确第一版不引入 heard_response
  ├── 明确第一版不做 provider 原生 synthesize_stream()
  └── 明确应用层分段合成 + WebSocket 音频段下发路线

Step 1: 配置与依赖
  ├── 新增 pysbd 依赖
  ├── 在 config/tts_config.yaml 增加 streaming 顶层配置
  ├── 在 src/tts/config.py 增加默认 streaming 配置
  └── 保证 streaming disabled 时现有 REST TTS 行为不变

Step 2: 文本分段器
  ├── 新增 src/tts/sentence_divider.py
  ├── 使用 pysbd 进行句子边界检测
  ├── 支持可选 faster_first_response
  └── 增加 tests/tts/test_sentence_divider.py

Step 3: TTS 分段管理器
  ├── 新增 src/tts/segment_manager.py
  ├── 调用现有 TTSService.synthesize() 合成完整小音频
  ├── 管理 segment_id、sequence、generation_id
  ├── 控制并发和 ordered delivery
  └── 增加 tests/tts/test_segment_manager.py

Step 4: 后端 WebSocket 音频事件
  ├── 在 src/routes/chat_ws.py 接入 TTSSegmentManager
  ├── 发送 output:audio:segment
  ├── 发送 output:audio:complete
  ├── 发送 output:audio:error
  └── VAD interrupt 时取消旧 generation 的 TTS manager

Step 5: 前端音频段播放
  ├── 在 frontend/src/utils/websocket.ts 分发 audio 事件
  ├── 在 useWebSocket.ts 接收 audio segment
  ├── 扩展 useAudioPlayer.ts 支持 generation + sequence 队列
  ├── streaming enabled 时停止 complete 后 REST auto TTS
  └── 保持手动历史消息播放继续走 REST TTS

Step 6: 测试、文档与验收
  ├── 补充 tests/tts/test-exe.md
  ├── 扩展 WebSocket 集成测试
  ├── 运行后端 mypy、ruff、pytest
  ├── 运行前端构建或类型检查
  └── 完成人工验收场景
```
