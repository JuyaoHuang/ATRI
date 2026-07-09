---
status: active
owner: asr
created: 2026-07-09
updated: 2026-07-09
source:
  - docs/developments/module-design/CN/ASR模块设计文档.md
related_code:
  - src/asr/providers/__init__.py
  - src/asr/providers/web_speech_api.py
  - src/asr/providers/faster_whisper.py
  - src/asr/providers/sherpa_onnx_asr.py
  - src/asr/providers/whisper_cpp.py
  - src/asr/providers/openai_whisper.py
---

# ASR Provider 矩阵

本页只描述当前 `ASRFactory` 已注册的 Provider。是否“出现在旧文档或旧 YAML 里”不构成当前实现事实。

## 当前注册表

| Provider | 类型 | `supports_backend_transcription` | `supports_browser_streaming` | 主要输入 | 当前要点 |
| --- | --- | --- | --- | --- | --- |
| `web_speech_api` | `browser` | 否 | 是 | 浏览器原生语音识别 | 后端只保存配置和状态，不接收上传音频。 |
| `faster_whisper` | `local` | 是 | 否 | float32 数组、WAV、部分浏览器录音格式 | 本地通用后端 Provider，支持临时文件兜底。 |
| `sherpa_onnx_asr` | `local` | 是 | 否 | float32 数组、16 kHz WAV | 当前实现只支持 SenseVoice 路径。 |
| `whisper_cpp` | `local` | 是 | 否 | float32 数组、16 kHz WAV | 依赖 `pywhispercpp`，不做通用浏览器格式解码。 |
| `openai_whisper` | `cloud` | 是 | 否 | 上传文件字节 | 每次请求创建 OpenAI 兼容客户端。 |

## 逐项说明

### `web_speech_api`

- 元数据：`provider_type="browser"`、`supports_browser_streaming=true`。
- `health()` 始终返回可用，但原因文本会提示“浏览器可用性在前端检查”。
- `transcribe_np()` 和 `async_transcribe_audio()` 都会抛出不可用异常。
- 适合做设置页展示和前端能力选择，不适合做后端转录入口。

### `faster_whisper`

- 依赖：`faster_whisper` Python 包。
- 健康前提：`model_path` 非空。
- 输入：
  - WAV 时复用 `ASRInterface` 默认数组适配器；
  - 非 WAV 时写入临时文件并调用模型转录文件路径。
- 适合：
  - 设置页录音测试；
  - VAD `speech_end` 后端转录；
  - 本地常驻缓存和预加载。

### `sherpa_onnx_asr`

- 依赖：`sherpa-onnx`、`onnxruntime`。
- 健康前提：
  - `model_type` 必须是 `sense_voice`；
  - `sense_voice` 和 `tokens` 文件必须存在；
  - `provider` 必须是 `cpu` 或 `cuda`；
  - `sample_rate` 必须是 16000。
- 输入：当前走默认 WAV/float32 数组契约。
- 适合：本地固定模型、CPU 友好、与 VAD 闭环对齐的后端转录。

### `whisper_cpp`

- 依赖：`pywhispercpp`。
- 健康前提：`model_name` 非空。
- 输入：当前依赖默认 WAV/float32 数组契约。
- 适合：本地轻量部署；不适合直接接浏览器非 WAV 录音上传。

### `openai_whisper`

- 依赖：`openai`。
- 健康前提：
  - `api_key` 已配置且不是 `${...}` 占位符；
  - `model` 非空。
- 输入：上传文件字节；Provider 会保留原始扩展名写入临时文件后调用 API。
- 注意：不支持 numpy 数组路径，因此 `transcribe_np()` 会直接报错。

## 当前缺席项

旧文档和旧 YAML 中提到过 `whisper` Provider，但当前注册表没有它。对长期文档而言，它属于“未实现状态”，而不是“可选 Provider”。

## 选择建议

| 场景 | 建议 |
| --- | --- |
| 浏览器原生实时识别 | `web_speech_api` |
| 本地统一后端上传转录 | `faster_whisper` 或 `sherpa_onnx_asr` |
| 资源更轻的本地方案 | `whisper_cpp` |
| 云端上传转录 | `openai_whisper` |

## 文档关系

- 旧 ASR 设计文档列过 6 个 Provider，并把 `whisper` 计入正式能力；本页按 `src/asr/providers/__init__.py` 纠偏。
- Provider 的安装细节和用户操作继续放在 `docs/configs/CN/ASR配置说明.md`，本页只保留开发侧事实。
