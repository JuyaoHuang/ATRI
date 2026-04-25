# CosyVoice3 TTS 使用说明

本文说明 ATRI 后端 `cosyvoice3_tts` 的当前实现状态、配置方法、参数含义，以及 CosyVoice3 的音色模型机制。

## 当前实现状态

`cosyvoice3_tts` 的工厂已经实现。

相关代码：

- `src/tts/providers/cosyvoice3_tts.py`
  - 通过 `@TTSFactory.register("cosyvoice3_tts", ...)` 注册到 TTS 工厂。
  - Provider 类为 `CosyVoice3TTSProvider`。
  - 通过 `gradio_client.Client(client_url).predict(...)` 调用 CosyVoice Gradio 服务。
- `src/tts/providers/__init__.py`
  - 已导入 `cosyvoice3_tts`，服务启动时会完成注册。
- `src/tts/service.py`
  - 允许前端/接口回写的字段仅为 `stream`、`speed`。

当前实现是“调用外部 CosyVoice Gradio WebUI”，不是在 ATRI 进程内直接加载 CosyVoice3 模型。

## 官方链接

- CosyVoice GitHub 仓库：<https://github.com/FunAudioLLM/CosyVoice>
- CosyVoice3 官方展示页：<https://funaudiollm.github.io/cosyvoice3/>
- CosyVoice3 Hugging Face 模型卡：<https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512>
- 官方 WebUI 示例源码：<https://github.com/FunAudioLLM/CosyVoice/blob/main/webui.py>
- CosyVoice3 论文：<https://arxiv.org/abs/2505.17589>

## 基本使用流程

1. 单独启动 CosyVoice Gradio WebUI。

   ATRI 默认连接：

   ```yaml
   cosyvoice3_tts:
     client_url: http://127.0.0.1:50000/
   ```

   因此 CosyVoice WebUI 需要监听 `50000` 端口，或者把 `client_url` 改成实际地址。

2. 在 `config/tts_config.yaml` 中选择 provider：

   ```yaml
   tts_model: cosyvoice3_tts
   ```

3. 确认后端依赖存在：

   ```bash
   uv sync
   ```

   `pyproject.toml` 已包含 `gradio-client`。

4. 在前端设置页选择 `CosyVoice3`，然后配置允许前端调整的字段：

   - `Request streaming mode`：写入 `stream`
   - `Speed`：写入 `speed`

   `sft_dropdown` 会只读显示。需要修改时，直接编辑 `config/tts_config.yaml`。

## 音色模型机制

CosyVoice3 不使用 Edge TTS 那种固定云端音色列表，例如 `zh-CN-XiaoxiaoNeural`。

CosyVoice 的“音色”主要来自两类机制：

- 预训练音色，也就是 WebUI 里的 `sft_dropdown`。
- 参考音频复刻，也就是通过 `prompt_wav_upload_url` 或 `prompt_wav_record_url` 提供参考音频。

官方 WebUI 中，预训练音色列表来自服务端模型对象的 `list_available_spks()`。这意味着可选音色取决于你本地加载的模型目录，而不是 ATRI 前端内置列表。

当前 ATRI 的 `/api/tts/voices?provider=cosyvoice3_tts` 只返回配置文件里的当前 `sft_dropdown`，不会主动从 CosyVoice WebUI 动态拉取完整音色列表。实际可用的 `sft_dropdown` 需要以你启动的 CosyVoice WebUI 下拉框为准。

## 配置示例

```yaml
cosyvoice3_tts:
  client_url: http://127.0.0.1:50000/
  mode_checkbox_group: 预训练音色
  sft_dropdown: 中文女
  prompt_text: ''
  prompt_wav_upload_url: https://github.com/gradio-app/gradio/raw/main/test/test_files/audio_sample.wav
  prompt_wav_record_url: https://github.com/gradio-app/gradio/raw/main/test/test_files/audio_sample.wav
  instruct_text: ''
  stream: false
  seed: 0
  speed: 1.0
  api_name: /generate_audio
```

## 参数说明

| 字段 | 是否允许前端回写 | 作用 |
| --- | --- | --- |
| `client_url` | 否 | CosyVoice Gradio WebUI 地址。ATRI 通过这个地址调用本地或远程 CosyVoice 服务。 |
| `mode_checkbox_group` | 否 | 推理模式。常见值为 `预训练音色`、`3s极速复刻`、`跨语种复刻`、`自然语言控制`。 |
| `sft_dropdown` | 否 | 预训练音色 ID。只在预训练音色模式、部分自然语言控制模式中有意义。 |
| `prompt_text` | 否 | 参考音频对应的文本。3 秒复刻模式通常需要它和参考音频内容一致。 |
| `prompt_wav_upload_url` | 否 | 上传参考音频的路径或 URL。复刻/跨语种模式使用。 |
| `prompt_wav_record_url` | 否 | 录制参考音频的路径或 URL。当前实现会传给 Gradio 接口。 |
| `instruct_text` | 否 | 自然语言控制指令，例如要求情绪、方言、语速、音量等。 |
| `stream` | 是 | 请求 CosyVoice WebUI 使用流式推理。ATRI 当前仍把结果作为完整音频返回给前端。 |
| `seed` | 否 | 随机种子。固定后有助于复现相近结果。 |
| `speed` | 是 | 语速倍率。通常 `1.0` 为正常速度，低于 1 变慢，高于 1 变快。 |
| `api_name` | 否 | Gradio API 名称。当前适配默认 `/generate_audio`。 |

## 推理模式说明

### 预训练音色

使用 `sft_dropdown` 指定服务端已有音色。

适合场景：

- 只想用模型自带音色。
- 不想准备参考音频。
- 希望配置最简单。

此模式下，`prompt_text`、`prompt_wav_upload_url`、`prompt_wav_record_url`、`instruct_text` 通常会被服务端忽略。

### 3s 极速复刻

使用参考音频克隆音色。

关键参数：

- `prompt_wav_upload_url` 或 `prompt_wav_record_url`
- `prompt_text`

`prompt_text` 应该和参考音频中的实际语音内容一致。参考音频质量会直接影响克隆效果。

### 跨语种复刻

使用参考音频提供说话人音色，但生成文本可以是另一种语言。

关键参数：

- `prompt_wav_upload_url` 或 `prompt_wav_record_url`
- `mode_checkbox_group: 跨语种复刻`

此模式更依赖参考音频质量。参考音频建议清晰、无背景噪声、说话人单一。

### 自然语言控制

通过 `instruct_text` 控制风格，例如方言、情绪、语速或音量。

CosyVoice3 官方模型卡展示的是更偏 `inference_instruct2` 的用法。ATRI 当前不是直接调用 Python API，而是把参数转发给 Gradio WebUI，因此实际行为以你启动的 WebUI 实现为准。

## `prompt_wav_upload_url` 和 `prompt_wav_record_url` 的区别

这两个字段最终都表示“参考音频”。

- `prompt_wav_upload_url` 对应 WebUI 里上传的音频文件。
- `prompt_wav_record_url` 对应 WebUI 里录制的音频文件。

在当前 ATRI 实现中，两者都会通过 `gradio_client.handle_file(...)` 传给 CosyVoice WebUI。

如果两者都配置，服务端 WebUI 的处理逻辑通常会优先使用上传音频。具体优先级取决于你运行的 CosyVoice WebUI 代码。

## 常见问题

### 前端为什么不应该显示 Edge 的音色列表？

因为 CosyVoice3 的音色不是 Edge TTS 的云端 voice ID。Edge 的 `zh-CN-XiaoxiaoNeural`、`en-US-AriaNeural` 等 ID 对 CosyVoice3 没有意义。

如果前端切到 CosyVoice3 后看到 Edge 音色，通常是前端保留了上一个 provider 的 voices 缓存，而不是 CosyVoice3 真实支持这些音色。

### `sft_dropdown` 应该填什么？

打开你启动的 CosyVoice WebUI，查看“选择预训练音色”下拉框。里面显示的值就是可用的 `sft_dropdown`。

不同模型目录的预训练音色可能不同。如果模型没有 SFT 预训练音色，WebUI 可能只显示空值。

### 为什么有些配置前端不允许修改？

ATRI 当前只允许前端修改高频、安全的运行参数：

- `stream`
- `speed`

其他字段通常和本地服务部署、参考音频路径、Gradio 接口形状有关。让前端回写这些字段容易覆盖手动配置。

### CosyVoice3 支持音色克隆吗？

支持。官方模型卡介绍了 zero-shot multilingual speech synthesis，并展示了 zero-shot、cross-lingual、instruct 等用法。实际在 ATRI 中，需要通过 CosyVoice Gradio WebUI 的复刻模式和参考音频参数实现。
