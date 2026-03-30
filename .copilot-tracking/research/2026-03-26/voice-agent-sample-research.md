<!-- markdownlint-disable-file -->
# Task Research: Voice Agent Sample Project

Set up a sample project for creating simple voice agents with a FastAPI/Pydantic server (using OpenAI Agents SDK), Azure Bicep IaC for the realtime model, and a browser-based frontend for audio input.

## Task Implementation Requests

* Server: FastAPI backend with Pydantic settings/models, using OpenAI Agents SDK `RealtimeAgent` + `RealtimeRunner` for voice agent orchestration
* IaC: Bicep templates for provisioning Azure OpenAI with a realtime model deployment (`gpt-4o-realtime-preview` / `gpt-realtime-1.5`)
* Frontend: Vanilla HTML/JS browser app for microphone capture and WebSocket audio streaming to the server

## Scope and Success Criteria

* Scope: End-to-end voice agent sample — server, IaC, and frontend. Greenfield project in `observability-realtime-agent/`.
* Assumptions:
  * Azure OpenAI service with realtime model availability (GlobalStandard deployment)
  * Python 3.10+ for the server
  * Modern browser with WebAudio API + AudioWorklet support (Chrome 74+, Edge 79+, Firefox 76+, Safari 14.1+)
  * HTTPS or localhost for microphone access
* Success Criteria:
  * Complete architecture with code examples for all three layers
  * One recommended approach per technical scenario with rationale
  * Bicep templates ready for deployment
  * Implementation-ready project structure with file references

## Outline

1. Key Discoveries
2. Technical Scenarios (Server SDK, IaC, Frontend, Project Structure)
3. Selected Architecture
4. Complete Examples
5. Potential Next Research

## Research Executed

### Subagent Research Documents

* .copilot-tracking/research/subagents/2026-03-26/openai-agents-sdk-voice-research.md — OpenAI Agents SDK voice capabilities, RealtimeAgent, VoicePipeline, Azure integration, Microsoft Foundry comparison
* .copilot-tracking/research/subagents/2026-03-26/bicep-azure-openai-realtime-research.md — Azure Bicep resource types, model names, region availability, three complete Bicep templates (minimal, AVM, full-stack)
* .copilot-tracking/research/subagents/2026-03-26/browser-audio-frontend-research.md — WebAudio capture, AudioWorklet, PCM16 encoding, audio playback, UI patterns, framework comparison
* .copilot-tracking/research/subagents/2026-03-26/fastapi-websocket-voice-server-research.md — FastAPI WebSocket relay, Pydantic settings/models, SDK integration, project structure, reference implementation analysis

### External Research

* OpenAI Agents SDK docs: https://openai.github.io/openai-agents-python/
  * v0.13.1, PyPI `openai-agents`, voice extras via `pip install 'openai-agents[voice]'`
* OpenAI Agents SDK GitHub: https://github.com/openai/openai-agents-python
  * Reference implementation at `examples/realtime/app/server.py` — complete FastAPI + RealtimeAgent relay
* Azure OpenAI Realtime API: https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/realtime-audio
  * WebSocket, WebRTC, SIP transports; PCM16 mono 24kHz; 30-min sessions
* Azure Bicep resource references: https://learn.microsoft.com/en-us/azure/templates/microsoft.cognitiveservices/accounts
  * `Microsoft.CognitiveServices/accounts@2025-12-01` and `accounts/deployments@2025-12-01`
* Pydantic Settings docs: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
* FastAPI WebSocket docs: https://fastapi.tiangolo.com/advanced/websockets/
* MDN WebAudio/AudioWorklet docs: https://developer.mozilla.org/en-US/docs/Web/API/AudioWorkletNode

## Key Discoveries

### 1. OpenAI Agents SDK Is the Right Choice (Not Microsoft Foundry)

**Microsoft Foundry Agent Service does NOT support voice/realtime.** It is a text-only agent platform (prompt agents, workflow agents, hosted agents). For voice scenarios with Azure, the recommended path is the **OpenAI Agents SDK** with `RealtimeAgent` pointed at Azure endpoints.

The SDK provides two voice approaches:

| Approach | Latency | Mechanism | Best For |
|---|---|---|---|
| VoicePipeline (STT → Agent → TTS) | Higher (~3 round trips) | Separate Whisper + Agent + TTS | Push-to-talk, pre-recorded audio |
| **RealtimeAgent + RealtimeRunner** | **Low (~200ms WebSocket)** | **Direct Realtime API WebSocket** | **Live voice assistants, browser relay** |

**RealtimeAgent is the correct choice** — the SDK fully manages the WebSocket to Azure/OpenAI, handles tool execution, handoffs, interruptions, guardrails, and history.

### 2. Azure OpenAI Realtime API Requires GlobalStandard Deployment

* Realtime models require **`GlobalStandard`** SKU (global routing)
* Available models: `gpt-4o-realtime-preview` (preview), `gpt-realtime` (GA), `gpt-realtime-1.5` (latest)
* Audio format: PCM16, mono, 24kHz, base64-encoded in JSON transport
* VAD modes: `none` (push-to-talk), `server_vad` (silence-based), `semantic_vad` (model-based)
* Max session duration: 30 minutes
* GA endpoint: `wss://{resource}.openai.azure.com/openai/v1/realtime?model={deployment}`

### 3. Browser AudioWorklet with 24kHz AudioContext Avoids Manual Resampling

Creating `AudioContext({ sampleRate: 24000 })` in the browser natively resamples to 24kHz (Chrome 74+, Edge 79+, Firefox 61+, Safari 14.1+). The AudioWorklet converts Float32 to Int16 (PCM16) off the main thread, then base64-encodes for WebSocket transport. No manual resampling needed.

### 4. Reference Implementation Exists

The `openai/openai-agents-python` repo has a complete FastAPI + RealtimeAgent reference at `examples/realtime/app/`. Key pattern: `RealtimeWebSocketManager` accepts browser WebSocket, creates `RealtimeRunner` → `RealtimeSession` per connection, runs two concurrent async flows (browser→Azure, Azure→browser).

### 5. Bicep Templates for Azure OpenAI

* Account: `Microsoft.CognitiveServices/accounts@2025-12-01`, `kind: 'OpenAI'`, SKU `S0`
* Deployment: `accounts/deployments@2025-12-01`, SKU `GlobalStandard`, model format `OpenAI`
* `customSubDomainName` is required for Entra ID auth
* East US 2 and Sweden Central have broadest availability

## Technical Scenarios

### Scenario 1: Server-Side Agent Framework

**Requirements:**
* FastAPI WebSocket endpoint relaying browser audio to Azure OpenAI Realtime API
* OpenAI Agents SDK managing the upstream connection
* Pydantic settings for configuration, Pydantic models for message types
* Support for tool calls, interruptions, transcript forwarding

**Preferred Approach: OpenAI Agents SDK `RealtimeAgent` + `RealtimeRunner` in FastAPI**

The SDK manages the entire Azure WebSocket lifecycle internally. The server acts as a relay:

```text
Browser (WebSocket) ──▶ FastAPI (RealtimeRunner/Session) ──▶ Azure OpenAI Realtime API
                    ◀──                                  ◀──
```

```python
# agent.py — Agent definition
from agents.realtime import RealtimeAgent
from agents import function_tool

@function_tool
def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"Sunny, 72°F in {city}"

agent = RealtimeAgent(
    name="Assistant",
    instructions="You are a helpful voice assistant. Keep responses concise.",
    tools=[get_weather],
)
```

```python
# config.py — Pydantic settings
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_deployment: str = "gpt-4o-realtime"
    voice: str = "ash"
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def azure_realtime_url(self) -> str:
        base = self.azure_openai_endpoint.replace("https://", "")
        return f"wss://{base}/openai/v1/realtime?model={self.azure_openai_deployment}"

    @property
    def azure_headers(self) -> dict[str, str]:
        return {"api-key": self.azure_openai_api_key}
```

```python
# main.py — FastAPI server with WebSocket relay
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from agents.realtime import RealtimeRunner, RealtimeSession
import asyncio, json, struct, base64

app = FastAPI()

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    settings = Settings()

    runner = RealtimeRunner(agent)
    session_ctx = await runner.run(model_config={
        "url": settings.azure_realtime_url,
        "headers": settings.azure_headers,
    })
    session = await session_ctx.__aenter__()

    async def forward_events():
        async for event in session:
            if event.type == "audio":
                audio_b64 = base64.b64encode(event.audio.data).decode()
                await websocket.send_text(json.dumps({"type": "audio", "audio": audio_b64}))
            elif event.type == "agent_start":
                await websocket.send_text(json.dumps({"type": "agent_start", "agent": event.agent.name}))

    task = asyncio.create_task(forward_events())
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg["type"] == "audio":
                audio_bytes = struct.pack(f"{len(msg['data'])}h", *msg["data"])
                await session.send_audio(audio_bytes)
    except WebSocketDisconnect:
        task.cancel()
        await session_ctx.__aexit__(None, None, None)

app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

#### Considered Alternatives

**Manual WebSocket to Azure (without SDK):** Would require reimplementing session management, tool execution, interruption handling, and all event parsing. The SDK provides all of this out of the box. **Rejected** — unnecessary complexity with no benefit for a sample project.

**VoicePipeline (STT → Agent → TTS):** Higher latency (3 sequential round trips), works with any text-based Agent but doesn't leverage the Realtime API's native speech-to-speech capability. **Rejected** — wrong tool for a low-latency voice assistant demo.

**Microsoft Foundry Agent Service:** Does not support voice/realtime at all. **Rejected** — not applicable.

### Scenario 2: Infrastructure as Code (Bicep)

**Requirements:**
* Deploy Azure OpenAI account with realtime model
* Support parameterized model name and version
* Include outputs for endpoint URL and resource identifiers

**Preferred Approach: Raw Bicep resources (not AVM) — minimal template**

A simple, self-contained Bicep template is best for a sample project. AVM adds abstraction complexity that obscures what resources are actually deployed.

```bicep
// infra/main.bicep
targetScope = 'resourceGroup'

@description('Name of the Azure OpenAI resource')
param openAiAccountName string

@description('Azure region')
param location string = resourceGroup().location

@description('Realtime model deployment name')
param realtimeDeploymentName string = 'gpt-4o-realtime'

@description('Realtime model name')
@allowed(['gpt-4o-realtime-preview', 'gpt-realtime', 'gpt-realtime-1.5'])
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

#### Considered Alternatives

**AVM module (`br/public:avm/res/cognitive-services/account`):** More feature-rich (private endpoints, diagnostics, RBAC built-in) but adds indirection. The module uses API version `2025-06-01` vs the latest `2025-12-01`. **Better for production** but overkill for a sample. Documented in subagent research for reference.

**Full-stack template (Log Analytics + App Insights + Key Vault + RBAC):** Complete observability stack. Documented in subagent research. Can be adopted later as the sample matures.

### Scenario 3: Browser Frontend

**Requirements:**
* Capture microphone audio as PCM16 24kHz mono
* Stream audio over WebSocket to FastAPI server
* Play back agent audio responses
* Handle interruptions (stop playback when user speaks)
* Minimal UI with connect/disconnect and transcript display

**Preferred Approach: Vanilla HTML/JS — zero build step**

Two files: `index.html` (UI + app logic) and `audio-processor.js` (AudioWorklet). FastAPI serves them as static files. No npm, no bundler, no framework.

Key implementation patterns:

1. **Audio Capture:** `getUserMedia()` → `AudioContext({ sampleRate: 24000 })` → `AudioWorkletNode` → Float32→Int16 conversion → base64 encode → WebSocket send
2. **Audio Playback:** Receive base64 PCM16 → decode → `AudioBufferSourceNode` with scheduled `start()` for gapless playback
3. **Interruption:** On `speech_started` event, close and re-create playback `AudioContext`
4. **Chunk buffering:** Buffer ~100ms (2400 samples) before sending to match Azure API recommendations

```text
static/
  index.html              # UI + app.js inline or linked
  audio-processor.js      # AudioWorklet processor (must be separate file)
```

#### Considered Alternatives

**React/Vite SPA:** Component model, hot reload, but requires Node.js + build step. Overkill for a sample focused on the server-side agent. OpenAI Realtime Console uses this, but it also uses WebRTC — a different architecture.

**WebRTC direct connection:** Lowest latency (~100ms), bypasses server for audio, but prevents server-side observability/tracing and requires client-side API key management. Not compatible with the server-side relay pattern the user requested.

### Scenario 4: Project Structure

**Preferred Structure:**

```text
observability-realtime-agent/
├── infra/
│   ├── main.bicep                # Azure OpenAI + realtime model
│   └── main.bicepparam           # Parameter file
├── src/
│   └── app/
│       ├── __init__.py
│       ├── main.py               # FastAPI app, WebSocket endpoint, uvicorn
│       ├── config.py             # Pydantic BaseSettings
│       ├── models.py             # Pydantic message models
│       ├── agent.py              # RealtimeAgent + tools
│       └── session_manager.py    # WebSocket relay manager
├── static/
│   ├── index.html                # Browser UI
│   └── audio-processor.js        # AudioWorklet processor
├── pyproject.toml                # Dependencies + project metadata
├── .env.example                  # Environment variable template
├── .gitignore
└── README.md
```

**Dependencies:**

```toml
[project]
name = "observability-realtime-agent"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "websockets>=13.0",
    "openai-agents>=0.13.0",
    "pydantic-settings>=2.0.0",
]
```

## Potential Next Research

* OpenTelemetry tracing integration for RealtimeAgent sessions (observability in production)
  * Reasoning: Core to the "observability-realtime-agent" project name
  * Reference: OpenAI Agents SDK built-in tracing support
* Azure Entra ID managed identity auth flow (vs API key)
  * Reasoning: Production security best practice
  * Reference: Azure OpenAI docs on token-based auth
* CI/CD pipeline for Bicep deployment (GitHub Actions / Azure DevOps)
  * Reasoning: Automate infrastructure provisioning
  * Reference: Azure deployment documentation
* Audio echo cancellation and mobile browser quirks
  * Reasoning: Production audio quality
  * Reference: Browser WebAudio documentation
* Cost estimation for realtime model usage
  * Reasoning: Budget planning for the sample
  * Reference: Azure OpenAI pricing documentation
