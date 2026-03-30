# Semantic Kernel Realtime Audio + Abstraction Patterns for Voice Agents

## Research Topics

1. Semantic Kernel Python SDK Realtime Audio Support
2. Semantic Kernel Contact Center / Call Route Pattern
3. Abstraction Pattern for Multi-SDK Orchestration
4. OpenAI Agents SDK Event Model
5. Semantic Kernel Agent Event Model

## Status: Complete

---

## 1. Semantic Kernel Python SDK Realtime Audio Support

### Package Version and Availability

- **Package**: `semantic-kernel` v1.41.1 (released 2026-03-25)
- **PyPI**: https://pypi.org/project/semantic-kernel/
- **Realtime extra**: `pip install semantic-kernel[realtime]`
- **Additional deps**: `pyaudio`, `sounddevice`, `pydub`
- **Python**: 3.10+
- **API version requirement**: `2025-08-28` or later for Azure OpenAI realtime deployments
- **Feature stage**: Marked as `@experimental` (not yet GA in the SDK)

### Core Realtime Classes

The realtime API is structured around a base class and concrete implementations:

#### `RealtimeClientBase` (ABC)

Located at `semantic_kernel.connectors.ai.realtime_client_base`.

Abstract base class defining the realtime session lifecycle:

```python
class RealtimeClientBase(AIServiceClientBase, ABC):
    SUPPORTS_FUNCTION_CALLING: ClassVar[bool] = False
    audio_output_callback: Callable[[ndarray], Coroutine[Any, Any, None]] | None = None

    @abstractmethod
    async def send(self, event: RealtimeEvents) -> None: ...

    @abstractmethod
    def receive(self, audio_output_callback=None, **kwargs) -> AsyncGenerator[RealtimeEvents, None]: ...

    @abstractmethod
    async def create_session(self, chat_history=None, settings=None, **kwargs) -> None: ...

    @abstractmethod
    async def update_session(self, chat_history=None, settings=None, **kwargs) -> None: ...

    @abstractmethod
    async def close_session(self) -> None: ...

    # Context manager support
    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None: ...

    # Callable pattern for fluent configuration
    def __call__(self, chat_history=None, settings=None, **kwargs) -> Self: ...
```

#### Concrete Implementations

All in `semantic_kernel.connectors.ai.open_ai`:

| Class | Protocol | Backend |
|---|---|---|
| `AzureRealtimeWebsocket` | WebSocket | Azure OpenAI |
| `OpenAIRealtimeWebsocket` | WebSocket | OpenAI |
| `AzureRealtimeWebRTC` | WebRTC | Azure OpenAI |
| `OpenAIRealtimeWebRTC` | WebRTC | OpenAI |

Import pattern:

```python
from semantic_kernel.connectors.ai.open_ai import (
    AzureRealtimeExecutionSettings,
    AzureRealtimeWebsocket,
    ListenEvents,
)
```

#### `AzureRealtimeExecutionSettings`

Configuration for the realtime session:

```python
settings = AzureRealtimeExecutionSettings(
    instructions="You are a helpful assistant...",
    voice="shimmer",  # alloy, shimmer, etc.
    turn_detection=TurnDetection(
        type="server_vad",
        create_response=True,
        silence_duration_ms=800,
        threshold=0.8,
    ),
    function_choice_behavior=FunctionChoiceBehavior.Auto(),
)
```

### Event Model (Semantic Kernel)

#### `RealtimeEvents` Union Type

Defined in `semantic_kernel.contents.realtime_events`:

```python
RealtimeEvents = Union[
    RealtimeEvent,          # Base/generic event (service_event, service_type)
    RealtimeAudioEvent,     # audio: AudioContent
    RealtimeTextEvent,      # text: TextContent
    RealtimeFunctionCallEvent,    # function_call: FunctionCallContent
    RealtimeFunctionResultEvent,  # function_result: FunctionResultContent
    RealtimeImageEvent,     # image: ImageContent
]
```

Each event has:
- `event_type`: ClassVar discriminator (e.g., `"audio"`, `"text"`, `"service"`)
- `service_event`: Raw underlying event from the service (Any)
- `service_type`: String identifying the specific service event type (e.g., `ListenEvents.SESSION_UPDATED`)

#### `ListenEvents` Enum (Receive Events)

```python
class ListenEvents(str, Enum):
    ERROR = "error"
    SESSION_CREATED = "session.created"
    SESSION_UPDATED = "session.updated"
    CONVERSATION_CREATED = "conversation.created"
    INPUT_AUDIO_BUFFER_COMMITTED = "input_audio_buffer.committed"
    INPUT_AUDIO_BUFFER_CLEARED = "input_audio_buffer.cleared"
    INPUT_AUDIO_BUFFER_SPEECH_STARTED = "input_audio_buffer.speech_started"
    INPUT_AUDIO_BUFFER_SPEECH_STOPPED = "input_audio_buffer.speech_stopped"
    CONVERSATION_ITEM_CREATED = "conversation.item.created"
    CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED = "conversation.item.input_audio_transcription.completed"
    CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_FAILED = "conversation.item.input_audio_transcription.failed"
    CONVERSATION_ITEM_TRUNCATED = "conversation.item.truncated"
    CONVERSATION_ITEM_DELETED = "conversation.item.deleted"
    RESPONSE_CREATED = "response.created"
    RESPONSE_DONE = "response.done"
    RESPONSE_OUTPUT_ITEM_ADDED = "response.output_item.added"
    RESPONSE_OUTPUT_ITEM_DONE = "response.output_item.done"
    RESPONSE_CONTENT_PART_ADDED = "response.content_part.added"
    RESPONSE_CONTENT_PART_DONE = "response.content_part.done"
    RESPONSE_TEXT_DELTA = "response.output_text.delta"
    RESPONSE_TEXT_DONE = "response.output_text.done"
    RESPONSE_AUDIO_TRANSCRIPT_DELTA = "response.output_audio_transcript.delta"
    RESPONSE_AUDIO_TRANSCRIPT_DONE = "response.output_audio_transcript.done"
    RESPONSE_AUDIO_DELTA = "response.output_audio.delta"
    RESPONSE_AUDIO_DONE = "response.output_audio.done"
    RESPONSE_FUNCTION_CALL_ARGUMENTS_DELTA = "response.function_call_arguments.delta"
    RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE = "response.function_call_arguments.done"
    RATE_LIMITS_UPDATED = "rate_limits.updated"
```

#### `SendEvents` Enum (Send Events)

```python
class SendEvents(str, Enum):
    SESSION_UPDATE = "session.update"
    INPUT_AUDIO_BUFFER_APPEND = "input_audio_buffer.append"
    INPUT_AUDIO_BUFFER_COMMIT = "input_audio_buffer.commit"
    INPUT_AUDIO_BUFFER_CLEAR = "input_audio_buffer.clear"
    CONVERSATION_ITEM_CREATE = "conversation.item.create"
    CONVERSATION_ITEM_TRUNCATE = "conversation.item.truncate"
    CONVERSATION_ITEM_DELETE = "conversation.item.delete"
    RESPONSE_CREATE = "response.create"
    RESPONSE_CANCEL = "response.cancel"
```

### Event Consumption Pattern

SK uses an **async generator** pattern for event consumption:

```python
async with realtime_client:
    async for event in realtime_client.receive():
        match event:
            case RealtimeAudioEvent():
                await audio_player.add_audio(event.audio)
            case RealtimeTextEvent():
                print(event.text.text, end="")
            case _:
                if event.service_type == ListenEvents.SESSION_UPDATED:
                    print("Session updated")
                if event.service_type == ListenEvents.RESPONSE_CREATED:
                    print("\nAgent (transcript): ", end="")
```

Key patterns:
- **Context manager**: `async with realtime_client:` manages `create_session`/`close_session`
- **Async generator**: `async for event in realtime_client.receive():` yields typed events
- **Pattern matching**: Use Python `match/case` on event types
- **Audio callback**: Optional `audio_output_callback` parameter for low-latency audio
- **No explicit listener registration**: Events are consumed via the async for loop, not callbacks

### Function Calling Integration

SK integrates function calling via the Kernel:

```python
kernel = Kernel()
kernel.add_functions(plugin_name="helpers", functions=[goodbye, get_weather])

realtime_agent = AzureRealtimeWebsocket(credential=AzureCliCredential())

async with realtime_agent(
    settings=settings,
    chat_history=chat_history,
    kernel=kernel,
    create_response=True,
):
    async for event in realtime_agent.receive(audio_output_callback=audio_player.client_callback):
        match event:
            case RealtimeTextEvent():
                print(event.text.text, end="")
```

When `function_choice_behavior=FunctionChoiceBehavior.Auto()` is set and a kernel is attached:
- SK automatically handles `RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE` events
- Invokes the kernel function
- Sends the result back to the service
- Creates a new response automatically
- Yields `RealtimeFunctionCallEvent` and `RealtimeFunctionResultEvent` to the developer

### Samples

Located at `python/samples/concepts/realtime/` in the SK repo:

1. `simple_realtime_chat_websocket.py` - Basic voice chat via WebSocket
2. `simple_realtime_chat_webrtc.py` - Basic voice chat via WebRTC
3. `realtime_agent_with_function_calling_websocket.py` - Function calling via WebSocket
4. `realtime_agent_with_function_calling_webrtc.py` - Function calling via WebRTC
5. `utils.py` - Audio player/recorder utilities (`AudioPlayerWebsocket`, `AudioRecorderWebsocket`, etc.)

---

## 2. Semantic Kernel Contact Center / Call Route Pattern

### Referenced Internal Repo

The user referenced `commercial-software-engineering/ai-contact-center-solution-accelerator`, file `src/ai_contact_centre_solution_accelerator/routes/call.py`. This is a Microsoft internal/private repo and cannot be accessed via public GitHub search.

### Public Reconstruction Feasibility

Based on the SK realtime API discovered above, the contact center call route pattern can be **fully reconstructed from public sources**:

**Key architectural components a contact center voice agent would use:**

1. **FastAPI WebSocket endpoint**: Receives audio from telephony (e.g., Azure Communication Services)
2. **SK `AzureRealtimeWebsocket`**: Connects to Azure OpenAI Realtime API
3. **Audio relay**: Forward audio between the caller WebSocket and the Azure OpenAI WebSocket
4. **Kernel plugins**: Business logic tools (CRM lookup, transfer call, etc.)
5. **Event loop**: Process events from both sides

**Inferred pattern from public SK API:**

```python
@app.websocket("/call")
async def call_route(websocket: WebSocket):
    await websocket.accept()

    realtime_client = AzureRealtimeWebsocket(settings=settings)

    async with realtime_client(kernel=kernel, settings=settings):
        # Forward incoming audio from caller to Azure OpenAI
        async def forward_audio():
            while True:
                audio_data = await websocket.receive_bytes()
                await realtime_client.send(
                    RealtimeAudioEvent(audio=AudioContent(data=base64.b64encode(audio_data).decode()))
                )

        # Process events from Azure OpenAI and forward audio back
        async def process_events():
            async for event in realtime_client.receive():
                match event:
                    case RealtimeAudioEvent():
                        await websocket.send_bytes(event.audio.data)
                    case RealtimeTextEvent():
                        # Log transcript
                        pass

        await asyncio.gather(forward_audio(), process_events())
```

### Public GitHub Search Results

No public repos were found with exact `AzureRealtimeWebSocket` + FastAPI + contact center patterns. The SK samples in `microsoft/semantic-kernel` are the closest public reference.

---

## 3. Abstraction Pattern for Multi-SDK Orchestration

### Comparison: SK vs OpenAI Agents SDK

| Aspect | Semantic Kernel | OpenAI Agents SDK |
|---|---|---|
| **Session lifecycle** | `create_session()` / `close_session()` / context manager | `RealtimeSession` context manager |
| **Audio send** | `send(RealtimeAudioEvent(...))` | `session.send_audio(bytes)` |
| **Event consumption** | `async for event in client.receive()` | `async for event in result.stream` |
| **Event types** | `RealtimeEvents` union (discriminated) | `RealtimeSessionEvent` with typed variants |
| **Audio events** | `RealtimeAudioEvent` with `AudioContent` | `RealtimeAudio` / `RealtimeAudioEnd` |
| **Text events** | `RealtimeTextEvent` with `TextContent` | Included in `history_added` etc. |
| **Function calling** | Kernel auto-invocation or manual | `@function_tool` decorator, auto-invocation |
| **Listener/callbacks** | `audio_output_callback` parameter (optional) | Hooks via `RunHooks` |
| **Configuration** | `AzureRealtimeExecutionSettings` | `RealtimeSessionConfig` |
| **Base class** | `RealtimeClientBase` (ABC) | No common base; `RealtimeSession` is concrete |

### Recommended Abstraction: Protocol-Based (Hybrid)

**Recommendation: Use `typing.Protocol` for structural subtyping with a thin adapter layer.**

Rationale:
- SK already uses ABC (`RealtimeClientBase`) -- we don't want to force inheritance
- OpenAI Agents SDK has a completely different class hierarchy
- `typing.Protocol` allows structural subtyping (duck typing) without requiring inheritance
- An adapter pattern bridges the gap between SDK-specific APIs and the common interface

#### Proposed Protocol Design

```python
from typing import Protocol, AsyncIterator, Callable, Coroutine, Any
from dataclasses import dataclass
from enum import Enum
import numpy as np


# --- Unified Event Types ---

class VoiceEventType(str, Enum):
    AUDIO_DELTA = "audio_delta"
    AUDIO_END = "audio_end"
    AUDIO_INTERRUPTED = "audio_interrupted"
    TRANSCRIPT_DELTA = "transcript_delta"
    TRANSCRIPT_DONE = "transcript_done"
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    SESSION_CREATED = "session_created"
    SESSION_UPDATED = "session_updated"
    ERROR = "error"
    SPEECH_STARTED = "speech_started"
    SPEECH_STOPPED = "speech_stopped"


@dataclass
class VoiceEvent:
    event_type: VoiceEventType
    audio: bytes | None = None
    text: str | None = None
    tool_name: str | None = None
    tool_args: dict | None = None
    error: str | None = None
    raw_event: Any = None  # original SDK-specific event


# --- Session Protocol ---

class VoiceSessionProtocol(Protocol):
    """Protocol for a realtime voice agent session."""

    async def connect(self) -> None:
        """Establish the realtime connection."""
        ...

    async def disconnect(self) -> None:
        """Close the realtime connection."""
        ...

    async def send_audio(self, audio_data: bytes) -> None:
        """Send audio data to the model."""
        ...

    def events(self) -> AsyncIterator[VoiceEvent]:
        """Async iterator of voice events from the model."""
        ...

    async def __aenter__(self) -> "VoiceSessionProtocol":
        ...

    async def __aexit__(self, *args) -> None:
        ...


# --- Listener/Hook Protocol ---

class VoiceEventListener(Protocol):
    """Optional event listener for cross-cutting concerns (logging, metrics)."""

    async def on_event(self, event: VoiceEvent) -> None:
        """Called for every event."""
        ...


# --- Factory Protocol ---

class VoiceSessionFactory(Protocol):
    """Creates voice sessions from configuration."""

    def create_session(
        self,
        instructions: str,
        voice: str = "alloy",
        tools: list | None = None,
        listeners: list[VoiceEventListener] | None = None,
    ) -> VoiceSessionProtocol:
        ...
```

#### Adapter Examples

**SK Adapter:**

```python
class SemanticKernelVoiceSession:
    def __init__(self, sk_client: RealtimeClientBase, settings, kernel=None):
        self._client = sk_client
        self._settings = settings
        self._kernel = kernel

    async def connect(self):
        await self._client.create_session(settings=self._settings)

    async def disconnect(self):
        await self._client.close_session()

    async def send_audio(self, audio_data: bytes):
        await self._client.send(
            RealtimeAudioEvent(audio=AudioContent(data=base64.b64encode(audio_data).decode()))
        )

    async def events(self) -> AsyncIterator[VoiceEvent]:
        async for event in self._client.receive():
            yield self._map_event(event)

    def _map_event(self, event) -> VoiceEvent:
        match event:
            case RealtimeAudioEvent():
                return VoiceEvent(event_type=VoiceEventType.AUDIO_DELTA, audio=event.audio.data)
            case RealtimeTextEvent():
                return VoiceEvent(event_type=VoiceEventType.TRANSCRIPT_DELTA, text=event.text.text)
            # ... etc
```

**OpenAI Agents SDK Adapter:**

```python
class OpenAIAgentsVoiceSession:
    def __init__(self, agent, model, ...):
        self._agent = agent
        self._session = None

    async def connect(self):
        self._session = RealtimeSession(agent=self._agent, model=self._model)
        # ... connect

    async def send_audio(self, audio_data: bytes):
        self._session.send_audio(audio_data)

    async def events(self) -> AsyncIterator[VoiceEvent]:
        async for event in self._result.stream:
            yield self._map_event(event)
```

### Key Abstraction Points

1. **Session lifecycle**: `connect()` / `disconnect()` / context manager -- maps cleanly to both SDKs
2. **Audio I/O**: `send_audio(bytes)` / receive via `events()` async iterator -- both SDKs support this
3. **Event stream**: `async for event in session.events()` -- both SDKs use async generators
4. **Event normalization**: Map SDK-specific events to `VoiceEvent` with `VoiceEventType` enum
5. **Listeners**: Separate `VoiceEventListener` protocol for cross-cutting concerns (observability, logging)
6. **Configuration**: Each adapter takes SDK-specific config, but the factory protocol standardizes creation

### Why Protocol Over ABC

- **No forced inheritance**: Adapters don't need to inherit from a base class
- **Structural subtyping**: Any class with the right methods satisfies the protocol
- **Testability**: Easy to create mock sessions for testing
- **Composition over inheritance**: Adapters wrap SDK-specific clients
- **Runtime checking**: Can use `@runtime_checkable` for isinstance checks if needed

---

## 4. OpenAI Agents SDK Event Model

### `RealtimeSessionEvent` Types

From prior research (cross-referenced):

| Event Type | Description |
|---|---|
| `RealtimeAudio` | Audio delta from the model |
| `RealtimeAudioEnd` | Audio output completed |
| `RealtimeAudioInterrupted` | Audio was interrupted (user spoke) |
| `RealtimeAgentStartEvent` | Agent started processing |
| `RealtimeAgentEndEvent` | Agent finished processing |
| `RealtimeToolStart` | Tool call started |
| `RealtimeToolEnd` | Tool call completed |
| `RealtimeHistoryAdded` | Conversation history item added |
| `RealtimeGuardrailTripped` | Guardrail was triggered |
| `RealtimeError` | Error occurred |

### Event Consumption

```python
result = runner.run(session)
async for event in result.stream:
    match event:
        case RealtimeAudio():
            # raw audio bytes
        case RealtimeAudioEnd():
            # audio output finished
        case RealtimeAgentStartEvent():
            # agent is generating
```

### Hooks/Middleware

OpenAI Agents SDK supports `RunHooks` for cross-cutting concerns but these are primarily designed for chat agents. For realtime, event consumption is via the async stream.

---

## 5. Semantic Kernel Agent Event Model

### How SK Realtime Events Work

SK surfaces events through the **same async generator pattern** used by the OpenAI Agents SDK, but with different type hierarchy:

1. **Raw OpenAI events** are received from the WebSocket/WebRTC connection
2. **`_parse_event()`** method in `OpenAIRealtimeBase` maps them to SK's `RealtimeEvents` union types
3. **Audio events** (`RESPONSE_AUDIO_DELTA`) are handled specially:
   - The `audio_output_callback` is invoked first (for low-latency playback)
   - Then a `RealtimeAudioEvent` is yielded
4. **Text transcript events** (`RESPONSE_AUDIO_TRANSCRIPT_DELTA`) yield `RealtimeTextEvent`
5. **Function call events** trigger auto-invocation if a kernel is attached
6. **All other events** yield a generic `RealtimeEvent` with `service_type` and `service_event`

### No Separate Listener/Hook System

SK does NOT have a registered listener or callback system for realtime events (unlike its chat completion filters). The only callback is `audio_output_callback` for audio playback. All other event handling is done in the consumer's `async for` loop.

SK _does_ have **filters** for chat completion agents (auto function invocation filters, prompt filters), but these are not exposed for realtime agents.

### Comparison Table: Event Models

| Feature | SK Realtime | OpenAI Agents SDK |
|---|---|---|
| Consumption | `async for event in client.receive()` | `async for event in result.stream` |
| Event base type | `RealtimeEvent` (Pydantic) | Distinct event classes |
| Discriminator | `event_type` ClassVar + `service_type` | Python class type |
| Audio events | `RealtimeAudioEvent` → `AudioContent` | `RealtimeAudio` → raw bytes |
| Text events | `RealtimeTextEvent` → `TextContent` | Part of `RealtimeHistoryAdded` |
| Tool events | `RealtimeFunctionCallEvent` / `RealtimeFunctionResultEvent` | `RealtimeToolStart` / `RealtimeToolEnd` |
| Callbacks | Only `audio_output_callback` | `RunHooks` (limited for realtime) |
| Auto function calling | Via Kernel + `FunctionChoiceBehavior.Auto()` | Via `@function_tool` decorator |
| Raw event access | `event.service_event` | Via event-specific attributes |

---

## 6. References

- PyPI semantic-kernel: https://pypi.org/project/semantic-kernel/
- SK Python Realtime Samples: https://github.com/microsoft/semantic-kernel/tree/main/python/samples/concepts/realtime
- SK RealtimeClientBase source: `semantic_kernel/connectors/ai/realtime_client_base.py`
- SK OpenAI Realtime connectors: `semantic_kernel/connectors/ai/open_ai/services/_open_ai_realtime.py`
- SK Realtime events: `semantic_kernel/contents/realtime_events.py`
- SK Agent Framework docs: https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/
- SK Agent Architecture: https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/agent-architecture
- Python typing.Protocol: https://docs.python.org/3/library/typing.html#typing.Protocol
- PR #13291: "Python: support (Azure) OpenAI realtime audio models"

---

## 7. Follow-On Questions

1. Does SK plan to add a `RealtimeAgent` higher-level abstraction (like `ChatCompletionAgent`)?
2. Will SK expose filters/hooks for realtime events (similar to auto function invocation filters)?
3. The contact center pattern from `ai-contact-center-solution-accelerator` -- does it use any additional SK abstractions beyond what's in the public SDK?
4. Does Microsoft Foundry Agents plan to support realtime/voice as a native modality?

---

## 8. Clarifying Questions (Require User Input)

1. Should the abstraction layer handle **telephony integration** (e.g., Azure Communication Services WebSocket) or only the AI model connection?
2. For the event listener system, should it support **event filtering** (subscribe to specific event types) or receive all events?
3. Is the abstraction meant for **runtime switching** between SDKs or **compile-time selection** (one adapter per deployment)?
