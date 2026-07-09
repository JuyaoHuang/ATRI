---
status: active
owner: asr
created: 2026-07-09
updated: 2026-07-09
source:
  - docs/developments/module-design/CN/ASR模块设计文档.md
related_code:
  - config.yaml
  - config/asr_config.yaml
  - src/asr/config.py
  - src/asr/service.py
  - src/routes/asr.py
  - frontend/src/stores/asr.ts
---

# ASR 配置与运行边界

用户侧安装和界面操作见 [ASR配置说明](../../../configs/CN/ASR配置说明.md)。本文只记录开发侧的配置语义和运行边界。

## 配置入口

根配置通过 `config.yaml` 引用：

```yaml
asr_config: config/asr_config.yaml
```

运行时加载路径是：

```text
config.yaml
  -> config/asr_config.yaml
  -> load_config()
  -> config["asr"]
  -> ASRConfigStore / ASRService
```

## 根字段

| 字段 | 作用 | 备注 |
| --- | --- | --- |
| `asr_model` | 当前活跃 Provider 名称 | 必须存在于 `ASRFactory.available()`。 |
| `persistent_provider` | 是否复用本地后端 Provider 实例 | 仅后端使用，前端配置 API 不暴露也不允许回写。 |
| `preload_provider` | 是否在启动后预加载当前本地 Provider | 仅后端使用。 |
| `auto_send.enabled` | 前端按钮式 ASR 转录后是否自动发送聊天 | 由前端 `InputBox.vue` 使用，不影响 VAD 后端自动提交。 |
| `auto_send.delay_ms` | 自动发送延迟 | 当前主要由 YAML 和前端 store 默认值提供。 |

一个重要现状是：**后端没有 ASR 根级 `enabled` 开关**。前端 `useASRStore().enabled` 是本地 `localStorage` UI 开关，不会写回 `config/asr_config.yaml`。

## Provider 配置块

当前配置文件中有以下主要块：

| 配置块 | 当前状态 | 说明 |
| --- | --- | --- |
| `web_speech_api` | 已注册 | 浏览器原生识别的配置镜像。 |
| `faster_whisper` | 已注册 | 本地 `faster_whisper` Provider。 |
| `sherpa_onnx_asr` | 已注册 | 本地 SenseVoice ONNX Provider。 |
| `whisper_cpp` | 已注册 | 本地 `pywhispercpp` Provider。 |
| `openai_whisper` | 已注册 | 云端 OpenAI 兼容上传转录 Provider。 |
| `whisper` | 历史残留 | YAML 和默认值中仍保留该块，但当前代码没有对应 Provider。 |

### `whisper` 历史残留

`config/asr_config.yaml`、`DEFAULT_ASR_CONFIG` 和前端类型里仍保留 `whisper` 配置块，但当前仓库没有 `src/asr/providers/whisper.py`，`ASRFactory.available()` 也不会返回 `whisper`。

因此：

- 不要把 `asr_model` 设成 `whisper`；
- 设置页和文档应以当前注册表而不是旧 YAML 注释为准；
- 如需恢复该 Provider，应先补齐实现和注册，再讨论开放配置。

## 前端可写边界

`PUT /api/asr/config` 并不会原样持久化所有字段。`ASRService` 会先做三层过滤：

1. 去掉已经被掩码的敏感值；
2. 去掉后端专属根字段 `persistent_provider`、`preload_provider`；
3. 去掉不在 Provider 白名单中的字段。

当前前端允许回写的字段如下：

| Provider | 允许回写 |
| --- | --- |
| `web_speech_api` | `language`、`continuous`、`interim_results`、`max_alternatives` |
| `faster_whisper` | `language` |
| `sherpa_onnx_asr` | `num_threads`、`use_itn`、`provider`、`debug` |
| `whisper_cpp` | 无 |
| `openai_whisper` | 无 |

这意味着：

- 本地模型路径、下载目录、云端 API 地址和提示词等字段默认视为后端控制项；
- 前端设置页更像“安全子集编辑器”，不是完整 YAML 编辑器。

## 敏感字段规则

敏感字段集合是：

```text
api_key, token, secret, password
```

规则如下：

- API 响应会把这些字段掩码成 `********`；
- 如果默认值是 `${ENV_VAR}` 占位符，磁盘回写时尽量保留占位符；
- 运行时若已解析出真实密钥，刷新磁盘配置时会保留内存中的真实值，不把占位符覆盖回运行态。

`openai_whisper.api_key` 因此应优先写成：

```yaml
openai_whisper:
  api_key: ${OPENAI_API_KEY}
```

## 上传转录契约

`POST /api/asr/transcribe` 接收：

- `audio` 文件；
- 可选表单字段 `source`、`sample_rate`、`channels`、`encoding`；
- 可选查询参数 `provider`。

默认上传适配器只会把“16 kHz WAV”转换为本地 Provider 所需的 float32 数组，并校验元数据是否匹配。非 WAV 上传是否可用，取决于具体 Provider 是否覆盖了 `async_transcribe_audio()`：

- `faster_whisper`：支持把非 WAV 写入临时文件后转录；
- `openai_whisper`：支持把上传文件直接转发给云接口；
- `sherpa_onnx_asr`、`whisper_cpp`：当前仍建议使用 16 kHz WAV；
- `web_speech_api`：不会处理上传。

## 与实时 VAD 的关系

VAD 后端链路不会走前端 `auto_send` 配置。`speech_end` 后：

```text
chat_ws audio buffer
  -> _float_audio_to_wav_bytes()
  -> ASRService.transcribe_audio()
  -> output:asr:transcript
  -> backend starts next chat task
```

这里的自动提交属于聊天 WebSocket 行为，不属于 ASR 配置页行为。

## 文档关系

- 旧 ASR 设计文档把大量“可能的配置”和“未来流式接口”写在同一层；本页只保留已落代码事实。
- `docs/configs/CN/ASR配置说明.md` 继续面向用户解释如何安装依赖和选择 Provider；本页不重复用户教程。
