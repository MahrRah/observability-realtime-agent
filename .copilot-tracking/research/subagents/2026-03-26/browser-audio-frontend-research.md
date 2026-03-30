# Browser Audio Frontend for Voice Agent WebSocket Streaming

## Research Status: Complete

## Research Topics

1. Browser Audio Capture (WebAudio API, getUserMedia, PCM16 at 24kHz, resampling, base64 encoding)
2. WebSocket Communication (Browser WebSocket API, JSON+base64 protocol, bidirectional audio)
3. Frontend Implementation Options (Vanilla JS vs React/Vite vs WebRTC)
4. Audio Playback (decoding base64 PCM16, queuing, interruption handling)
5. UI Design for Voice Agent (minimal UI, PTT vs VAD, visual feedback)

---

## 1. Browser Audio Capture

### 1.1 getUserMedia for Microphone Access

`navigator.mediaDevices.getUserMedia()` prompts for microphone permission and returns a `MediaStream`.

- **Secure context required**: HTTPS or localhost only.
- **Browser support**: Chrome 53+, Edge 12+, Firefox 36+, Safari 11+ — widely available.
- **Audio constraints**: Can request specific sample rates, channels, echo cancellation.

```javascript
const stream = await navigator.mediaDevices.getUserMedia({
  audio: {
    channelCount: 1,          // mono
    sampleRate: 24000,         // request 24kHz (browser may ignore)
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  }
});
```

**Important**: Browsers typically capture at their native sample rate (usually 48kHz on desktop, 44.1kHz on some mobile). The `sampleRate` constraint is a hint and may be ignored. Resampling in code is almost always necessary.

### 1.2 AudioContext and AudioWorkletNode

`AudioContext` is the central object for all WebAudio operations. `AudioWorkletNode` processes audio off the main thread (unlike the deprecated `ScriptProcessorNode`).

**Architecture**:
```
getUserMedia → MediaStreamSource → AudioWorkletNode → (capture PCM data)
```

**Key facts about AudioWorkletProcessor**:
- Receives 128-frame blocks (Float32Array) per `process()` call.
- Runs on a dedicated audio rendering thread (not main thread).
- Communicates with main thread via `MessagePort` (the `port` property).
- Must return `true` from `process()` to stay alive (especially on Chrome).
- Browser support: Chrome 66+, Edge 79+, Firefox 76+, Safari 14.1+.

```javascript
// Main thread
const audioContext = new AudioContext({ sampleRate: 24000 });
// ^ Request 24kHz context — if supported, avoids resampling entirely
await audioContext.audioWorklet.addModule('audio-processor.js');
const source = audioContext.createMediaStreamSource(stream);
const workletNode = new AudioWorkletNode(audioContext, 'audio-capture-processor');
source.connect(workletNode);

// Receive PCM data from worklet
workletNode.port.onmessage = (event) => {
  const pcm16Chunk = event.data; // Int16Array
  const base64 = arrayBufferToBase64(pcm16Chunk.buffer);
  websocket.send(JSON.stringify({
    type: 'input_audio_buffer.append',
    audio: base64
  }));
};
```

### 1.3 AudioWorklet Processor (Separate File)

```javascript
// audio-processor.js — loaded via audioWorklet.addModule()
class AudioCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = [];
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input.length > 0) {
      const channelData = input[0]; // Float32Array, mono channel
      // Convert float32 [-1,1] to Int16 [-32768,32767]
      const pcm16 = new Int16Array(channelData.length);
      for (let i = 0; i < channelData.length; i++) {
        const s = Math.max(-1, Math.min(1, channelData[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }
      this.port.postMessage(pcm16, [pcm16.buffer]);
    }
    return true; // keep processor alive
  }
}

registerProcessor('audio-capture-processor', AudioCaptureProcessor);
```

### 1.4 Resampling from 48kHz to 24kHz

**Option A — Use AudioContext sampleRate parameter (preferred)**:
```javascript
const audioContext = new AudioContext({ sampleRate: 24000 });
```
When the browser supports this, all audio through this context is automatically resampled to 24kHz. Chrome 74+, Edge 79+, Firefox 61+, Safari 14.1+ support `sampleRate` in AudioContext constructor.

**Option B — Manual linear interpolation resampling**:
```javascript
function downsample(inputBuffer, inputSampleRate, outputSampleRate) {
  if (inputSampleRate === outputSampleRate) return inputBuffer;
  const ratio = inputSampleRate / outputSampleRate;
  const newLength = Math.round(inputBuffer.length / ratio);
  const result = new Float32Array(newLength);
  for (let i = 0; i < newLength; i++) {
    const srcIndex = i * ratio;
    const srcIndexFloor = Math.floor(srcIndex);
    const srcIndexCeil = Math.min(srcIndexFloor + 1, inputBuffer.length - 1);
    const frac = srcIndex - srcIndexFloor;
    result[i] = inputBuffer[srcIndexFloor] * (1 - frac) + inputBuffer[srcIndexCeil] * frac;
  }
  return result;
}
```

**Option C — OfflineAudioContext for high-quality resampling**:
```javascript
async function resample(audioData, fromRate, toRate) {
  const offlineCtx = new OfflineAudioContext(1, audioData.length * toRate / fromRate, toRate);
  const buffer = offlineCtx.createBuffer(1, audioData.length, fromRate);
  buffer.copyToChannel(audioData, 0);
  const source = offlineCtx.createBufferSource();
  source.buffer = buffer;
  source.connect(offlineCtx.destination);
  source.start();
  const rendered = await offlineCtx.startRendering();
  return rendered.getChannelData(0);
}
```

**Recommendation**: Option A (AudioContext sampleRate) is simplest and most performant. Fall back to Option B for older browsers.

### 1.5 Base64 Encoding for WebSocket Transport

```javascript
function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function base64ToArrayBuffer(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}
```

---

## 2. WebSocket Communication

### 2.1 Browser WebSocket API

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/audio');

ws.onopen = () => console.log('Connected');
ws.onclose = () => console.log('Disconnected');
ws.onerror = (err) => console.error('WebSocket error:', err);
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  handleServerMessage(msg);
};
```

**Browser support**: Universally supported — Chrome 5+, Edge 12+, Firefox 11+, Safari 5+.

### 2.2 Message Protocol Design

All messages are JSON with a `type` field. Audio payloads are base64-encoded PCM16 24kHz mono.

**Client → Server messages**:
```json
{ "type": "session.start", "config": { "voice": "alloy", "instructions": "..." } }
{ "type": "input_audio_buffer.append", "audio": "<base64 PCM16 24kHz mono>" }
{ "type": "input_audio_buffer.commit" }
{ "type": "response.create" }
{ "type": "response.cancel" }
{ "type": "session.stop" }
```

**Server → Client messages**:
```json
{ "type": "session.created", "session": { ... } }
{ "type": "input_audio_buffer.speech_started" }
{ "type": "input_audio_buffer.speech_stopped" }
{ "type": "response.audio.delta", "delta": "<base64 PCM16 24kHz mono>" }
{ "type": "response.audio.done" }
{ "type": "response.audio_transcript.delta", "delta": "Hello..." }
{ "type": "response.done", "response": { ... } }
{ "type": "error", "error": { "message": "..." } }
```

### 2.3 Audio Chunk Sizing

Azure Realtime API recommends sending audio in ~100ms chunks:
- At 24kHz, 16-bit mono: 100ms = 2400 samples = 4800 bytes
- Base64 overhead: ~6400 chars per chunk
- The AudioWorklet produces 128-frame blocks (~5.3ms at 24kHz), so buffer multiple blocks before sending

**Buffering strategy in worklet or main thread**:
```javascript
// Buffer ~100ms worth of audio before sending
const CHUNK_SIZE = 2400; // samples at 24kHz = 100ms
let audioBuffer = new Int16Array(0);

workletNode.port.onmessage = (event) => {
  const newData = event.data;
  const combined = new Int16Array(audioBuffer.length + newData.length);
  combined.set(audioBuffer, 0);
  combined.set(newData, audioBuffer.length);
  audioBuffer = combined;

  while (audioBuffer.length >= CHUNK_SIZE) {
    const chunk = audioBuffer.slice(0, CHUNK_SIZE);
    audioBuffer = audioBuffer.slice(CHUNK_SIZE);
    const base64 = arrayBufferToBase64(chunk.buffer);
    ws.send(JSON.stringify({
      type: 'input_audio_buffer.append',
      audio: base64
    }));
  }
};
```

---

## 3. Frontend Implementation Options

### Option A: Vanilla HTML/JS (Recommended for Sample Project)

**Pros**:
- Zero build step — open index.html directly or serve from FastAPI static files
- No npm/node dependency
- Fastest to prototype; easiest to read/understand in a sample repo
- FastAPI can serve the HTML via `StaticFiles` or a single endpoint
- Single file or two files (index.html + audio-processor.js)

**Cons**:
- No component model for complex UIs
- Harder to maintain if the UI grows significantly

**Structure**:
```
frontend/
  index.html              # Main UI + inline JS
  audio-processor.js      # AudioWorklet processor (must be separate file)
```

### Option B: React/Vite Lightweight SPA

**Pros**:
- Component-based UI for better organization
- Hot module reload for development
- Larger ecosystem for UI enhancements

**Cons**:
- Requires Node.js, npm, build step
- Heavier dependency footprint for a sample project
- More complex project structure to explain

This is the approach used by [openai/openai-realtime-console](https://github.com/openai/openai-realtime-console) — React + Vite + Express SSR. Uses WebRTC DataChannel for events and RTCPeerConnection for audio.

### Option C: WebRTC Direct Connection

**Pros**:
- Lowest latency (~100ms vs ~200ms for WebSocket)
- Audio is handled natively by the browser — no manual PCM/base64 encoding
- OpenAI and Azure now recommend WebRTC for client-side apps

**Cons**:
- Requires direct client-to-API connection (bypasses the FastAPI middlebox for audio)
- TURN/STUN configuration needed for production
- Harder to add server-side observability/tracing of audio
- API key/token management must be handled carefully in the browser

**How OpenAI Realtime Console does WebRTC**:
```javascript
// 1. Get ephemeral token from backend
const tokenResponse = await fetch('/token');
const EPHEMERAL_KEY = (await tokenResponse.json()).value;

// 2. Create peer connection
const pc = new RTCPeerConnection();

// 3. Play remote audio
const audioEl = document.createElement('audio');
audioEl.autoplay = true;
pc.ontrack = (e) => audioEl.srcObject = e.streams[0];

// 4. Add local microphone track
const ms = await navigator.mediaDevices.getUserMedia({ audio: true });
pc.addTrack(ms.getTracks()[0]);

// 5. Data channel for events
const dc = pc.createDataChannel('oai-events');

// 6. SDP exchange
const offer = await pc.createOffer();
await pc.setLocalDescription(offer);
const sdpResponse = await fetch(`https://api.openai.com/v1/realtime/calls?model=gpt-realtime`, {
  method: 'POST',
  body: offer.sdp,
  headers: { Authorization: `Bearer ${EPHEMERAL_KEY}`, 'Content-Type': 'application/sdp' }
});
await pc.setRemoteDescription({ type: 'answer', sdp: await sdpResponse.text() });
```

### Recommendation for This Sample Project

**Option A (Vanilla HTML/JS)** is best for a sample/demo project because:
1. The focus is on observability of the server-side agent, not frontend engineering.
2. Zero build tooling means contributors can clone and run immediately.
3. FastAPI can serve the static files directly.
4. Audio capture/WebSocket code is educational and easy to follow.
5. The WebSocket relay through FastAPI enables server-side tracing/observability.

If WebRTC direct connection is desired later, it can coexist — the FastAPI backend would only provide token generation, not relay audio.

---

## 4. Audio Playback

### 4.1 Decoding Base64 PCM16 Audio

```javascript
function base64ToInt16Array(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Int16Array(bytes.buffer);
}

function int16ToFloat32(int16Array) {
  const float32 = new Float32Array(int16Array.length);
  for (let i = 0; i < int16Array.length; i++) {
    float32[i] = int16Array[i] / 32768.0;
  }
  return float32;
}
```

### 4.2 Queued Audio Playback with AudioContext

Use `AudioBufferSourceNode` for seamless gapless playback by scheduling each chunk at the correct time:

```javascript
class AudioPlayer {
  constructor(sampleRate = 24000) {
    this.context = new AudioContext({ sampleRate });
    this.nextStartTime = 0;
    this.isPlaying = false;
  }

  play(float32Data) {
    const buffer = this.context.createBuffer(1, float32Data.length, this.context.sampleRate);
    buffer.copyToChannel(float32Data, 0);

    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.context.destination);

    const currentTime = this.context.currentTime;
    const startTime = Math.max(currentTime, this.nextStartTime);
    source.start(startTime);
    this.nextStartTime = startTime + buffer.duration;
    this.isPlaying = true;

    source.onended = () => {
      if (this.nextStartTime <= this.context.currentTime) {
        this.isPlaying = false;
      }
    };
  }

  interrupt() {
    // Stop all scheduled audio by closing and re-creating context
    this.context.close();
    this.context = new AudioContext({ sampleRate: 24000 });
    this.nextStartTime = 0;
    this.isPlaying = false;
  }
}
```

### 4.3 Handling Interruptions (Barge-In)

When server VAD detects the user starts speaking while the agent is responding:
1. Server sends `input_audio_buffer.speech_started`.
2. Client should call `player.interrupt()` to stop playback immediately.
3. Client tracks how much audio was actually played (for `conversation.item.truncate`).
4. Client sends `response.cancel` if response is still in progress.

```javascript
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  switch (msg.type) {
    case 'response.audio.delta':
      const pcm16 = base64ToInt16Array(msg.delta);
      const float32 = int16ToFloat32(pcm16);
      audioPlayer.play(float32);
      break;
    case 'input_audio_buffer.speech_started':
      audioPlayer.interrupt(); // stop agent audio immediately
      break;
    case 'response.done':
      // response complete
      break;
  }
};
```

---

## 5. UI Design for Voice Agent

### 5.1 Minimal UI Components

For a sample project, the UI should be lean:

```
┌──────────────────────────────────┐
│  🎙️ Voice Agent Demo            │
│                                  │
│  [  Connect  ] [  Disconnect  ]  │
│                                  │
│  Status: 🟢 Connected           │
│                                  │
│  ┌─────────────────────────┐    │
│  │  ░░░░░██████░░░░░░░░░░  │    │  ← Audio level meter
│  └─────────────────────────┘    │
│                                  │
│  Agent: "Hello, how can I help?" │
│  You:   "Tell me about..."       │
│                                  │
│  [  Push to Talk  ]              │  ← Optional PTT button
└──────────────────────────────────┘
```

**Essential elements**:
- Connect/Disconnect button
- Connection status indicator (disconnected / connecting / connected / error)
- Audio level visualization (AnalyserNode for real-time levels)
- Transcript display (both user and agent text)

**Optional enhancements**:
- Push-to-talk button (for manual turn detection mode)
- Settings panel (voice selection, system prompt)
- Event log (raw JSON events for debugging)

### 5.2 Push-to-Talk vs Always-On (VAD)

**Server VAD mode** (default, recommended for sample):
- `turn_detection.type: "server_vad"` or `"semantic_vad"`
- User speaks freely; server detects when speech ends
- More natural conversation flow
- Client just streams audio continuously

**Push-to-Talk mode**:
- `turn_detection.type: "none"`
- Client sends `input_audio_buffer.commit` + `response.create` on button release
- Better for noisy environments or precise control
- Simpler client logic (no need to handle speech_started/stopped events)

### 5.3 Audio Level Visualization

```javascript
const analyser = audioContext.createAnalyser();
analyser.fftSize = 256;
source.connect(analyser);

function drawLevel() {
  const dataArray = new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteFrequencyData(dataArray);
  const average = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
  const level = average / 255; // 0..1
  // Update UI bar width or color based on level
  levelBar.style.width = `${level * 100}%`;
  requestAnimationFrame(drawLevel);
}
drawLevel();
```

---

## 6. Azure OpenAI Realtime API — Key Requirements

Source: [Azure docs — Use the GPT Realtime API for speech and audio](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/realtime-audio)

### Audio Format Requirements
- **Format**: PCM 16-bit (`pcm16`)
- **Channels**: Mono (single channel)
- **Sample rate**: 24kHz
- **Transport encoding**: Base64 when using JSON/WebSocket
- **Chunk size**: Recommended ~100ms chunks

### Connection Methods (Azure)
| Method | Use Case | Latency | Best For |
|--------|----------|---------|----------|
| WebRTC | Client-side apps | ~100ms | Web apps, browsers |
| WebSocket | Server-to-server | ~200ms | Backend services, middleware |
| SIP | Telephony | Varies | Call centers, IVR |

For a **browser → FastAPI → Azure** architecture, the FastAPI backend uses **WebSocket** to connect to Azure. The browser connects to FastAPI via WebSocket. This adds one hop but enables full server-side observability.

### Session Configuration
```json
{
  "type": "session.update",
  "session": {
    "voice": "alloy",
    "instructions": "You are a helpful assistant.",
    "input_audio_format": "pcm16",
    "input_audio_transcription": { "model": "whisper-1" },
    "turn_detection": {
      "type": "server_vad",
      "threshold": 0.5,
      "prefix_padding_ms": 300,
      "silence_duration_ms": 200,
      "create_response": true
    },
    "tools": []
  }
}
```

### Supported Models
- `gpt-4o-realtime-preview` (2024-12-17)
- `gpt-4o-mini-realtime-preview` (2024-12-17)
- `gpt-realtime` (2025-08-28)
- `gpt-realtime-mini` (2025-10-06, 2025-12-15)
- `gpt-realtime-1.5` (2026-02-23)

### Session Limits
- Max session duration: 30 minutes
- Max input tokens: 32,000
- Max output tokens: 4,096
- GA endpoint format: `/openai/v1` (no date-based API versions)

---

## 7. Browser Compatibility Summary

| Feature | Chrome | Edge | Firefox | Safari | Notes |
|---------|--------|------|---------|--------|-------|
| getUserMedia | 53+ | 12+ | 36+ | 11+ | HTTPS required |
| AudioContext | 35+ | 12+ | 25+ | 14.1+ | Widely available |
| AudioWorkletNode | 66+ | 79+ | 76+ | 14.1+ | Modern only; no IE |
| AudioContext sampleRate | 74+ | 79+ | 61+ | 14.1+ | Enables 24kHz direct |
| WebSocket | 5+ | 12+ | 11+ | 5+ | Universal |
| WebRTC (RTCPeerConnection) | 56+ | 15+ | 44+ | 11+ | For direct API mode |

**Minimum viable browser**: Chrome 74+ / Edge 79+ / Firefox 76+ / Safari 14.1+ (for AudioWorklet + sampleRate support).

**Fallback considerations**:
- Safari on older iOS may need `webkit` prefix for AudioContext.
- AudioContext often requires a user gesture (click) before it can be created/resumed, due to autoplay policies.
- All browsers require HTTPS (or localhost) for getUserMedia.

---

## 8. Complete End-to-End Pattern (Browser → FastAPI WebSocket)

```
┌─────────────────────┐     WebSocket      ┌──────────────────┐     WebSocket     ┌──────────────────┐
│  Browser            │ ←──────JSON────────→ │  FastAPI Server  │ ←────JSON───────→ │  Azure OpenAI    │
│                     │   base64 PCM16       │                  │   base64 PCM16    │  Realtime API    │
│  getUserMedia       │                      │  /ws/audio       │                   │  /realtime       │
│  AudioWorklet       │                      │  relay + trace   │                   │                  │
│  AudioPlayer        │                      │  OTel spans      │                   │                  │
└─────────────────────┘                      └──────────────────┘                   └──────────────────┘
```

### Minimal File Structure (Vanilla HTML/JS)
```
frontend/
  index.html              # UI + WebSocket + audio capture logic (~200 lines)
  audio-processor.js      # AudioWorklet processor (~25 lines)
```

### Key Startup Sequence
1. User clicks "Connect" → browser resumes AudioContext (user gesture)
2. `getUserMedia({ audio: true })` → get MediaStream
3. `new WebSocket('ws://localhost:8000/ws/audio')` → connect to FastAPI
4. AudioWorklet captures PCM16, sends base64 chunks over WebSocket
5. FastAPI relays to Azure OpenAI WebSocket
6. Azure response audio deltas relayed back → browser decodes and plays via AudioBufferSourceNode
7. Server VAD events control barge-in behavior

---

## 9. References

- [MDN Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API) — Core audio processing documentation
- [MDN AudioWorkletNode](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorkletNode) — Modern audio processing off main thread
- [MDN Using AudioWorklet](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API/Using_AudioWorklet) — Step-by-step AudioWorklet guide
- [MDN getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia) — Microphone access API
- [MDN WebSocket](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket) — Browser WebSocket client API
- [Azure OpenAI Realtime API](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/realtime-audio) — Official Azure documentation
- [openai/openai-realtime-console](https://github.com/openai/openai-realtime-console) — OpenAI's WebRTC-based React reference implementation
- [Azure-Samples/aisearch-openai-rag-audio](https://github.com/Azure-Samples/aisearch-openai-rag-audio) — RAG + voice interface sample

---

## 10. Follow-On Questions (Discovered During Research)

1. Should the sample support both WebSocket relay (for observability) and WebRTC direct (for lowest latency) modes?
2. What OpenTelemetry attributes should be emitted for audio streaming spans (audio_duration_ms, chunk_count, etc.)?
3. Should the frontend include a recording/export feature for debugging audio quality issues?
4. Is there a preference for a specific Azure OpenAI model version (gpt-realtime vs gpt-realtime-1.5)?
