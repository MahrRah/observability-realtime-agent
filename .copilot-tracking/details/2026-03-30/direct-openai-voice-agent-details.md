<!-- markdownlint-disable-file -->
# Implementation Details: Direct OpenAI Voice Agent (Stage 1)

## Context Reference

Sources:
* .copilot-tracking/research/2026-03-26/voice-agent-sample-research.md — full project design
* .copilot-tracking/research/subagents/2026-03-26/openai-agents-sdk-voice-research.md — SDK API
* .copilot-tracking/research/subagents/2026-03-26/fastapi-websocket-voice-server-research.md — server patterns
* .copilot-tracking/research/subagents/2026-03-26/browser-audio-frontend-research.md — frontend patterns
* .copilot-tracking/research/subagents/2026-03-26/bicep-azure-openai-realtime-research.md — IaC templates

Stage 2 reference:
* .copilot-tracking/plans/2026-03-26/orchestration-abstraction-plan.instructions.md — abstraction plan
* .copilot-tracking/details/2026-03-26/orchestration-abstraction-details.md — VoiceEvent, protocols, adapters

## Implementation Phase 1: Project Scaffold and Config

<!-- parallelizable: true -->

### Step 1.1: Create `pyproject.toml`

```toml
[project]
name = "observability-realtime-agent"
version = "0.1.0"
description = "Real-time voice agent sample with OpenAI Agents SDK and Azure OpenAI"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "websockets>=13.0",
    "openai-agents[voice]>=0.13.0",
    "pydantic-settings>=2.0.0",
]

[tool.setuptools.packages.find]
where = ["src"]

[project.optional-dependencies]
dev = [
    "ruff>=0.8.0",
]
```

Files:
* pyproject.toml - New file

Success criteria:
* `pip install -e .` installs all dependencies
* `openai-agents[voice]` pulls in realtime extras

Dependencies:
* None

### Step 1.2: Create `src/app/__init__.py`

Empty file to make `app` a package.

```python
```

Files:
* src/app/__init__.py - New file (empty)

### Step 1.3: Create `src/app/config.py`

Pydantic settings loading from `.env`:

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    azure_openai_endpoint: str = Field(
        description="Azure OpenAI resource endpoint (e.g., https://myresource.openai.azure.com)",
    )
    azure_openai_api_key: str = Field(description="Azure OpenAI API key")
    azure_openai_deployment: str = Field(
        default="gpt-4o-realtime-preview",
        description="Azure OpenAI deployment name for Realtime API",
    )
    agent_instructions: str = Field(
        default="You are a helpful voice assistant. Keep responses concise.",
        description="System instructions for the agent",
    )
    voice: str = Field(default="ash", description="TTS voice name")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    @property
    def azure_realtime_url(self) -> str:
        base = self.azure_openai_endpoint.replace("https://", "")
        return f"wss://{base}/openai/v1/realtime?model={self.azure_openai_deployment}"

    @property
    def azure_headers(self) -> dict[str, str]:
        return {"api-key": self.azure_openai_api_key}
```

Files:
* src/app/config.py - New file

Success criteria:
* `Settings()` loads from `.env`
* `azure_realtime_url` constructs valid WSS URL
* `azure_headers` returns API key header

Dependencies:
* None

### Step 1.4: Create `.env.example`

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_DEPLOYMENT=gpt-4o-realtime-preview
AGENT_INSTRUCTIONS=You are a helpful voice assistant. Keep responses concise.
VOICE=ash
HOST=0.0.0.0
PORT=8000
```

Files:
* .env.example - New file

### Step 1.5: Create `.gitignore`

```gitignore
__pycache__/
*.pyc
.env
.venv/
*.egg-info/
dist/
build/
.ruff_cache/
```

Files:
* .gitignore - New file

## Implementation Phase 2: Agent and Server

<!-- parallelizable: false -->

### Step 2.1: Create `src/app/agent.py`

Define the RealtimeAgent with example tools. This file is the primary refactor target for Stage 2 — the agent definition stays, but session management moves to the adapter.

```python
from agents import function_tool
from agents.realtime import RealtimeAgent


@function_tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"Sunny, 72°F in {city}"


def create_agent(instructions: str, voice: str) -> RealtimeAgent:
    """Create a RealtimeAgent with the given instructions and tools."""
    return RealtimeAgent(
        name="Assistant",
        instructions=instructions,
        voice=voice,
        tools=[get_weather],
    )
```

**Stage 2 note:** When adding the abstraction, `create_agent` stays unchanged. The factory function in `voice/factory.py` will call `create_agent()` and pass the result to `OpenAIAgentsVoiceSession`.

Files:
* src/app/agent.py - New file

Success criteria:
* `create_agent()` returns a `RealtimeAgent` with tools attached
* `get_weather` is a working `@function_tool`

Dependencies:
* `openai-agents[voice]>=0.13.0`

### Step 2.2: Create `src/app/main.py`

FastAPI application with:
1. WebSocket endpoint relaying browser audio ↔ Azure OpenAI Realtime API
2. Static file serving for the browser frontend
3. Logging for observability groundwork

```python
from __future__ import annotations

import asyncio
import base64
import json
import logging
import struct
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from agents.realtime import RealtimeRunner, RealtimeSession

from app.agent import create_agent
from app.config import Settings
from app.realtime_listener import create_default_listeners

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Voice Agent")


@lru_cache
def get_settings() -> Settings:
    return Settings()


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    settings = get_settings()

    agent = create_agent(
        instructions=settings.agent_instructions,
        voice=settings.voice,
    )
    runner = RealtimeRunner(agent)

    model_config: dict[str, Any] = {
        "url": settings.azure_realtime_url,
        "headers": settings.azure_headers,
    }

    session_ctx = await runner.run(model_config=model_config)
    session: RealtimeSession = await session_ctx.__aenter__()
    logger.info("Session %s: connected to Azure OpenAI", session_id)

    listeners = create_default_listeners()

    async def forward_events() -> None:
        """Azure → Browser: forward agent events to the browser WebSocket."""
        async for event in session:
            try:
                # Notify registered listeners
                for listener in listeners:
                    await listener.on_event(event)
                await _handle_event(websocket, event, session_id)
            except Exception:
                logger.exception("Session %s: error handling event", session_id)

    task = asyncio.create_task(forward_events())
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "audio":
                audio_data: list[int] = msg["data"]
                audio_bytes = struct.pack(f"{len(audio_data)}h", *audio_data)
                await session.send_audio(audio_bytes)
    except WebSocketDisconnect:
        logger.info("Session %s: browser disconnected", session_id)
    finally:
        task.cancel()
        await session_ctx.__aexit__(None, None, None)
        logger.info("Session %s: session closed", session_id)


async def _handle_event(
    websocket: WebSocket, event: Any, session_id: str
) -> None:
    """Map a RealtimeSession event to a browser-bound JSON message."""
    from agents.realtime import (
        RealtimeAudio,
        RealtimeAudioEnd,
        RealtimeAudioInterrupted,
        RealtimeAgentStartEvent,
        RealtimeAgentEndEvent,
        RealtimeError,
        RealtimeRawModelEvent,
    )

    match event:
        case RealtimeAudio():
            audio_b64 = base64.b64encode(event.audio.data).decode()
            await websocket.send_text(
                json.dumps({"type": "response.audio.delta", "delta": audio_b64})
            )
        case RealtimeAudioEnd():
            await websocket.send_text(json.dumps({"type": "response.audio.done"}))
            logger.info("Session %s: audio output completed", session_id)
        case RealtimeAudioInterrupted():
            await websocket.send_text(
                json.dumps({"type": "input_audio_buffer.speech_started"})
            )
            logger.info("Session %s: user interrupted", session_id)
        case RealtimeAgentStartEvent():
            logger.info(
                "Session %s: agent started: %s", session_id, event.agent.name
            )
        case RealtimeAgentEndEvent():
            logger.info(
                "Session %s: agent ended: %s", session_id, event.agent.name
            )
        case RealtimeError():
            await websocket.send_text(
                json.dumps({"type": "error", "error": str(event.error)})
            )
            logger.error("Session %s: error: %s", session_id, event.error)
        case RealtimeRawModelEvent():
            raw = event.data if hasattr(event, "data") else {}
            event_type = raw.get("type", "") if isinstance(raw, dict) else ""
            if event_type == "response.audio_transcript.delta":
                await websocket.send_text(
                    json.dumps({
                        "type": "response.audio_transcript.delta",
                        "delta": raw.get("delta", ""),
                    })
                )
            elif event_type == "response.audio_transcript.done":
                await websocket.send_text(
                    json.dumps({
                        "type": "response.audio_transcript.done",
                        "transcript": raw.get("transcript", ""),
                    })
                )
                logger.info(
                    "Session %s: transcript: %s",
                    session_id,
                    raw.get("transcript", "")[:80],
                )
            elif event_type == "conversation.item.input_audio_transcription.completed":
                await websocket.send_text(
                    json.dumps({
                        "type": "conversation.item.input_audio_transcription.completed",
                        "transcript": raw.get("transcript", ""),
                    })
                )
                logger.info(
                    "Session %s: user said: %s",
                    session_id,
                    raw.get("transcript", "")[:80],
                )
            elif event_type == "response.done":
                await websocket.send_text(json.dumps({"type": "response.done"}))
            elif event_type == "session.created":
                logger.info("Session %s: Azure session created", session_id)
            elif event_type == "error":
                error_msg = raw.get("error", {}).get("message", str(raw))
                await websocket.send_text(
                    json.dumps({"type": "error", "error": error_msg})
                )
                logger.error("Session %s: raw error: %s", session_id, error_msg)
        case _:
            logger.debug("Session %s: unhandled event type: %s", session_id, type(event).__name__)


# Serve static files (browser frontend) — must be last
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=True)
```

**Stage 2 note:** When adding the abstraction, this file replaces the `RealtimeRunner`/`RealtimeSession` usage with `create_voice_session()` from the factory. The `_handle_event` function becomes a `VoiceEventListener`. The event loop (`async for event in session`) becomes `async for event in session.events()`.

Files:
* src/app/main.py - New file

Success criteria:
* `uvicorn app.main:app` starts without import errors
* WebSocket at `/ws/{session_id}` accepts connections
* Forward events: audio, transcripts, interruptions, errors
* Cleanup on disconnect (session close, task cancel)
* Logging on all significant events
* `RealtimeEventListener` registered and receiving events

Context references:
* .copilot-tracking/research/subagents/2026-03-26/fastapi-websocket-voice-server-research.md — RealtimeWebSocketManager pattern
* .copilot-tracking/research/subagents/2026-03-26/openai-agents-sdk-voice-research.md — event types and iteration

Dependencies:
* Step 1.3 (config.py), Step 2.1 (agent.py), Step 2.3 (realtime_listener.py)

### Step 2.3: Create `src/app/realtime_listener.py`

A lightweight event listener that hooks into the realtime session event stream. Prints errors and `conversation.item.created` events. This is a precursor to the full `VoiceEventListener` protocol in Stage 2 — same concept, but directly coupled to the OpenAI SDK event types.

```python
from __future__ import annotations

import json
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class RealtimeEventListener(Protocol):
    """Simple listener protocol for realtime session events.

    Stage 2 replaces this with VoiceEventListener + VoiceEvent.
    """

    async def on_event(self, event: Any) -> None: ...


class LoggingRealtimeListener:
    """Logs errors and conversation item events from the realtime session."""

    async def on_event(self, event: Any) -> None:
        from agents.realtime import RealtimeError, RealtimeRawModelEvent

        match event:
            case RealtimeError():
                logger.error("[RealtimeListener] Error: %s", event.error)
            case RealtimeRawModelEvent():
                raw = event.data if hasattr(event, "data") else {}
                event_type = raw.get("type", "") if isinstance(raw, dict) else ""
                match event_type:
                    case "conversation.item.created":
                        item = raw.get("item", {})
                        role = item.get("role", "unknown")
                        item_type = item.get("type", "unknown")
                        item_id = item.get("id", "")
                        logger.info(
                            "[RealtimeListener] Conversation item created: "
                            "id=%s type=%s role=%s",
                            item_id,
                            item_type,
                            role,
                        )
                    case "error":
                        error_msg = raw.get("error", {}).get("message", str(raw))
                        logger.error(
                            "[RealtimeListener] Raw error: %s", error_msg
                        )


def create_default_listeners() -> list[RealtimeEventListener]:
    """Create the default set of event listeners."""
    return [LoggingRealtimeListener()]
```

**Design decisions:**

1. **`RealtimeEventListener` protocol** — a minimal `Protocol` with a single `on_event(Any)` method. This is the Stage 1 version of the Stage 2 `VoiceEventListener`. The protocol exists so `main.py` doesn't need to know the concrete listener class.
2. **Deferred imports** — `from agents.realtime import ...` inside `on_event` keeps the module importable even if the SDK layout changes.
3. **`conversation.item.created`** — arrives as `RealtimeRawModelEvent` with `data.type == "conversation.item.created"`. The payload includes `item.id`, `item.type` ("message", "function_call", "function_call_output"), and `item.role` ("user", "assistant", "system").
4. **`create_default_listeners()`** — factory function used by `main.py` so additional listeners can be added without modifying the server.

**Stage 2 note:** This file is replaced entirely by `src/app/voice/listeners/logging_listener.py` which uses `VoiceEvent` and `VoiceEventType` instead of raw SDK events.

Files:
* src/app/realtime_listener.py - New file

Success criteria:
* `LoggingRealtimeListener` satisfies `RealtimeEventListener` protocol
* Errors logged at ERROR level
* Conversation item creation logged at INFO level with item id, type, and role
* `create_default_listeners()` returns a list containing the logging listener

Dependencies:
* `openai-agents[voice]>=0.13.0`

## Implementation Phase 3: Browser Frontend

<!-- parallelizable: true -->

### Step 3.1: Create `static/audio-processor.js`

AudioWorklet processor that converts Float32 audio from the microphone to Int16 (PCM16) and posts it to the main thread. Runs off the main thread for zero-jank audio.

```javascript
// audio-processor.js — AudioWorklet processor for PCM16 capture
class AudioCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Int16Array(0);
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input.length > 0) {
      const channelData = input[0]; // Float32Array, mono
      const pcm16 = new Int16Array(channelData.length);
      for (let i = 0; i < channelData.length; i++) {
        const s = Math.max(-1, Math.min(1, channelData[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }

      // Buffer chunks to ~100ms (2400 samples at 24kHz)
      const combined = new Int16Array(this._buffer.length + pcm16.length);
      combined.set(this._buffer, 0);
      combined.set(pcm16, this._buffer.length);
      this._buffer = combined;

      while (this._buffer.length >= 2400) {
        const chunk = this._buffer.slice(0, 2400);
        this._buffer = this._buffer.slice(2400);
        this.port.postMessage(chunk, [chunk.buffer]);
      }
    }
    return true;
  }
}

registerProcessor("audio-capture-processor", AudioCaptureProcessor);
```

Files:
* static/audio-processor.js - New file

Success criteria:
* Registered as `"audio-capture-processor"`
* Buffers to ~100ms chunks before posting
* Converts Float32 → Int16 correctly

Dependencies:
* None (standalone AudioWorklet)

### Step 3.2: Create `static/index.html`

Complete browser UI with:
1. Connect/Disconnect controls
2. Audio capture via AudioWorklet → WebSocket
3. Audio playback via queued AudioBufferSourceNode
4. Interruption handling (stop playback on speech_started)
5. Transcript display (agent + user)

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Voice Agent</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: system-ui, -apple-system, sans-serif;
      max-width: 600px;
      margin: 2rem auto;
      padding: 0 1rem;
      color: #1a1a1a;
    }
    h1 { font-size: 1.5rem; margin-bottom: 1rem; }
    .controls { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
    button {
      padding: 0.5rem 1rem;
      border: 1px solid #ccc;
      border-radius: 4px;
      background: #fff;
      cursor: pointer;
      font-size: 0.9rem;
    }
    button:hover { background: #f0f0f0; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    button.active { background: #e74c3c; color: #fff; border-color: #e74c3c; }
    #status {
      padding: 0.5rem;
      margin-bottom: 1rem;
      border-radius: 4px;
      font-size: 0.85rem;
      background: #f5f5f5;
    }
    #status.connected { background: #d4edda; color: #155724; }
    #status.error { background: #f8d7da; color: #721c24; }
    #transcript {
      border: 1px solid #ddd;
      border-radius: 4px;
      padding: 1rem;
      min-height: 300px;
      max-height: 500px;
      overflow-y: auto;
      font-size: 0.9rem;
      line-height: 1.6;
    }
    .msg { margin-bottom: 0.5rem; }
    .msg-user { color: #2c3e50; }
    .msg-user::before { content: "You: "; font-weight: 600; }
    .msg-agent { color: #2980b9; }
    .msg-agent::before { content: "Agent: "; font-weight: 600; }
    .msg-system { color: #7f8c8d; font-style: italic; font-size: 0.8rem; }
  </style>
</head>
<body>
  <h1>Voice Agent</h1>

  <div class="controls">
    <button id="connectBtn" onclick="connect()">Connect</button>
    <button id="disconnectBtn" onclick="disconnect()" disabled>Disconnect</button>
  </div>

  <div id="status">Not connected</div>
  <div id="transcript"></div>

  <script>
    // --- State ---
    let ws = null;
    let audioContext = null;
    let workletNode = null;
    let mediaStream = null;
    let player = null;
    let currentAgentTranscript = "";

    // --- DOM refs ---
    const statusEl = document.getElementById("status");
    const transcriptEl = document.getElementById("transcript");
    const connectBtn = document.getElementById("connectBtn");
    const disconnectBtn = document.getElementById("disconnectBtn");

    // --- Audio Player ---
    class AudioPlayer {
      constructor(sampleRate = 24000) {
        this.sampleRate = sampleRate;
        this.context = new AudioContext({ sampleRate });
        this.nextStartTime = 0;
      }

      play(float32Data) {
        const buffer = this.context.createBuffer(1, float32Data.length, this.sampleRate);
        buffer.copyToChannel(float32Data, 0);
        const source = this.context.createBufferSource();
        source.buffer = buffer;
        source.connect(this.context.destination);
        const now = this.context.currentTime;
        const startTime = Math.max(now, this.nextStartTime);
        source.start(startTime);
        this.nextStartTime = startTime + buffer.duration;
      }

      interrupt() {
        this.context.close();
        this.context = new AudioContext({ sampleRate: this.sampleRate });
        this.nextStartTime = 0;
      }

      close() {
        this.context.close();
      }
    }

    // --- Base64 helpers ---
    function base64ToInt16Array(b64) {
      const binary = atob(b64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      return new Int16Array(bytes.buffer);
    }

    function int16ToFloat32(int16) {
      const f32 = new Float32Array(int16.length);
      for (let i = 0; i < int16.length; i++) f32[i] = int16[i] / 32768.0;
      return f32;
    }

    // --- Transcript helpers ---
    function addTranscript(role, text) {
      const div = document.createElement("div");
      div.className = `msg msg-${role}`;
      div.textContent = text;
      transcriptEl.appendChild(div);
      transcriptEl.scrollTop = transcriptEl.scrollHeight;
    }

    function addSystem(text) {
      const div = document.createElement("div");
      div.className = "msg msg-system";
      div.textContent = text;
      transcriptEl.appendChild(div);
      transcriptEl.scrollTop = transcriptEl.scrollHeight;
    }

    // --- Connect ---
    async function connect() {
      try {
        setStatus("Requesting microphone...");

        mediaStream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            sampleRate: 24000,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });

        audioContext = new AudioContext({ sampleRate: 24000 });
        await audioContext.audioWorklet.addModule("audio-processor.js");

        const source = audioContext.createMediaStreamSource(mediaStream);
        workletNode = new AudioWorkletNode(audioContext, "audio-capture-processor");
        source.connect(workletNode);

        // WebSocket
        const sessionId = crypto.randomUUID();
        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        ws = new WebSocket(`${proto}//${location.host}/ws/${sessionId}`);

        ws.onopen = () => {
          setStatus("Connected", "connected");
          connectBtn.disabled = true;
          disconnectBtn.disabled = false;
          addSystem("Connected to voice agent");
        };

        ws.onclose = () => {
          setStatus("Disconnected");
          connectBtn.disabled = false;
          disconnectBtn.disabled = true;
        };

        ws.onerror = () => {
          setStatus("Connection error", "error");
        };

        ws.onmessage = (e) => {
          const msg = JSON.parse(e.data);
          handleServerMessage(msg);
        };

        // Send audio chunks to server
        workletNode.port.onmessage = (e) => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            const pcm16 = e.data; // Int16Array
            ws.send(JSON.stringify({ type: "audio", data: Array.from(pcm16) }));
          }
        };

        player = new AudioPlayer(24000);

      } catch (err) {
        setStatus(`Error: ${err.message}`, "error");
        console.error(err);
      }
    }

    // --- Disconnect ---
    function disconnect() {
      if (ws) { ws.close(); ws = null; }
      if (workletNode) { workletNode.disconnect(); workletNode = null; }
      if (audioContext) { audioContext.close(); audioContext = null; }
      if (mediaStream) { mediaStream.getTracks().forEach((t) => t.stop()); mediaStream = null; }
      if (player) { player.close(); player = null; }
      currentAgentTranscript = "";
      setStatus("Disconnected");
      connectBtn.disabled = false;
      disconnectBtn.disabled = true;
    }

    // --- Handle server messages ---
    function handleServerMessage(msg) {
      switch (msg.type) {
        case "response.audio.delta":
          if (player && msg.delta) {
            const pcm16 = base64ToInt16Array(msg.delta);
            const float32 = int16ToFloat32(pcm16);
            player.play(float32);
          }
          break;

        case "response.audio.done":
          // Audio stream complete for this response
          break;

        case "input_audio_buffer.speech_started":
          // User is speaking — interrupt agent playback
          if (player) player.interrupt();
          if (currentAgentTranscript) {
            addTranscript("agent", currentAgentTranscript);
            currentAgentTranscript = "";
          }
          break;

        case "response.audio_transcript.delta":
          currentAgentTranscript += msg.delta || "";
          break;

        case "response.audio_transcript.done":
          currentAgentTranscript = msg.transcript || currentAgentTranscript;
          break;

        case "response.done":
          if (currentAgentTranscript) {
            addTranscript("agent", currentAgentTranscript);
            currentAgentTranscript = "";
          }
          break;

        case "conversation.item.input_audio_transcription.completed":
          if (msg.transcript) addTranscript("user", msg.transcript);
          break;

        case "error":
          addSystem(`Error: ${msg.error}`);
          break;
      }
    }

    // --- Status ---
    function setStatus(text, cls) {
      statusEl.textContent = text;
      statusEl.className = cls || "";
    }
  </script>
</body>
</html>
```

**Design decisions:**

1. **No build step** — single HTML file with inline JS. Ideal for a sample project.
2. **Audio chunks as `Int16Array` serialized to JSON `data: [...]`** — matches the server-side `struct.pack` pattern from the reference implementation. Base64 would be more bandwidth-efficient but this keeps the code clear.
3. **Agent transcript accumulates deltas** — displayed as a complete message on `response.done` or when the user interrupts.
4. **User transcript** — displayed on `conversation.item.input_audio_transcription.completed`.
5. **Interruption** — on `speech_started`, the AudioPlayer closes and re-creates its AudioContext, stopping all queued playback immediately.

**Stage 2 note:** The frontend does not change at all when adding the abstraction layer. The WebSocket message format is the contract between frontend and server. As long as the server sends the same JSON shapes, the frontend works unchanged.

Files:
* static/index.html - New file

Success criteria:
* Opens in browser, shows Connect/Disconnect buttons
* Requests microphone permission on Connect
* Sends audio chunks over WebSocket
* Plays back agent audio
* Displays transcripts for agent and user
* Interrupts playback when user speaks

Dependencies:
* Step 3.1 (audio-processor.js for AudioWorklet)
* Step 2.2 (server running at /ws/)

## Implementation Phase 4: Infrastructure as Code

<!-- parallelizable: true -->

### Step 4.1: Create `infra/main.bicep`

Minimal Bicep template deploying Azure OpenAI with a realtime model:

```bicep
targetScope = 'resourceGroup'

@description('Name of the Azure OpenAI resource')
param openAiAccountName string

@description('Azure region')
param location string = resourceGroup().location

@description('Realtime model deployment name')
param realtimeDeploymentName string = 'gpt-4o-realtime'

@description('Realtime model name')
@allowed([
  'gpt-4o-realtime-preview'
  'gpt-realtime'
  'gpt-realtime-1.5'
])
param realtimeModelName string = 'gpt-4o-realtime-preview'

@description('Model version')
param realtimeModelVersion string = '2024-12-17'

@description('Deployment capacity (TPM in thousands)')
@minValue(1)
param deploymentCapacity int = 1

resource openAiAccount 'Microsoft.CognitiveServices/accounts@2025-12-01' = {
  name: openAiAccountName
  location: location
  kind: 'OpenAI'
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: openAiAccountName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
  sku: { name: 'S0' }
}

resource realtimeDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-12-01' = {
  parent: openAiAccount
  name: realtimeDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: deploymentCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: realtimeModelName
      version: realtimeModelVersion
    }
    versionUpgradeOption: 'OnceCurrentVersionExpired'
  }
}

output openAiEndpoint string = openAiAccount.properties.endpoint
output openAiAccountName string = openAiAccount.name
output realtimeDeploymentName string = realtimeDeployment.name
output principalId string = openAiAccount.identity.principalId
```

Files:
* infra/main.bicep - New file

Success criteria:
* `az bicep lint --file infra/main.bicep` passes
* Deploys Azure OpenAI with GlobalStandard realtime model
* Outputs endpoint URL and deployment name

Dependencies:
* None

### Step 4.2: Create `infra/main.bicepparam`

```bicep
using './main.bicep'

param openAiAccountName = 'oai-voice-agent-dev'
param location = 'eastus2'
param realtimeDeploymentName = 'gpt-4o-realtime'
param realtimeModelName = 'gpt-4o-realtime-preview'
param realtimeModelVersion = '2024-12-17'
param deploymentCapacity = 1
```

Files:
* infra/main.bicepparam - New file

Success criteria:
* References `main.bicep`
* Provides sensible defaults for development
* East US 2 has broadest realtime model availability

## Implementation Phase 5: Documentation

<!-- parallelizable: true -->

### Step 5.1: Create `README.md`

```markdown
# Real-Time Voice Agent

A sample project demonstrating a real-time voice agent using the OpenAI Agents SDK,
Azure OpenAI Realtime API, and a browser-based frontend.

## Architecture

Browser (WebSocket) → FastAPI Server (RealtimeRunner) → Azure OpenAI Realtime API

The server acts as a relay: microphone audio flows from the browser through
FastAPI to Azure; agent audio and transcripts flow back.

## Prerequisites

- Python 3.10+
- Azure OpenAI resource with a realtime model deployment
- Modern browser (Chrome 74+, Edge 79+, Firefox 76+, Safari 14.1+)

## Setup

### 1. Deploy Azure Resources

```bash
az deployment group create \
  --resource-group <your-rg> \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your Azure OpenAI endpoint, key, and deployment name
```

### 3. Install and Run

```bash
pip install -e .
uvicorn app.main:app --reload
```

### 4. Open Browser

Navigate to `http://localhost:8000` and click **Connect**.

## Project Structure

```text
├── infra/              # Bicep IaC for Azure OpenAI
├── src/app/            # FastAPI server + agent
│   ├── main.py         # WebSocket endpoint
│   ├── config.py       # Pydantic settings
│   ├── agent.py        # RealtimeAgent + tools
│   └── realtime_listener.py  # Event listener
├── static/             # Browser frontend
│   ├── index.html      # UI + audio logic
│   └── audio-processor.js  # AudioWorklet
├── pyproject.toml      # Dependencies
└── .env.example        # Environment template
```
```

Files:
* README.md - New file

## Implementation Phase 6: Validation

<!-- parallelizable: false -->

### Step 6.1: Verify Python imports and syntax

```bash
python -m py_compile src/app/config.py
python -m py_compile src/app/agent.py
python -m py_compile src/app/realtime_listener.py
python -m py_compile src/app/main.py
```

### Step 6.2: Verify Bicep linting (if az cli available)

```bash
az bicep lint --file infra/main.bicep
```

### Step 6.3: Fix minor issues

Iterate on import errors and lint warnings.

### Step 6.4: Report blocking issues

Document anything requiring additional research.

## Dependencies

* `openai-agents[voice]>=0.13.0` — RealtimeAgent + RealtimeRunner
* `fastapi>=0.115.0` — WebSocket endpoints
* `uvicorn[standard]>=0.30.0` — ASGI server
* `pydantic-settings>=2.0.0` — Environment config
* Python 3.10+

## Success Criteria

* Server starts with `uvicorn app.main:app`
* Browser connects, sends audio, receives audio and transcripts
* Bicep deploys Azure OpenAI with realtime model
* No abstraction layer code (no `voice/` module, no VoiceEvent, no protocols)
