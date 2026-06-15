# VAD 模块测试执行说明

## 测试范围

验证 M1 后端 VAD 模块骨架：

1. `fake` 与 `silero_vad` provider 已注册。
2. `VADService` 可接收音频 chunk 并输出稳定事件。
3. `required_hits` 可防止 speech_start 误触发。
4. `required_misses` 可防止 speech_end 过早触发。
5. VAD 关闭时返回明确的 silence 状态。
6. 根配置 `config.yaml` 可加载 `config/vad_config.yaml`。

## 执行命令

```bash
uv run pytest tests/vad -v
```

## 期望结果

1. 所有 `tests/vad` 用例通过。
2. 测试环境不需要安装或加载 Silero、torch 等真实模型依赖。
3. fake provider 可用于后续 WebSocket 和 ASR 衔接测试。
