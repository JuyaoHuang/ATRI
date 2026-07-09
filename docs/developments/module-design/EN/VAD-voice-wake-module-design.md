# VAD Voice Wake Word Module Design Document

> Legacy design note:
> Prefer the current implementation docs under [../../modules/vad/README.zh-CN.md](../../modules/vad/README.zh-CN.md).
> This file is kept as historical design source and migration reference, not as the authoritative entry point for the current implementation.

**Version**: v1.0  
**Created**: 2026-04-23  
**Status**: Pending implementation (Phase 12 or standalone Phase)

---

## 1. Overview

### 1.1 What is VAD

**VAD (Voice Activity Detection)** is a technique for detecting the presence of human speech in an audio stream. In voice interaction systems, VAD is used for:

- **Wake Word Detection**: Detects when the user starts speaking, automatically triggering recording
- **Voice Endpoint Detection**: Detects when the user stops speaking, automatically ending recording
- **Reducing false triggers**: Filters environmental noise, only triggers when actual human speech is present

### 1.2 Why VAD is Needed

In the emotion-robot project, VAD can improve the user experience:

- **Hands-free interaction**: Users don't need to click a record button, just speak directly
- **Automatic endpoint detection**: Recording stops automatically after the user finishes speaking, no need to manually click stop
- **Reduced latency**: Recording starts immediately upon detecting speech, reducing wait time
- **Enhanced immersion**: A more natural conversation experience

---

## 2. Open-LLM-VTuber's VAD Implementation

### 2.1 Technology Selection

OLV uses **Silero VAD** as the VAD engine:

- **Model**: `silero-vad` (PyTorch model)
- **Advantages**:
  - Lightweight (~1MB)
  - High accuracy (low false positive rate)
  - Multi-language support
  - Fully offline operation
  - CPU-friendly
- **Disadvantages**:
  - Requires Python environment
  - Requires PyTorch dependency

### 2.2 Core Configuration Parameters

OLV's VAD configuration (`conf.yaml`):

```yaml
vad_config:
  vad_model: 'silero_vad'
  
  silero_vad:
    orig_sr: 16000           # Original audio sample rate (Hz)
    target_sr: 16000         # Target audio sample rate (Hz)
    prob_threshold: 0.4      # Speech probability threshold (0-1)
    db_threshold: 60         # Decibel threshold (dB)
    required_hits: 3         # Consecutive hit count (3 * 0.032s = 0.1s)
    required_misses: 24      # Consecutive miss count (24 * 0.032s = 0.8s)
    smoothing_window: 5      # Smoothing window size
```

**Parameter descriptions**:

| Parameter | Default | Description |
|------|--------|------|
| `orig_sr` | 16000 | Original audio sample rate, typically 16kHz |
| `target_sr` | 16000 | Target audio sample rate, matched to ASR model |
| `prob_threshold` | 0.4 | Speech probability threshold, higher means stricter (0.3-0.5 recommended) |
| `db_threshold` | 60 | Decibel threshold, filters low-volume noise (50-70 recommended) |
| `required_hits` | 3 | Consecutive speech detection count, prevents false triggers |
| `required_misses` | 24 | Consecutive silence detection count, confirms speech has ended |
| `smoothing_window` | 5 | Smoothing window, reduces jitter |

### 2.3 Working Principle

**State machine design**:

```
IDLE
  | Speech detected (3 consecutive hits)
ACTIVE
  | Silence detected (24 consecutive misses)
INACTIVE
  | Speech detected again (3 consecutive hits)
ACTIVE
  | Sustained silence (24 consecutive misses)
IDLE -> Output complete speech segment
```

**Time calculations**:
- Each audio chunk: 512 samples / 16000 Hz = 0.032 seconds
- Trigger delay: 3 * 0.032s = 0.1 seconds
- End delay: 24 * 0.032s = 0.8 seconds

### 2.4 Core Code Structure

**Interface definition** (`vad_interface.py`):

```python
class VADInterface(ABC):
    @abstractmethod
    def detect_speech(self, audio_data: bytes):
        """Detect voice activity in audio"""
        pass
```

**Factory pattern** (`vad_factory.py`):

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

**Silero VAD implementation** (`silero.py`):

```python
class VADEngine(VADInterface):
    def __init__(self, orig_sr=16000, target_sr=16000, 
                 prob_threshold=0.4, db_threshold=60,
                 required_hits=3, required_misses=24,
                 smoothing_window=5):
        self.config = SileroVADConfig(...)
        self.model = load_silero_vad()  # Load Silero VAD model
        self.state = StateMachine(self.config)
        
    def detect_speech(self, audio_data: list[float]):
        """Detect voice activity, return audio segments containing human speech"""
        for chunk in audio_chunks:
            speech_prob = self.model(chunk, self.config.target_sr)
            for audio_bytes in self.state.get_result(speech_prob, chunk):
                yield audio_bytes
```

---

## 3. Reusing VAD in emotion-robot

### 3.1 Reuse Strategy

**Option A: Fully reuse OLV's Silero VAD implementation (Recommended)**

**Advantages**:
- Mature and stable, already validated in OLV
- Well-configured, parameters are adjustable
- Fully offline, no cloud services needed
- Clean code structure, easy to integrate

**Disadvantages**:
- Requires Python backend support
- Requires installing `silero-vad` and `torch` dependencies
- Increases backend complexity

**Implementation steps**:

1. **Backend integration** (`atri/src/vad/`):
   ```
   atri/src/vad/
   ├── __init__.py
   ├── interface.py          # VAD interface definition
   ├── factory.py            # VAD factory class
   ├── exceptions.py         # VAD exceptions
   └── providers/
       ├── __init__.py
       └── silero_vad.py     # Silero VAD implementation (reused from OLV)
   ```

2. **Configuration management** (`atri/src/config/vad.py`):
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
       enabled: bool = False  # Disabled by default
       provider: str = "silero_vad"
       silero_vad: SileroVADConfig = SileroVADConfig()
   ```

3. **API endpoint** (`atri/src/api/vad.py`):
   ```python
   @router.post("/vad/detect")
   async def detect_voice_activity(audio: UploadFile):
       """Detect voice activity in audio"""
       vad_engine = VADFactory.get_vad_engine("silero_vad", **config)
       audio_data = await audio.read()
       speech_segments = vad_engine.detect_speech(audio_data)
       return {"segments": speech_segments}
   ```

4. **Frontend integration** (`atri-webui/src/composables/useVAD.ts`):
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
           // Speech detected, trigger recording
           emit('voice-detected', response.segments)
         }
       }
     }
   }
   ```

5. **Dependency installation** (`atri/pyproject.toml`):
   ```toml
   [project.optional-dependencies]
   vad = [
       "silero-vad>=5.1",
       "torch>=2.0.0",
   ]
   ```

### 3.2 Alternative Options

**Option B: Use browser-side Web Speech API**

**Advantages**:
- Zero cost, natively supported by browsers
- No backend service needed
- Simple to implement

**Disadvantages**:
- Limited functionality, no fine-grained parameter tuning
- Browser compatibility issues (Chrome/Edge have better support)
- Requires network connection (for some browsers)

**Implementation example**:

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

## 4. Implementation Recommendations

### 4.1 Phase Planning Recommendation

**Recommendation: Implement as standalone Phase 12**

- **Phase 12: VAD Voice Wake Word**
  - Backend: Silero VAD integration
  - Frontend: Automatic recording trigger
  - Settings page: VAD parameter configuration
  - Estimated time: 3-4 days

**Reasons**:
1. Phase 9 (ASR) already includes 4 providers, which is a significant workload
2. VAD is an independent feature that doesn't affect core ASR functionality
3. Can decide whether VAD is needed based on user feedback
4. Reduces the complexity and risk of Phase 9

### 4.2 Configuration Recommendations

**Default configuration** (suitable for most scenarios):

```yaml
vad_config:
  enabled: false  # Disabled by default, user manually enables
  provider: 'silero_vad'
  
  silero_vad:
    orig_sr: 16000
    target_sr: 16000
    prob_threshold: 0.4      # Medium sensitivity
    db_threshold: 60         # Filters low-volume noise
    required_hits: 3         # 0.1s trigger delay
    required_misses: 24      # 0.8s end delay
    smoothing_window: 5
```

**High sensitivity configuration** (quiet environment):

```yaml
silero_vad:
  prob_threshold: 0.3      # Lower threshold
  db_threshold: 50         # Lower decibels
  required_hits: 2         # Faster trigger
  required_misses: 18      # Faster end
```

**Low sensitivity configuration** (noisy environment):

```yaml
silero_vad:
  prob_threshold: 0.5      # Higher threshold
  db_threshold: 70         # Higher decibels
  required_hits: 5         # Slower trigger
  required_misses: 30      # Slower end
```

### 4.3 Frontend UI Recommendations

**Settings page** (`atri-webui/src/pages/settings/modules/hearing.vue`):

```vue
<template>
  <div class="vad-settings">
    <h3>Voice Wake Word (VAD)</h3>
    
    <!-- Toggle -->
    <Switch v-model="vadEnabled" label="Enable Voice Wake Word" />
    
    <!-- Sensitivity presets -->
    <Select v-model="vadPreset" label="Sensitivity Preset">
      <option value="low">Low (noisy environment)</option>
      <option value="medium">Medium (recommended)</option>
      <option value="high">High (quiet environment)</option>
      <option value="custom">Custom</option>
    </Select>
    
    <!-- Advanced parameters (only shown in custom mode) -->
    <div v-if="vadPreset === 'custom'">
      <Slider v-model="probThreshold" label="Speech Probability Threshold" :min="0.2" :max="0.6" :step="0.05" />
      <Slider v-model="dbThreshold" label="Decibel Threshold" :min="40" :max="80" :step="5" />
      <Slider v-model="requiredHits" label="Trigger Delay" :min="1" :max="10" :step="1" />
      <Slider v-model="requiredMisses" label="End Delay" :min="10" :max="40" :step="2" />
    </div>
    
    <!-- Test button -->
    <Button @click="testVAD">Test VAD</Button>
  </div>
</template>
```

---

## 5. Reference Resources

### 5.1 Silero VAD

- **GitHub**: https://github.com/snakers4/silero-vad
- **Documentation**: https://github.com/snakers4/silero-vad/wiki
- **Model downloads**: https://github.com/snakers4/silero-vad/releases

### 5.2 Open-LLM-VTuber Implementation

- **Repository**: https://github.com/t41372/Open-LLM-VTuber
- **VAD module**: `src/open_llm_vtuber/vad/`
- **Configuration file**: `conf.yaml` (`vad_config` section)

### 5.3 Related Technologies

- **WebRTC VAD**: https://webrtc.org/
- **PyAudio**: https://people.csail.mit.edu/hubert/pyaudio/
- **Web Speech API**: https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API

---

## 6. Summary

### 6.1 Key Points

1. **VAD is the core technology for voice wake words**, enabling hands-free interaction
2. **OLV uses Silero VAD**, which is mature, stable, and fully offline
3. **Recommended to implement as standalone Phase 12**, not affecting Phase 9's core ASR functionality
4. **VAD is disabled by default**, users can manually enable it in the settings page

### 6.2 Implementation Priority

- **P0 (Required)**: Phase 9 completes core ASR functionality (4 providers)
- **P1 (Important)**: Phase 12 implements VAD voice wake word (Silero VAD)
- **P2 (Optional)**: Support multiple VAD providers (WebRTC VAD, Web Speech API)

### 6.3 Risk Assessment

| Risk | Impact | Mitigation |
|------|------|----------|
| Silero VAD has heavy dependencies | Medium | Provide Web Speech API as a lightweight alternative |
| High false trigger rate | Medium | Provide sensitivity presets, allow users to adjust parameters |
| Browser compatibility | Low | Prioritize Chrome/Edge support, degrade gracefully for other browsers |
| Increased backend complexity | Medium | Use factory pattern to maintain clean code structure |

---

**End of Document**
