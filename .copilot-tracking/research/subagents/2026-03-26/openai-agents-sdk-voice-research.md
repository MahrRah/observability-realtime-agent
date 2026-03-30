# OpenAI Agents SDK and Microsoft Agent Framework for Voice Agents

## Research Topics

1. OpenAI Agents SDK (openai-agents-python) — architecture, voice pipeline, realtime support
2. Microsoft Agent Framework (Foundry Agent Service) — current state, voice/realtime capabilities
3. Azure OpenAI Realtime API — WebSocket protocol, authentication, message format

## Status: Complete

---

## 1. OpenAI Agents SDK (openai-agents-python)

### Overview

The OpenAI Agents SDK is a lightweight Python framework for building multi-agent workflows. It is provider-agnostic, supporting OpenAI Responses and Chat Completions APIs plus 100+ other LLMs. Successor to `Swarm`.

- **GitHub**: https://github.com/openai/openai-agents-python (v0.13.1, 20.3k stars)
- **PyPI**: `openai-agents` v0.13.1 (released 2025-03-25)
- **Install**: `pip install openai-agents` (base), `pip install 'openai-agents[voice]'` (voice extras)
- **Python**: 3.10+
- **Docs**: https://openai.github.io/openai-agents-python/

### Core Primitives

- **Agent**: LLM configured with instructions, tools, guardrails, and handoffs
- **Runner**: Executes agents with an agent loop (tool calls, LLM responses, looping until done)
- **Handoffs**: Delegate to sub-agents for specific tasks
- **Guardrails**: Input/output validation/safety checks run in parallel
- **Function Tools**: Any Python function becomes a tool via `@function_tool` decorator
- **MCP Servers**: Built-in Model Context Protocol server integration
- **Sessions**: Persistent memory layer for cross-run context
- **Tracing**: Built-in trace/debug/monitor support

### Two Voice Approaches

The SDK provides **two distinct approaches** for voice agents:

#### Approach A: Voice Pipeline (STT → Agent → TTS)

A three-step pipeline architecture:

1. **Speech-to-Text (STT)**: Transcribes audio input to text (OpenAI Whisper or similar)
2. **Agent Workflow**: Runs your agent logic on the transcribed text
3. **Text-to-Speech (TTS)**: Converts agent output text back to audio

**Key classes:**
- `VoicePipeline` — Orchestrates the 3-step pipeline
- `SingleAgentVoiceWorkflow` — Simple workflow wrapping a single Agent
- `VoiceWorkflowBase` — Base class for custom workflows
- `AudioInput` — Static (pre-recorded) audio buffer
- `StreamedAudioInput` — Live streaming audio with turn detection
- `StreamedAudioResult` — Streams events + audio output
- `VoicePipelineConfig` — Configuration for STT/TTS models, tracing
- `OpenAIVoiceModelProvider` — Default provider for STT/TTS models

**Voice pipeline example:**

```python
import asyncio
import numpy as np
import sounddevice as sd

from agents import Agent, function_tool
from agents.voice import AudioInput, SingleAgentVoiceWorkflow, VoicePipeline
from agents.extensions.handoff_prompt import prompt_with_handoff_instructions

@function_tool
def get_weather(city: str) -> str:
    """Get the weather for a given city."""
    return f"The weather in {city} is sunny."

agent = Agent(
    name="Assistant",
    instructions=prompt_with_handoff_instructions(
        "You're speaking to a human, so be polite and concise.",
    ),
    model="gpt-5.4",
    tools=[get_weather],
)

async def main():
    pipeline = VoicePipeline(workflow=SingleAgentVoiceWorkflow(agent))
    buffer = np.zeros(24000 * 3, dtype=np.int16)
    audio_input = AudioInput(buffer=buffer)

    result = await pipeline.run(audio_input)

    player = sd.OutputStream(samplerate=24000, channels=1, dtype=np.int16)
    player.start()

    async for event in result.stream():
        if event.type == "voice_stream_event_audio":
            player.write(event.data)

if __name__ == "__main__":
    asyncio.run(main())
```

**Streamed (live microphone) variant:**

```python
from agents.voice import StreamedAudioInput, VoicePipeline

pipeline = VoicePipeline(workflow=SingleAgentVoiceWorkflow(agent))
audio_input = StreamedAudioInput()

# Push audio chunks from microphone
await audio_input.add_audio(data)

result = await pipeline.run(audio_input)
async for event in result.stream():
    if event.type == "voice_stream_event_audio":
        player.write(event.data)
```

**Characteristics:**
- Higher latency (STT + LLM + TTS sequentially)
- Works with any text-based Agent (not limited to realtime models)
- Good for push-to-talk or pre-recorded audio
- Custom STT/TTS model selection


#### Approach B: Realtime Agents (Native speech-to-speech via WebSocket)

Direct WebSocket connection to the OpenAI Realtime API. Audio goes in and audio comes out — the model handles speech natively without separate STT/TTS steps. Much lower latency.

**Key classes:**
- `RealtimeAgent` — Specialized Agent subclass for realtime sessions
- `RealtimeRunner` — Session factory; wires agent to WebSocket transport
- `RealtimeSession` — Live connection; send input, receive events, tracks history
- `RealtimeModel` / `OpenAIRealtimeWebSocketModel` — Transport abstraction (WebSocket default)
- `OpenAIRealtimeSIPModel` — SIP/telephony attach transport
- `RealtimeSessionEvent` — Union type for all session events
- `RealtimeRunConfig` — Full session configuration
- `RealtimeSessionModelSettings` — Audio format, voice, VAD, model settings
- `RealtimePlaybackTracker` — Track what audio the user has heard (for interruption)
- `realtime_handoff()` — Create handoffs between RealtimeAgents

**RealtimeAgent limitations vs regular Agent:**
- No per-agent model choice (all agents in a session use the same realtime model)
- No structured outputs
- Voice cannot change after first spoken audio
- No `modelSettings` or `toolUseBehavior`
- Instructions, tools, handoffs, hooks, and guardrails still work

**Realtime agent example:**

```python
import asyncio
from agents.realtime import RealtimeAgent, RealtimeRunner

agent = RealtimeAgent(
    name="Assistant",
    instructions="You are a helpful voice assistant. Keep responses short and conversational.",
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
                    "turn_detection": {
                        "type": "semantic_vad",
                        "interrupt_response": True,
                    },
                },
                "output": {
                    "format": "pcm16",
                    "voice": "ash",
                },
            },
        }
    },
)

async def main() -> None:
    session = await runner.run()

    async with session:
        await session.send_message("Say hello in one short sentence.")

        async for event in session:
            if event.type == "audio":
                # Forward or play event.audio.data
                pass
            elif event.type == "history_added":
                print(event.item)
            elif event.type == "agent_end":
                break
            elif event.type == "error":
                print(f"Error: {event.error}")

if __name__ == "__main__":
    asyncio.run(main())
```

**Twilio phone integration example (server):**

```python
from agents import function_tool
from agents.realtime import (
    RealtimeAgent, RealtimeRunner, RealtimeSession, RealtimePlaybackTracker
)

@function_tool
def get_weather(city: str) -> str:
    """Get the weather in a city."""
    return "Sunny, 72°F"

agent = RealtimeAgent(
    name="Twilio Assistant",
    instructions="You are a helpful phone assistant. Keep responses concise.",
    tools=[get_weather],
)

# In Twilio WebSocket handler:
runner = RealtimeRunner(agent)
session = await runner.run(
    model_config={
        "api_key": os.getenv("OPENAI_API_KEY"),
        "initial_model_settings": {
            "model_name": "gpt-realtime-1.5",
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "turn_detection": {
                "type": "semantic_vad",
                "interrupt_response": True,
                "create_response": True,
            },
        },
    }
)
await session.enter()
```

**Multi-agent handoff example:**

```python
from agents.realtime import RealtimeAgent, realtime_handoff

billing_agent = RealtimeAgent(
    name="Billing Support",
    instructions="You specialize in billing issues.",
)

main_agent = RealtimeAgent(
    name="Customer Service",
    instructions="Triage the request and hand off when needed.",
    handoffs=[realtime_handoff(billing_agent, tool_description="Transfer to billing support")],
)
```

**Supported transport topologies:**
1. **Server-side WebSocket** (default) — Python service manages audio pipeline, tools, approvals
2. **SIP attach** — Telephony; agent attaches to an existing call via `call_id`
3. **Browser WebRTC** — Outside Python SDK scope; use official WebRTC docs

**Default model settings:**
```python
DEFAULT_MODEL_SETTINGS = {
    "voice": "ash",
    "modalities": ["audio"],
    "input_audio_format": "pcm16",
    "output_audio_format": "pcm16",
    "input_audio_transcription": {"model": "gpt-4o-mini-transcribe"},
    "turn_detection": {"type": "semantic_vad", "interrupt_response": True},
}
DEFAULT_REALTIME_MODEL = "gpt-realtime-1.5"
```

**Available realtime model names:**
- `gpt-realtime`, `gpt-realtime-1.5`, `gpt-realtime-2025-08-28`
- `gpt-4o-realtime-preview`, `gpt-4o-realtime-preview-2024-10-01`, `gpt-4o-realtime-preview-2024-12-17`, `gpt-4o-realtime-preview-2025-06-03`
- `gpt-4o-mini-realtime-preview`, `gpt-4o-mini-realtime-preview-2024-12-17`
- `gpt-realtime-mini`, `gpt-realtime-mini-2025-10-06`, `gpt-realtime-mini-2025-12-15`

**Audio formats:** `pcm16`, `g711_ulaw`, `g711_alaw`

**Session events emitted:**
- `RealtimeAgentStartEvent`, `RealtimeAgentEndEvent`
- `RealtimeAudio`, `RealtimeAudioEnd`, `RealtimeAudioInterrupted`
- `RealtimeToolStart`, `RealtimeToolEnd`, `RealtimeToolApprovalRequired`
- `RealtimeHandoffEvent`
- `RealtimeHistoryAdded`, `RealtimeHistoryUpdated`
- `RealtimeGuardrailTripped`
- `RealtimeError`, `RealtimeRawModelEvent`
- `RealtimeInputAudioTimeoutTriggered`

**Shipped examples in repo:**
- `examples/realtime/app/` — Full web UI demo
- `examples/realtime/cli/` — Terminal-based voice demo with microphone
- `examples/realtime/twilio/` — Twilio Media Streams phone integration
- `examples/realtime/twilio_sip/` — Twilio SIP integration with multi-agent handoffs
- `examples/voice/static/` — Pre-recorded audio pipeline demo
- `examples/voice/streamed/` — Live microphone streaming pipeline demo

### Connecting to Azure OpenAI

From the realtime quickstart docs:

> When connecting to Azure OpenAI, pass a GA Realtime endpoint URL in `model_config["url"]` and explicit headers. Avoid the legacy beta path (`/openai/realtime?api-version=...`) with realtime agents.

```python
session = await runner.run(
    model_config={
        "url": "wss://my-resource.openai.azure.com/openai/v1/realtime?model=my-deployment",
        "headers": {"api-key": "YOUR_AZURE_API_KEY"},
    }
)
```

---

## 2. Microsoft Agent Framework (Foundry Agent Service)

### Current State

Microsoft Foundry Agent Service (formerly Azure AI Agents) is a fully managed platform for building, deploying, and scaling AI agents. It is now part of **Microsoft Foundry** (renamed from Azure AI Foundry).

**Agent types supported:**
1. **Prompt agents** — No-code, defined via instructions + model + tools in the portal
2. **Workflow agents** (preview) — Multi-step orchestration, YAML/visual builder
3. **Hosted agents** (preview) — Custom code deployed as containers (Agent Framework, LangGraph, etc.)

**Key capabilities:**
- Built-in tools: web search, file search, memory, code interpreter, MCP servers, custom functions
- Model catalog support: GPT-4o, Llama, DeepSeek, etc.
- Enterprise features: Entra identity, RBAC, content filters, VNet isolation
- Observability: Tracing, metrics, Application Insights
- Publishing: Stable endpoints, versioning, Teams/M365 Copilot distribution

### Voice/Realtime Support

**No native voice/realtime agent support in Foundry Agent Service.**

The Foundry Agent Service is designed for text-based agent interactions (chat threads, tool calls, structured outputs). It does not provide:
- Real-time audio streaming capabilities
- WebSocket-based voice sessions
- Speech-to-speech model integration
- Turn detection or audio VAD

**For voice scenarios with Azure**, the recommended path is:
- Use the **Azure OpenAI Realtime API** directly (WebSocket, WebRTC, or SIP)
- Use the **OpenAI Agents SDK** with `RealtimeAgent` pointed at Azure endpoints
- Build custom voice pipelines using Azure Speech Services + Foundry agents for the text processing layer

### Comparison: OpenAI Agents SDK vs Microsoft Foundry Agent Service for Voice

| Feature | OpenAI Agents SDK | Microsoft Foundry Agent Service |
|---|---|---|
| Voice/audio native | Yes (Realtime + Voice Pipeline) | No |
| Real-time WebSocket | Yes (RealtimeAgent) | No |
| STT/TTS Pipeline | Yes (VoicePipeline) | No (would need custom) |
| Turn detection/VAD | Yes (server_vad, semantic_vad) | No |
| Telephony (SIP/Twilio) | Yes (built-in examples) | No |
| Interruption handling | Yes (native) | No |
| Multi-agent handoffs | Yes (realtime_handoff) | Yes (workflow agents) |
| Enterprise hosting | No (self-hosted) | Yes (fully managed) |
| Tool execution | Yes (function_tool) | Yes (built-in + custom) |
| Azure integration | Via model_config url/headers | Native Azure service |

---

## 3. Azure OpenAI Realtime API

### Overview

Part of the GPT-4o model family supporting low-latency "speech in, speech out" conversational interactions.

### Connection Methods

| Method | Use Case | Latency | Best For |
|---|---|---|---|
| WebRTC | Client-side apps | ~50-100ms | Web apps, mobile, browser |
| WebSocket | Server-to-server | ~100-300ms | Backend services, custom middleware |
| SIP | Telephony | Varies | Call centers, IVR systems |

### Supported Models (Azure)

- `gpt-4o-realtime-preview` (2024-12-17)
- `gpt-4o-mini-realtime-preview` (2024-12-17)
- `gpt-realtime` (2025-08-28)
- `gpt-realtime-mini` (2025-10-06, 2025-12-15)
- `gpt-realtime-1.5` (2026-02-23)

Token limits: 32,000 input tokens, 4,096 output tokens.
Max session duration: 30 minutes.

### WebSocket Connection

**Endpoint format (GA):**
```
wss://{resource-name}.openai.azure.com/openai/v1/realtime?model={deployment-name}
```

**Endpoint format (Preview):**
```
wss://{resource-name}.openai.azure.com/openai/realtime?api-version=2025-04-01-preview&deployment={deployment-name}
```

**Authentication options:**
1. **Microsoft Entra ID (recommended):** Bearer token in `Authorization` header
2. **API Key:** Via `api-key` header or query parameter

**Required libraries (Python):** `pip install websockets azure-identity`

### Session Configuration

First event sent is typically `session.update`:

```json
{
  "type": "session.update",
  "session": {
    "voice": "alloy",
    "instructions": "You are a helpful assistant.",
    "input_audio_format": "pcm16",
    "input_audio_transcription": {
      "model": "whisper-1"
    },
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

### Audio Format Requirements

- **Format**: PCM 16-bit (`pcm16`)
- **Channels**: Mono (single channel)
- **Sample rate**: 24kHz
- **Chunk size**: Recommended 100ms chunks
- **Encoding**: Base64-encoded when using JSON transport

### Voice Activity Detection (VAD)

Three modes:
1. **`none`** — Manual/push-to-talk; client sends `input_audio_buffer.commit` + `response.create`
2. **`server_vad`** — Automatic silence-based detection with configurable threshold/padding
3. **`semantic_vad`** — Model-based detection; understands when user has finished speaking (less likely to interrupt)

### Key Event Flow

**Client sends:**
- `session.update` — Configure session
- `input_audio_buffer.append` — Send audio chunks
- `input_audio_buffer.commit` — Commit audio (manual mode)
- `response.create` — Request response
- `response.cancel` — Cancel in-progress response
- `conversation.item.create` — Add items to conversation
- `conversation.item.truncate` — Truncate audio for interruption sync

**Server emits (response lifecycle):**
1. `response.created`
2. `response.output_item.added`
3. `conversation.item.created`
4. `response.content_part.added`
5. `response.audio_transcript.delta` (multiple)
6. `response.audio.delta` (multiple; base64 PCM audio chunks)
7. `response.audio.done`
8. `response.audio_transcript.done`
9. `response.content_part.done`
10. `response.output_item.done`
11. `response.done`

### Additional Features

- **Image input**: Send base64 images via `conversation.item.create` with `input_image` content type
- **MCP server support**: Configure remote MCP servers in session for tool execution
- **Out-of-band responses**: Generate responses outside the default conversation context
- **Tool calls**: Configure function tools in session; server calls them during conversation

---

## Follow-on Questions Discovered

1. How to add OpenTelemetry observability/tracing to a RealtimeAgent session for production monitoring?
2. What are the token costs and rate limits for realtime audio tokens on Azure?
3. How to implement custom guardrails for voice content in realtime sessions?
4. Can the OpenAI Agents SDK's RealtimeAgent work with Azure AD managed identity auth directly?
5. What is the recommended architecture for a production voice agent using Azure (load balancing, scaling, failover)?

---

## References

- OpenAI Agents SDK docs: https://openai.github.io/openai-agents-python/
- OpenAI Agents SDK GitHub: https://github.com/openai/openai-agents-python (v0.13.1)
- PyPI openai-agents: https://pypi.org/project/openai-agents/
- Realtime agents quickstart: https://openai.github.io/openai-agents-python/realtime/quickstart/
- Voice pipeline quickstart: https://openai.github.io/openai-agents-python/voice/quickstart/
- Realtime transport guide: https://openai.github.io/openai-agents-python/realtime/transport/
- Azure Realtime API docs: https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/realtime-audio
- Azure Realtime WebSocket docs: https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/realtime-audio-websockets
- Microsoft Foundry Agent Service: https://learn.microsoft.com/en-us/azure/ai-services/agents/overview
