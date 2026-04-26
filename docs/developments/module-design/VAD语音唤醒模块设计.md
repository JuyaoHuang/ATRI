# VAD 语音唤醒模块设计文档

**版本**：v1.0  
**创建日期**：2026-04-23  
**状态**：待实现（Phase 12 或独立 Phase）

---

## 1. 概述

### 1.1 什么是 VAD

**VAD（Voice Activity Detection，语音活动检测）** 是一种检测音频流中是否存在人声的技术。在语音交互系统中，VAD 用于：

- **语音唤醒（Wake Word）**：检测用户开始说话，自动触发录音
- **语音端点检测**：检测用户停止说话，自动结束录音
- **降低误触发**：过滤环境噪音，只在真正有人声时触发

### 1.2 为什么需要 VAD

在 emotion-robot 项目中，VAD 可以提升用户体验：

- ✅ **免按钮交互**：用户无需点击录音按钮，直接说话即可
- ✅ **自动端点检测**：用户说完话后自动停止录音，无需手动点击停止
- ✅ **降低延迟**：检测到语音后立即开始录音，减少等待时间
- ✅ **提升沉浸感**：更自然的对话体验

---

## 2. Open-LLM-VTuber 的 VAD 实现

### 2.1 技术选型

OLV 使用 **Silero VAD** 作为 VAD 引擎：

- **模型**：`silero-vad`（PyTorch 模型）
- **优点**：
  - 轻量级（~1MB）
  - 高精度（误报率低）
  - 支持多语言
  - 完全离线运行
  - CPU 友好
- **缺点**：
  - 需要 Python 环境
  - 需要 PyTorch 依赖

### 2.2 核心配置参数

OLV 的 VAD 配置（`conf.yaml`）：

```yaml
vad_config:
  vad_model: 'silero_vad'
  
  silero_vad:
    orig_sr: 16000           # 原始音频采样率（Hz）
    target_sr: 16000         # 目标音频采样率（Hz）
    prob_threshold: 0.4      # 语音概率阈值（0-1）
    db_threshold: 60         # 分贝阈值（dB）
    required_hits: 3         # 连续命中次数（3 * 0.032s = 0.1s）
    required_misses: 24      # 连续未命中次数（24 * 0.032s = 0.8s）
    smoothing_window: 5      # 平滑窗口大小
```

**参数说明**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `orig_sr` | 16000 | 原始音频采样率，通常为 16kHz |
| `target_sr` | 16000 | 目标音频采样率，与 ASR 模型匹配 |
| `prob_threshold` | 0.4 | 语音概率阈值，越高越严格（0.3-0.5 推荐） |
| `db_threshold` | 60 | 分贝阈值，过滤低音量噪音（50-70 推荐） |
| `required_hits` | 3 | 连续检测到语音的次数，避免误触发 |
| `required_misses` | 24 | 连续检测到静音的次数，确认语音结束 |
| `smoothing_window` | 5 | 平滑窗口，减少抖动 |

### 2.3 工作原理

**状态机设计**：

```
IDLE（空闲）
  ↓ 检测到语音（连续 3 次命中）
ACTIVE（活跃）
  ↓ 检测到静音（连续 24 次未命中）
INACTIVE（非活跃）
  ↓ 再次检测到语音（连续 3 次命中）
ACTIVE（活跃）
  ↓ 持续静音（连续 24 次未命中）
IDLE（空闲）→ 输出完整语音片段
```

**时间计算**：
- 每个音频块：512 samples / 16000 Hz = 0.032 秒
- 触发延迟：3 * 0.032s = 0.1 秒
- 结束延迟：24 * 0.032s = 0.8 秒

### 2.4 核心代码结构

**接口定义**（`vad_interface.py`）：

```python
class VADInterface(ABC):
    @abstractmethod
    def detect_speech(self, audio_data: bytes):
        """检测音频中的语音活动"""
        pass
```

**工厂模式**（`vad_factory.py`）：

```python
class VADFactory:
    @staticmethod
    def get_vad_engine(engine_type, **kwargs) -> VADInterface:
        if engine_type == "silero_vad":
            from .silero import VADEngine
            return VADEngine(
                orig_sr=kwargs.get("orig_sr"),
                target_sr=kwargs.get("target_sr"),
                prob_threshold=kwargs.get("prob_threshold"),
                db_threshold=kwargs.get("db_threshold"),
                required_hits=kwargs.get("required_hits"),
                required_misses=kwargs.get("required_misses"),
                smoothing_window=kwargs.get("smoothing_window"),
            )
```

**Silero VAD 实现**（`silero.py`）：

```python
class VADEngine(VADInterface):
    def __init__(self, orig_sr=16000, target_sr=16000, 
                 prob_threshold=0.4, db_threshold=60,
                 required_hits=3, required_misses=24,
                 smoothing_window=5):
        self.config = SileroVADConfig(...)
        self.model = load_silero_vad()  # 加载 Silero VAD 模型
        self.state = StateMachine(self.config)
        
    def detect_speech(self, audio_data: list[float]):
        """检测语音活动，返回包含人声的音频片段"""
        for chunk in audio_chunks:
            speech_prob = self.model(chunk, self.config.target_sr)
            for audio_bytes in self.state.get_result(speech_prob, chunk):
                yield audio_bytes
```

---

## 3. 在 emotion-robot 中复用 VAD

### 3.1 复用策略

**方案 A：完全复用 OLV 的 Silero VAD 实现（推荐）**

**优点**：
- ✅ 成熟稳定，已在 OLV 中验证
- ✅ 配置完善，参数可调
- ✅ 完全离线，无需云服务
- ✅ 代码结构清晰，易于集成

**缺点**：
- ⚠️ 需要 Python 后端支持
- ⚠️ 需要安装 `silero-vad` 和 `torch` 依赖
- ⚠️ 增加后端复杂度

**实施步骤**：

1. **后端集成**（`atri/src/vad/`）：
   ```
   atri/src/vad/
   ├── __init__.py
   ├── interface.py          # VAD 接口定义
   ├── factory.py            # VAD 工厂类
   ├── exceptions.py         # VAD 异常
   └── providers/
       ├── __init__.py
       └── silero_vad.py     # Silero VAD 实现（复用 OLV）
   ```

2. **配置管理**（`atri/src/config/vad.py`）：
   ```python
   class SileroVADConfig(BaseModel):
       orig_sr: int = 16000
       target_sr: int = 16000
       prob_threshold: float = 0.4
       db_threshold: int = 60
       required_hits: int = 3
       required_misses: int = 24
       smoothing_window: int = 5
   
   class VADConfig(BaseModel):
       enabled: bool = False  # 默认关闭
       provider: str = "silero_vad"
       silero_vad: SileroVADConfig = SileroVADConfig()
   ```

3. **API 端点**（`atri/src/api/vad.py`）：
   ```python
   @router.post("/vad/detect")
   async def detect_voice_activity(audio: UploadFile):
       """检测音频中的语音活动"""
       vad_engine = VADFactory.get_vad_engine("silero_vad", **config)
       audio_data = await audio.read()
       speech_segments = vad_engine.detect_speech(audio_data)
       return {"segments": speech_segments}
   ```

4. **前端集成**（`atri-webui/src/composables/useVAD.ts`）：
   ```typescript
   export function useVAD() {
     const isListening = ref(false)
     const audioContext = new AudioContext()
     
     async function startListening() {
       const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
       const processor = audioContext.createScriptProcessor(512, 1, 1)
       
       processor.onaudioprocess = async (e) => {
         const audioData = e.inputBuffer.getChannelData(0)
         const response = await api.vad.detect(audioData)
         if (response.segments.length > 0) {
           // 检测到语音，触发录音
           emit('voice-detected', response.segments)
         }
       }
     }
   }
   ```

5. **依赖安装**（`atri/pyproject.toml`）：
   ```toml
   [project.optional-dependencies]
   vad = [
       "silero-vad>=5.1",
       "torch>=2.0.0",
   ]
   ```

### 3.2 替代方案

**方案 B：使用浏览器端 Web Speech API**

**优点**：
- ✅ 零成本，浏览器原生支持
- ✅ 无需后端服务
- ✅ 实现简单

**缺点**：
- ⚠️ 功能有限，无法精细调参
- ⚠️ 浏览器兼容性问题（Chrome/Edge 支持较好）
- ⚠️ 需要网络连接（部分浏览器）

**实施示例**：

```typescript
// atri-webui/src/composables/useWebSpeechVAD.ts
export function useWebSpeechVAD() {
  const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)()
  
  recognition.continuous = true
  recognition.interimResults = true
  
  recognition.onstart = () => {
    console.log('VAD started')
  }
  
  recognition.onresult = (event) => {
    const transcript = event.results[event.results.length - 1][0].transcript
    emit('voice-detected', transcript)
  }
  
  recognition.start()
}
```

---

## 4. 实施建议

### 4.1 Phase 划分建议

**建议：作为独立 Phase 12 实现**

- **Phase 12：VAD 语音唤醒**
  - 后端：Silero VAD 集成
  - 前端：自动录音触发
  - 设置页面：VAD 参数配置
  - 预估时间：3-4 天

**理由**：
1. Phase 9（ASR）已包含 4 个 Provider，工作量较大
2. VAD 是独立功能，不影响核心 ASR 功能
3. 可以根据用户反馈决定是否需要 VAD
4. 降低 Phase 9 的复杂度和风险

### 4.2 配置建议

**默认配置**（适合大多数场景）：

```yaml
vad_config:
  enabled: false  # 默认关闭，用户手动开启
  provider: 'silero_vad'
  
  silero_vad:
    orig_sr: 16000
    target_sr: 16000
    prob_threshold: 0.4      # 中等灵敏度
    db_threshold: 60         # 过滤低音量噪音
    required_hits: 3         # 0.1s 触发延迟
    required_misses: 24      # 0.8s 结束延迟
    smoothing_window: 5
```

**高灵敏度配置**（安静环境）：

```yaml
silero_vad:
  prob_threshold: 0.3      # 更低阈值
  db_threshold: 50         # 更低分贝
  required_hits: 2         # 更快触发
  required_misses: 18      # 更快结束
```

**低灵敏度配置**（嘈杂环境）：

```yaml
silero_vad:
  prob_threshold: 0.5      # 更高阈值
  db_threshold: 70         # 更高分贝
  required_hits: 5         # 更慢触发
  required_misses: 30      # 更慢结束
```

### 4.3 前端 UI 建议

**设置页面**（`atri-webui/src/pages/settings/modules/hearing.vue`）：

```vue
<template>
  <div class="vad-settings">
    <h3>语音唤醒（VAD）</h3>
    
    <!-- 开关 -->
    <Switch v-model="vadEnabled" label="启用语音唤醒" />
    
    <!-- 灵敏度预设 -->
    <Select v-model="vadPreset" label="灵敏度预设">
      <option value="low">低（嘈杂环境）</option>
      <option value="medium">中（推荐）</option>
      <option value="high">高（安静环境）</option>
      <option value="custom">自定义</option>
    </Select>
    
    <!-- 高级参数（仅在自定义模式显示） -->
    <div v-if="vadPreset === 'custom'">
      <Slider v-model="probThreshold" label="语音概率阈值" :min="0.2" :max="0.6" :step="0.05" />
      <Slider v-model="dbThreshold" label="分贝阈值" :min="40" :max="80" :step="5" />
      <Slider v-model="requiredHits" label="触发延迟" :min="1" :max="10" :step="1" />
      <Slider v-model="requiredMisses" label="结束延迟" :min="10" :max="40" :step="2" />
    </div>
    
    <!-- 测试按钮 -->
    <Button @click="testVAD">测试 VAD</Button>
  </div>
</template>
```

---

## 5. 参考资源

### 5.1 Silero VAD

- **GitHub**：https://github.com/snakers4/silero-vad
- **文档**：https://github.com/snakers4/silero-vad/wiki
- **模型下载**：https://github.com/snakers4/silero-vad/releases

### 5.2 Open-LLM-VTuber 实现

- **仓库**：https://github.com/t41372/Open-LLM-VTuber
- **VAD 模块**：`src/open_llm_vtuber/vad/`
- **配置文件**：`conf.yaml`（`vad_config` 部分）

### 5.3 相关技术

- **WebRTC VAD**：https://webrtc.org/
- **PyAudio**：https://people.csail.mit.edu/hubert/pyaudio/
- **Web Speech API**：https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API

---

## 6. 总结

### 6.1 核心要点

1. **VAD 是语音唤醒的核心技术**，可以实现免按钮交互
2. **OLV 使用 Silero VAD**，成熟稳定，完全离线
3. **推荐作为独立 Phase 12 实现**，不影响 Phase 9 的 ASR 核心功能
4. **默认关闭 VAD**，用户可在设置页面手动开启

### 6.2 实施优先级

- **P0（必须）**：Phase 9 完成 ASR 核心功能（4 个 Provider）
- **P1（重要）**：Phase 12 实现 VAD 语音唤醒（Silero VAD）
- **P2（可选）**：支持多种 VAD Provider（WebRTC VAD、Web Speech API）

### 6.3 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Silero VAD 依赖较重 | 中 | 提供 Web Speech API 作为轻量级替代 |
| 误触发率高 | 中 | 提供灵敏度预设，允许用户调参 |
| 浏览器兼容性 | 低 | 优先支持 Chrome/Edge，其他浏览器降级 |
| 增加后端复杂度 | 中 | 使用工厂模式，保持代码结构清晰 |

---

**文档结束**
