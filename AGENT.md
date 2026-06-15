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
- **当前 VAD 文档位置**: `docs/developments/wiki/VAD/`
  - `vad-design.md` — VAD、ASR、TTS 链路设计
  - `vad-implement.md` — VAD 开发边界与架构说明
  - `vad-implementation-plan.md` — VAD 分阶段实施计划
- **实现前必读**: 修改某个模块前，先阅读对应的设计文档章节

---

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

- **编写 test-exe.md 文档，给出测试指令和期望验收成果，方便管理员验收**。test-exe.md 位于每个系统测试目录下，以 memory system 为例，text-exe.md 位于"tests\memory"。编写内容参考"tests\memory\test-exe.md"


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

## 提交规范

- 在开始子系统的实现前（如 LLM 调用模块），执行`git checkout -b feat/...` 切换分支，在新分支上开发
- 每个功能点一个 commit，不要把多个不相关的改动混在一起
- commit message 格式：`<type>: <description>`
  - `feat:` 新功能
  - `fix:` 修复
  - `refactor:` 重构
  - `docs:` 文档
  - `chore:` 构建/依赖/配置
- 示例：`feat: implement LLM registry factory and openai_compatible provider`，**注意**：commit 内容应该简洁，重点描述做了什么，不附带任何的 AI 协助信息，例如"aaaa@claude.com<cooperate by claude>"。
- 提交 commit 时如果触发 GPG 签名验证，前往`.env`文件获取密码`GPG_VERIFY_KEY`
- 在实现功能后，等待负责人验收。
- 验收结束后，执行`git push` 推送到上游仓库，并且执行`gh pr`进 PR 的提交 

## 实现顺序

1. 在开始实现前，执行`git checkout -b feat/...` 切换分支，在新分支上开发
2. 每完成一个功能点一个 commit，不要把多个不相关的改动混在一起

当前主线任务为 VAD 语音实时打断。按 `docs/developments/wiki/VAD/vad-implementation-plan.md` 的里程碑推进：

```
M0: 文档与范围冻结
  ├── 明确 ATRI 当前语音链路
  ├── 明确 OLV 参考实现思路
  └── 明确第一版保留 REST TTS，不先重写全部 TTS 链路

M1: 后端 VAD 模块骨架
  ├── 新增 src/vad/ 模块
  ├── 建立 interface / factory / service / session / providers 结构
  ├── 增加 fake provider 用于测试
  └── 预留 Silero provider，避免硬编码到聊天、ASR、TTS 流程

M2: WebSocket 协议扩展
  ├── 支持前端发送麦克风音频 chunk
  ├── 支持后端发送 interrupt 控制事件
  ├── 为每个连接维护 VADSession 与音频缓存
  └── 为每个连接维护当前 LLM task 引用

M3: 前端实时麦克风输入
  ├── 在 atri/frontend 中新增实时语音输入能力
  ├── 将麦克风音频片段通过 WebSocket 发送给后端
  ├── 接收 interrupt 后调用现有 audio player stop 能力
  └── 保留原有按钮式 ASR 和 stop button

M4: VAD 到 ASR 的衔接
  ├── speech_start 后缓存有效音频
  ├── speech_end 后提交现有 ASR service
  ├── 将 ASR 转写文本返回前端展示
  └── 将 ASR 文本接入现有聊天流程

M5: LLM 生成打断
  ├── VAD speech_start 触发当前 LLM task cancel
  ├── 停止继续推送上一轮文本
  ├── 阻止被打断回复继续触发 TTS
  └── 明确 interrupted 回复的历史与记忆写入策略

M6: 配置、测试与文档补齐
  ├── 增加 VAD 配置文档
  ├── 增加后端单元测试与 WebSocket 集成测试
  ├── 增加前端构建或类型检查验证
  └── 在对应测试目录编写 test-exe.md

M7: 可选 TTS WebSocket 化
  ├── LLM 文本按句子或短段切分
  ├── 后端按段合成 TTS 音频
  ├── 通过 WebSocket 下发音频 payload 与 sequence
  └── interrupt 时取消后续 TTS 任务并清空前端播放队列
```
