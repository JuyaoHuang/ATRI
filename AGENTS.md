> 本文档定义 agents 在本项目中编写代码时必须遵循的流程和规范。每次编写/修改代码后，按此清单执行。

---

## 项目上下文

- **项目名**: emotion-robot (atri)
- **技术栈**: Python 3.11+ / FastAPI / uv / loguru
- **Python 环境**: 当前工作目录存在 uv 创建的 `.venv`，执行 Python、测试、格式化、类型检查时优先使用 `uv run ...`
- **正式设计文档位置**: `docs/`
  - `developments/README.md` — 开发文档导航和阅读入口
  - `developments/architecture/` — 项目级架构、分层和跨模块数据流
  - `developments/api/` — REST API、WebSocket 和事件协议
  - `developments/modules/` — 长期模块设计，目录尽量对齐 `src/`
  - `developments/features/` — 某次 feature 的设计、计划、日志和验收
  - `developments/wiki/` — GitHub Wiki 本地预发布稿
  - `developments/decisions/` — ADR 技术决策记录
- **旧设计文档位置**: `docs/developments/module-design/`
  - 该目录仍可作为历史设计来源；新增长期结论应逐步迁移到 `developments/modules/`
- **TTS 文档位置**:
  - `developments/modules/tts/README.zh-CN.md` — TTS 长期设计入口
  - `developments/modules/tts/streaming-design.zh-CN.md` — TTS 分段流式化长期设计
  - `developments/modules/tts/config.zh-CN.md` — TTS 配置与运行边界
  - `developments/features/2026-07-tts-segment-streaming/README.zh-CN.md` — TTS 分段流式化 feature 过程入口
- **VAD 文档位置**:
  - `developments/features/2026-06-vad-realtime-interrupt/README.zh-CN.md` — VAD 实时打断 feature 过程入口
  - `developments/features/2026-06-vad-realtime-interrupt/dev-log.zh-CN.md` — VAD 实时打断开发日志
  - `developments/wiki/development-blogs/2026-07-08-vad-realtime-interrupt.zh-CN.md` — VAD Wiki 发布稿
  - `developments/wiki/VAD/` — 旧设计、旧计划和原始长日志的过渡来源
- **实现前必读**: 修改某个模块前，先读 `docs/developments/README.md`，再读对应 `developments/modules/<module>/` 和相关 feature 文档。

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

当前文档整理任务按 `docs/文档构建思路.md` 推进。新增或迁移文档时遵守：

```text
docs/developments/
├── README.md                         # 开发文档总入口
├── architecture/                     # 项目级长期架构
├── api/                              # 稳定接口和协议
├── modules/<module>/                 # 长期模块设计
├── features/YYYY-MM-feature-slug/    # feature 过程文档
├── wiki/                             # GitHub Wiki 预发布稿
├── decisions/                        # ADR 技术决策记录
├── templates/                        # 文档模板
└── archive/                          # 历史归档
```

整理规则：

1. 用户教程和配置步骤继续留在 `docs/configs/`。
2. 长期有效的模块边界沉淀到 `docs/developments/modules/<module>/`。
3. 某次 feature 的设计、实施计划、开发日志和验收放入 `docs/developments/features/YYYY-MM-feature-slug/`。
4. 准备发布到 GitHub Wiki 的文章放入 `docs/developments/wiki/`。
5. 原始长日志、旧草稿和会话备份不要直接删除；需要迁移时先保留旧入口或放入 `archive/`。
6. 旧 `docs/developments/wiki/TTS/` 和 `docs/developments/wiki/VAD/` 作为过渡来源保留；新增长期设计不要继续写入这些旧目录。
7. TTS 分段流式化已完成第一版，后续以 `docs/developments/modules/tts/streaming-design.zh-CN.md` 作为长期设计依据。
