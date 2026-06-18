# VAD 配置说明

> **适用范围**: VAD 实时语音打断  
> **配置文件**: `config/vad_config.yaml`  
> **相关配置**: `config/asr_config.yaml`  
> **最后更新**: 2026-06-19

本文说明 VAD（Voice Activity Detection，语音活动检测）的配置结构、Provider 选择、实时打断链路和常见排障方法。

---

## 1. 快速开始

当前开发验证配置使用 `silero_vad`：

```yaml
enabled: true
vad_model: silero_vad
sample_rate: 16000
pre_buffer_ms: 500

silero_vad:
  sample_rate: 16000
  prob_threshold: 0.4
  db_threshold: 60
  required_hits: 3
  required_misses: 24
  smoothing_window: 5
```

如果只想验证 WebSocket 和状态机，不想加载真实模型，可以切换到 `fake`：

```yaml
enabled: true
vad_model: fake

fake:
  speech_threshold: 0.05
  required_hits: 2
  required_misses: 10
```

修改 YAML 后需要重启后端服务。

---

## 2. 配置加载方式

根配置文件 `config.yaml` 通过下面的入口引用 VAD 配置：

```yaml
vad_config: config/vad_config.yaml
```

后端配置加载后，VAD 模块读取运行时的 `config["vad"]`：

```text
config/vad_config.yaml -> runtime config["vad"]
```

---

## 3. 顶层配置结构

```yaml
enabled: true
vad_model: silero_vad
sample_rate: 16000
pre_buffer_ms: 500

fake:
  speech_threshold: 0.05
  required_hits: 2
  required_misses: 10

silero_vad:
  sample_rate: 16000
  prob_threshold: 0.4
  db_threshold: 60
  required_hits: 3
  required_misses: 24
  smoothing_window: 5
```

### 顶层字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | boolean | 是否启用后端 VAD 处理。关闭后实时语音 chunk 不会触发打断和 ASR 自动提交。 |
| `vad_model` | string | 当前 VAD Provider。可选 `fake`、`silero_vad`。 |
| `sample_rate` | number | 后端 VAD 目标采样率。当前前端实时语音会重采样到 `16000`。 |
| `pre_buffer_ms` | number | `speech_start` 前保留的短音频长度，用于避免 ASR 吞掉句首。 |

---

## 4. Provider 配置

### 4.1 `fake`

`fake` 是开发和测试 Provider。它不加载模型，只按音频最大振幅判断是否有人声。

```yaml
vad_model: fake
fake:
  speech_threshold: 0.05
  required_hits: 2
  required_misses: 10
```

| 字段 | 说明 |
| --- | --- |
| `speech_threshold` | 单个音频 chunk 的最大绝对振幅达到该值时，视为一次语音命中。 |
| `required_hits` | 连续多少次命中后触发 `speech_start`。 |
| `required_misses` | 说话中连续多少次未命中后触发 `speech_end`。 |

`fake` 的防抖单位是前端发送到后端的 chunk，不是 Silero 的 32 ms 内部窗口。因此它只能用于联调和测试，不建议作为真实用户语音检测方案。

### 4.2 `silero_vad`

`silero_vad` 是当前真实 VAD Provider。它通过 `silero-vad` Python 包懒加载模型，并固定使用 CPU 推理。

```yaml
vad_model: silero_vad
silero_vad:
  sample_rate: 16000
  prob_threshold: 0.4
  db_threshold: 60
  required_hits: 3
  required_misses: 24
  smoothing_window: 5
```

| 字段 | 说明 |
| --- | --- |
| `sample_rate` | Silero 推理采样率。当前使用 `16000`。 |
| `prob_threshold` | Silero 模型语音概率阈值。高于该值才可能算作语音。 |
| `db_threshold` | 音量门槛。用于降低小噪声误触发概率。 |
| `required_hits` | 连续命中多少个 Silero 窗口后触发 `speech_start`。 |
| `required_misses` | 说话中连续未命中多少个 Silero 窗口后触发 `speech_end`。 |
| `smoothing_window` | 平滑窗口大小。后端按最近 N 个窗口的概率和分贝均值判断状态。 |

Silero 在 16 kHz 下使用 512 samples 内部窗口：

```text
Silero 内部窗口 = 512 samples / 16000 Hz = 32 ms
speech_start 理论防抖延时 = required_hits * 32 ms
speech_end 理论静默结束延时 = required_misses * 32 ms
```

当前默认值对应：

```text
speech_start 理论防抖延时 = 3 * 32 ms = 96 ms
speech_end 理论静默结束延时 = 24 * 32 ms = 768 ms
```

实际体感延迟还会叠加前端采集 chunk、网络传输、平滑窗口和 ASR 耗时。

---

## 5. 与 ASR 的关系

VAD 只负责判断“用户开始说话”和“用户说完了”。用户说完后的转写由 ASR Provider 完成。

实时语音自动聊天需要后端可调用的 ASR Provider，例如：

```yaml
asr_model: sherpa_onnx_asr
```

`web_speech_api` 是浏览器侧 ASR，后端无法调用它完成 `speech_end -> ASR -> 自动聊天`。因此：

- `web_speech_api` 下，VAD 仍可触发打断。
- `web_speech_api` 下，后端不会在 `speech_end` 后自动转写并提交聊天。
- 完整实时语音闭环需要使用 `sherpa_onnx_asr`、`faster_whisper`、`whisper_cpp` 或 `openai_whisper` 这类后端 Provider。

当前本地验证推荐：

```yaml
asr_model: sherpa_onnx_asr
persistent_provider: true
preload_provider: false
```

模型目录示例：

```text
models/asr-models/sherpa-onnx-sense-voice/
```

---

## 6. 运行链路

```text
前端实时 VAD button 开启
  -> 前端采集麦克风
  -> 重采样为 16 kHz / mono / PCM float array
  -> WebSocket 发送 input:audio:chunk
  -> 后端 VAD Provider 判断 speech_start / speech_end
  -> speech_start: 后端发送 control:interrupt，并取消旧 generation
  -> speech_end: 后端提交 ASR
  -> ASR 成功: 后端发送 output:asr:transcript
  -> 后端自动启动新一轮聊天
```

TTS 当前仍是 REST 完整音频链路。VAD 打断会停止前端播放，并让旧 generation 的 TTS 结果失效，但第一版不把 TTS 音频改为 WebSocket 流。

---

## 7. 常见问题

### 开启实时语音后提示 ASR 不支持后端转写

原因是当前 `asr_model` 为 `web_speech_api`。

处理方式：切换到后端 ASR Provider，例如 `sherpa_onnx_asr`，并确认模型路径和依赖可用。

### 说话被切成多句

主要看 `required_misses`。当前 Silero 默认值为 `24`，理论静默结束时间约 `768 ms`。

如果连续说话时太容易被切断，可以适当增大：

```yaml
silero_vad:
  required_misses: 30
```

### 背景噪声容易误触发

优先调高 `prob_threshold` 或 `db_threshold`：

```yaml
silero_vad:
  prob_threshold: 0.5
  db_threshold: 65
```

如果 speech_start 仍然太敏感，再适当增大 `required_hits`。

### 第一次识别很慢

本地 ASR Provider 首次加载模型会有冷启动。可以保持：

```yaml
persistent_provider: true
```

如果希望服务启动时提前加载当前 ASR Provider，可以设置：

```yaml
preload_provider: true
```

低内存服务器不建议一开始就开启预加载。

---

## 8. 自检方式

浏览器联调时，打开：

```text
F12 -> Network -> WS -> /ws -> 消息
```

完整链路应能观察到类似顺序：

```text
input:audio:chunk
control:listen-state
control:interrupt
output:asr:transcript
output:chat:chunk
```

后端自动化检查参考：

```powershell
uv run pytest tests/vad tests/routes/test_chat_ws.py tests/routes/test_asr.py -q
```

前端检查参考：

```powershell
cd frontend
npm run type-check
npm run lint
npm run build
```

