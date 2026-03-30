# FastAPI WebSocket Voice Server with Pydantic — Research Document

## Research Topics

1. FastAPI WebSocket server design for bidirectional audio streaming
2. Pydantic Settings and Models for configuration and message types
3. Integration with OpenAI Agents SDK (RealtimeAgent + RealtimeRunner)
4. Project structure for a FastAPI voice agent
5. Static file serving and CORS

---

## 1. FastAPI WebSocket Server Design

### Core Pattern: Browser ↔ FastAPI ↔ Azure OpenAI Realtime API

The architecture follows a **server-side WebSocket relay** pattern:

```
Browser (JS) ──WebSocket──▶ FastAPI Server ──WebSocket──▶ Azure OpenAI Realtime API
              ◀── audio ───              ◀── audio ───
```

### FastAPI WebSocket Endpoint Basics

From the official FastAPI docs (https://fastapi.tiangolo.com/advanced/websockets/):

```python
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Message text was: {data}")
```

Key capabilities:
- `websocket.accept()` — accept the connection
- `websocket.receive_text()` / `websocket.receive_bytes()` — receive data
- `websocket.send_text()` / `websocket.send_bytes()` — send data
- `WebSocketDisconnect` exception — handle disconnections
- Supports `Depends`, `Query`, `Path` parameters like regular endpoints
- Supports binary, text, and JSON data

### Connection Manager Pattern

FastAPI docs show a `ConnectionManager` class for handling multiple clients:

```python
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
```

### Concurrent WebSocket Relay: The OpenAI `examples/realtime/app` Pattern

The **canonical reference implementation** is `examples/realtime/app/server.py` from the openai-agents-python repository. This is a FastAPI server that relays browser WebSocket audio to the OpenAI Realtime API.

**Architecture from the README:**
> Backend: FastAPI server with WebSocket connections for real-time communication. Each connection gets a unique session with the OpenAI Realtime API. Audio Processing: 24kHz mono audio capture and playback.

**Key code patterns from `examples/realtime/app/server.py`:**

```python
import asyncio
import base64
import json
import struct
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from agents.realtime import RealtimeRunner, RealtimeSession, RealtimeSessionEvent
from agents.realtime.model import RealtimeModelConfig

class RealtimeWebSocketManager:
    def __init__(self):
        self.active_sessions: dict[str, RealtimeSession] = {}
        self.session_contexts: dict[str, Any] = {}
        self.websockets: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.websockets[session_id] = websocket

        agent = get_starting_agent()
        runner = RealtimeRunner(agent)
        model_config: RealtimeModelConfig = {
            "initial_model_settings": {
                "model_name": "gpt-realtime-1.5",
                "turn_detection": {
                    "type": "server_vad",
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                    "interrupt_response": True,
                    "create_response": True,
                },
            },
        }
        session_context = await runner.run(model_config=model_config)
        session = await session_context.__aenter__()
        self.active_sessions[session_id] = session
        self.session_contexts[session_id] = session_context

        # Start background task to forward events from Realtime API to browser
        asyncio.create_task(self._process_events(session_id))

    async def _process_events(self, session_id: str):
        """Forward Realtime API events to the browser WebSocket."""
        session = self.active_sessions[session_id]
        websocket = self.websockets[session_id]
        async for event in session:
            event_data = await self._serialize_event(event)
            await websocket.send_text(json.dumps(event_data))

    async def send_audio(self, session_id: str, audio_bytes: bytes):
        if session_id in self.active_sessions:
            await self.active_sessions[session_id].send_audio(audio_bytes)

manager = RealtimeWebSocketManager()

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await manager.connect(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            if message["type"] == "audio":
                int16_data = message["data"]
                audio_bytes = struct.pack(f"{len(int16_data)}h", *int16_data)
                await manager.send_audio(session_id, audio_bytes)
    except WebSocketDisconnect:
        await manager.disconnect(session_id)
```

### Concurrency Pattern: asyncio Dual-Task

The relay uses two concurrent async flows per session:

1. **Browser → Server → Azure**: The `websocket_endpoint` loop receives audio from the browser and calls `session.send_audio()` to forward to Azure.
2. **Azure → Server → Browser**: A background `asyncio.create_task` iterates `async for event in session` and forwards serialized events back to the browser WebSocket.

This is the standard asyncio pattern — no threads needed, everything runs on a single event loop.

### Audio Serialization

- Browser sends audio as JSON with int16 array: `{"type": "audio", "data": [...]}`
- Server packs to bytes: `struct.pack(f"{len(int16_data)}h", *int16_data)`
- Response audio is base64-encoded: `base64.b64encode(event.audio.data).decode("utf-8")`

### Session Cleanup

```python
async def disconnect(self, session_id: str):
    if session_id in self.session_contexts:
        await self.session_contexts[session_id].__aexit__(None, None, None)
        del self.session_contexts[session_id]
    if session_id in self.active_sessions:
        del self.active_sessions[session_id]
    if session_id in self.websockets:
        del self.websockets[session_id]
```

---

## 2. Pydantic Settings and Models

### Pydantic Settings for Configuration

From pydantic-settings docs (https://docs.pydantic.dev/latest/concepts/pydantic_settings/):

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_deployment: str
    openai_api_key: str = ""
    model_name: str = "gpt-realtime-1.5"
    voice: str = "ash"
    host: str = "0.0.0.0"
    port: int = 8000
```

Key features:
- `env_file=".env"` — auto-loads from `.env` file
- Fields are automatically populated from environment variables
- Environment variables take priority over `.env` file values
- `extra="ignore"` — ignore extra env vars that aren't fields
- Supports type coercion (str → int, etc.)
- Case-insensitive by default for env var names

### Pydantic Models for WebSocket Message Types

For type-safe message parsing between browser and server:

```python
from pydantic import BaseModel
from typing import Literal

class AudioMessage(BaseModel):
    type: Literal["audio"]
    data: list[int]  # int16 PCM samples

class SessionConfigMessage(BaseModel):
    type: Literal["session.config"]
    voice: str | None = None
    instructions: str | None = None

class AudioOutputEvent(BaseModel):
    type: Literal["audio"]
    audio: str  # base64-encoded PCM

class TranscriptEvent(BaseModel):
    type: Literal["transcript"]
    role: Literal["user", "assistant"]
    text: str

class ErrorEvent(BaseModel):
    type: Literal["error"]
    error: str

# Discriminated union for incoming messages
from typing import Annotated, Union
from pydantic import Field

IncomingMessage = Annotated[
    Union[AudioMessage, SessionConfigMessage],
    Field(discriminator="type"),
]
```

---

## 3. Integration with OpenAI Agents SDK

### Key Finding: Use `RealtimeAgent` + `RealtimeRunner` — SDK Manages the Azure WebSocket

The OpenAI Agents SDK (openai-agents-python) provides a complete server-side WebSocket abstraction through `RealtimeAgent`, `RealtimeRunner`, and `RealtimeSession`. **The SDK manages the WebSocket connection to Azure/OpenAI Realtime API internally.**

From the Realtime transport docs:
> `RealtimeRunner` uses `OpenAIRealtimeWebSocketModel` unless you pass a custom `RealtimeModel`. The standard Python topology: 1) Your Python service creates a `RealtimeRunner`. 2) `await runner.run()` returns a `RealtimeSession`. 3) Enter the session and send text, structured messages, or audio. 4) Consume `RealtimeSessionEvent` items and forward audio or transcripts to your application.

### VoicePipeline vs RealtimeAgent — Which to Use?

There are **two distinct voice approaches** in the SDK:

#### VoicePipeline (STT → Agent → TTS)
- 3-step pipeline: Speech-to-Text → Agent workflow → Text-to-Speech
- Uses regular `Agent` (not `RealtimeAgent`)
- Audio goes through: mic → STT model → text → agent → text → TTS model → speaker
- Higher latency (multiple roundtrips)
- Works with `AudioInput` or `StreamedAudioInput`
- Good for turn-based conversations

#### RealtimeAgent + RealtimeRunner (Direct Realtime API)
- Direct WebSocket connection to OpenAI Realtime API
- Audio streams incrementally to/from the model
- **Lower latency** — model processes audio directly, no separate STT/TTS step
- Supports interruptions, tool calls, handoffs during live audio
- **This is the right choice for a WebSocket voice relay server**

### RealtimeAgent + RealtimeRunner Code Pattern

```python
from agents.realtime import RealtimeAgent, RealtimeRunner
from agents import function_tool

@function_tool
def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"Weather in {city} is sunny."

agent = RealtimeAgent(
    name="Assistant",
    instructions="You are a helpful voice assistant.",
    tools=[get_weather],
)

runner = RealtimeRunner(
    starting_agent=agent,
    config={
        "model_settings": {
            "model_name": "gpt-realtime-1.5",
            "audio": {
                "input": {
                    "format": "pcm16",
                    "transcription": {"model": "gpt-4o-mini-transcribe"},
                    "turn_detection": {"type": "semantic_vad", "interrupt_response": True},
                },
                "output": {"format": "pcm16", "voice": "ash"},
            },
        }
    },
)
```

### Connecting to Azure OpenAI (Not Just OpenAI)

From the Realtime agents guide — Low-level access and custom endpoints:

```python
session = await runner.run(
    model_config={
        "url": "wss://<your-resource>.openai.azure.com/openai/v1/realtime?model=<deployment-name>",
        "headers": {"api-key": "<your-azure-api-key>"},
    }
)
```

Or with bearer token:

```python
session = await runner.run(
    model_config={
        "url": "wss://<your-resource>.openai.azure.com/openai/v1/realtime?model=<deployment-name>",
        "headers": {"authorization": f"Bearer {token}"},
    }
)
```

**Critical note:** When `headers` are passed explicitly, the SDK does not add `Authorization` automatically. Avoid the legacy beta path.

### Session Lifecycle for WebSocket Relay

```python
# 1. Create runner (once, or per session)
runner = RealtimeRunner(agent)

# 2. Start session with Azure config
session = await runner.run(model_config={
    "url": azure_ws_url,
    "headers": {"api-key": azure_api_key},
    "initial_model_settings": { ... },
})

# 3. Enter session (opens WebSocket to Azure)
await session.enter()  # or use `async with session:`

# 4. Send audio from browser
await session.send_audio(audio_bytes)

# 5. Receive events (in background task)
async for event in session:
    if event.type == "audio":
        # Forward event.audio.data to browser
        pass

# 6. Close session
await session.close()
```

### Event Types from RealtimeSession

Key session events:
- `audio` — audio data bytes from the model
- `audio_end` — audio stream complete
- `audio_interrupted` — user interrupted
- `agent_start`, `agent_end` — agent lifecycle
- `tool_start`, `tool_end` — tool execution
- `history_added`, `history_updated` — conversation history
- `guardrail_tripped` — guardrail triggered
- `error` — error occurred
- `raw_model_event` — raw event from model

---

## 4. Recommended Project Structure

```
observability-realtime-agent/
├── pyproject.toml              # or requirements.txt
├── .env                        # local env vars (gitignored)
├── .env.example                # template for env vars
├── src/
│   └── app/
│       ├── __init__.py
│       ├── main.py             # FastAPI app, lifespan, uvicorn entry
│       ├── config.py           # Pydantic BaseSettings
│       ├── models.py           # Pydantic models for WS messages
│       ├── agent.py            # RealtimeAgent definition + tools
│       └── session_manager.py  # WebSocket session manager (browser ↔ Azure relay)
├── static/                     # Frontend HTML/JS/CSS
│   ├── index.html
│   ├── app.js
│   └── audio-recorder.worklet.js
└── tests/
    └── ...
```

### Dependencies

```toml
[project]
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "websockets>=13.0",
    "openai-agents>=0.13.0",
    "pydantic-settings>=2.0.0",
]
```

Or `requirements.txt`:

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
websockets>=13.0
openai-agents>=0.13.0
pydantic-settings>=2.0.0
```

---

## 5. Static File Serving

### FastAPI StaticFiles Mount

From the openai-agents-python example:

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()

# Mount static files AFTER all other routes
app.mount("/", StaticFiles(directory="static", html=True), name="static")

@app.get("/")
async def read_index():
    return FileResponse("static/index.html")
```

**Important:** `StaticFiles` mount must come after all route definitions (it's a catch-all).

### CORS Configuration (if needed)

Typically not needed when serving frontend from same origin, but if separate:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or specific origins
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Uvicorn Configuration

From the example:

```python
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        ws_max_size=16 * 1024 * 1024,  # 16MB for large payloads
    )
```

---

## 6. Complete Pydantic Settings Example

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Azure OpenAI Realtime
    azure_openai_endpoint: str = Field(
        description="Azure OpenAI resource endpoint (e.g., https://myresource.openai.azure.com)"
    )
    azure_openai_api_key: str = Field(description="Azure OpenAI API key")
    azure_openai_deployment: str = Field(
        default="gpt-4o-realtime-preview",
        description="Azure OpenAI deployment name for Realtime API"
    )

    # Agent configuration
    agent_instructions: str = Field(
        default="You are a helpful voice assistant. Keep responses concise.",
        description="System instructions for the agent"
    )
    voice: str = Field(default="ash", description="TTS voice name")

    # Server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    @property
    def azure_realtime_url(self) -> str:
        return (
            f"wss://{self.azure_openai_endpoint.replace('https://', '')}"
            f"/openai/v1/realtime?model={self.azure_openai_deployment}"
        )

    @property
    def azure_headers(self) -> dict[str, str]:
        return {"api-key": self.azure_openai_api_key}
```

Corresponding `.env.example`:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_DEPLOYMENT=gpt-4o-realtime-preview
AGENT_INSTRUCTIONS=You are a helpful voice assistant.
VOICE=ash
HOST=0.0.0.0
PORT=8000
```

---

## 7. Key Decisions and Recommendations

### Use OpenAI Agents SDK RealtimeAgent — NOT Manual WebSocket

**Recommendation: Use the SDK.**

Reasons:
- The SDK fully manages the WebSocket connection to Azure/OpenAI Realtime API
- Handles session lifecycle, tool execution, handoffs, guardrails, interruptions
- Provides `session.send_audio(bytes)` and `async for event in session` abstractions
- Supports Azure OpenAI via `model_config` with custom `url` and `headers`
- The `examples/realtime/app/server.py` is a complete reference FastAPI implementation
- Manual WebSocket management would require reimplementing all of the above

### VoicePipeline vs RealtimeAgent

**Recommendation: Use RealtimeAgent + RealtimeRunner.**

- `VoicePipeline` (STT → Agent → TTS) has higher latency and is designed for local mic/speaker or turn-based flows
- `RealtimeAgent` uses the direct Realtime API WebSocket — much lower latency
- The Realtime API handles speech-to-text and text-to-speech internally
- Better suited for browser WebSocket relay where audio streams bidirectionally

### Browser WebRTC Note

The Python SDK docs explicitly state:
> The Python SDK does not provide a browser WebRTC transport. Browser WebRTC is outside this SDK.

Our architecture uses **WebSocket transport from browser to server**, with the server managing the Realtime API connection. This is the standard supported pattern.

---

## 8. Follow-on Questions (Discovered During Research)

1. **Audio format negotiation**: The browser AudioWorklet captures at 24kHz 16-bit PCM. Does this match Azure OpenAI Realtime API `pcm16` format directly, or does resampling need to occur?
2. **Multiple concurrent sessions**: The `RealtimeWebSocketManager` uses dicts keyed by `session_id`. Any concern with memory/connection limits for many simultaneous users?
3. **Error recovery**: What happens when the Azure WebSocket connection drops mid-session? Does the SDK reconnect automatically, or do we need to handle this?
4. **Observability integration**: How to add OpenTelemetry tracing to the relay server for monitoring audio latency, session duration, and tool calls?

---

## References

- FastAPI WebSocket docs: https://fastapi.tiangolo.com/advanced/websockets/
- Pydantic Settings docs: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- OpenAI Agents SDK Realtime Quickstart: https://openai.github.io/openai-agents-python/realtime/quickstart/
- OpenAI Agents SDK Realtime Guide: https://openai.github.io/openai-agents-python/realtime/guide/
- OpenAI Agents SDK Realtime Transport: https://openai.github.io/openai-agents-python/realtime/transport/
- OpenAI Agents SDK Voice Quickstart: https://openai.github.io/openai-agents-python/voice/quickstart/
- Reference implementation (FastAPI + Realtime): `openai/openai-agents-python/examples/realtime/app/server.py`
- Twilio integration example: `openai/openai-agents-python/examples/realtime/twilio/`
