# TTS 分段流式化测试执行指令

## 1. 后端 TTS 单元测试

```bash
uv run pytest tests/tts/ -v
```

期望：
- `SentenceDivider` 能按中文句号切分，并在 `faster_first_response=true` 时允许首段按短停顿提前切出。
- `TTSSegmentManager` 能合成单段、多段乱序完成后按 sequence 下发、finish flush 剩余文本、interrupt 丢弃旧结果。
- 单个 segment 合成失败时发送 `output:audio:error` 语义的错误对象，并继续后续 segment。

## 2. 后端 WebSocket 集成测试

```bash
uv run pytest tests/routes/test_chat_ws.py -v
```

期望：
- streaming disabled 时不发送 `output:audio:*`。
- streaming enabled 时发送 `output:audio:segment` 和 `output:audio:complete`。
- VAD `speech_start` 会取消当前 generation 的 TTS manager，并向前端发送带 `generation_id` 的 `control:interrupt`。
- TTS segment 失败只产生 `output:audio:error`，不影响 `output:chat:complete`。

## 3. 后端基础检查

```bash
uv run python -m mypy src/ --ignore-missing-imports
uv run ruff format src/tts src/routes/chat_ws.py tests/tts tests/routes/test_chat_ws.py
uv run ruff check src/tts src/routes/chat_ws.py tests/tts tests/routes/test_chat_ws.py --fix
uv run pytest tests/ -v
```

期望：
- mypy 无类型错误。
- ruff 无错误。
- 全量 pytest 通过。

## 4. 前端检查

```bash
cd frontend
npm run type-check
npm run lint
npm run build
```

期望：
- TypeScript 类型检查通过。
- ESLint 无 error；当前既有 warning 不阻塞构建。
- Vite production build 成功。

## 5. 人工验收场景

1. 在 `config/tts_config.yaml` 中开启：

   ```yaml
   enabled: true
   auto_play: true
   streaming:
     enabled: true
   ```

2. 启动后端和前端，发送一条较长文本对话。
3. 观察前端在 `output:chat:complete` 前收到并播放第一段语音。
4. 说话触发 VAD interrupt，当前音频立即停止，旧 generation 的后续 segment 不再播放。
5. 关闭 `streaming.enabled` 后再次对话，自动 TTS 回到原来的 complete 后 REST 合成路径。
6. 点击历史 AI 消息的播放按钮，仍通过 REST TTS 播放，不依赖 streaming generation。
