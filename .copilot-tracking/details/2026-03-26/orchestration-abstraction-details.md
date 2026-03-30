<!-- markdownlint-disable-file -->
# Implementation Details: Orchestration Abstraction Layer for Voice Agents

## Context Reference

Sources:
* .copilot-tracking/research/subagents/2026-03-26/semantic-kernel-realtime-abstraction-research.md
* .copilot-tracking/research/subagents/2026-03-26/openai-agents-sdk-voice-research.md
* .copilot-tracking/research/subagents/2026-03-26/fastapi-websocket-voice-server-research.md
* .copilot-tracking/research/2026-03-26/voice-agent-sample-research.md

## Implementation Phase 1: Core Protocols and Event Model

<!-- parallelizable: true -->

### Step 1.1: Create `src/app/voice/events.py`

Define the unified event model that normalizes events across all supported SDKs.

**`VoiceEventType` enum** maps the superset of meaningful events from both SDKs:

| VoiceEventType | OpenAI Agents SDK Source | Semantic Kernel Source |
|---|---|---|
| `AUDIO_DELTA` | `RealtimeRawModelEvent` (`response.audio.delta`) | `RealtimeAudioEvent` |
| `AUDIO_END` | `RealtimeAudioEnd` | `ListenEvents.RESPONSE_AUDIO_DONE` |
| `AUDIO_INTERRUPTED` | `RealtimeAudioInterrupted` | `ListenEvents.INPUT_AUDIO_BUFFER_SPEECH_STARTED` |
| `TRANSCRIPT_DELTA` | `RealtimeRawModelEvent` (`response.audio_transcript.delta`, `conversation.item.input_audio_transcription.delta`) | `RealtimeTextEvent` |
| `TRANSCRIPT_DONE` | `RealtimeRawModelEvent` (`response.audio_transcript.done`, `conversation.item.input_audio_transcription.completed`) | `ListenEvents.RESPONSE_AUDIO_TRANSCRIPT_DONE` |
| `AGENT_START` | `RealtimeRawModelEvent` (`response.created`) | `ListenEvents.RESPONSE_CREATED` |
| `AGENT_END` | `RealtimeRawModelEvent` (`response.done`) | `ListenEvents.RESPONSE_DONE` |
| `TOOL_CALL_DONE` | `RealtimeRawModelEvent` (`response.function_call_arguments.done`) | `ListenEvents.RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE` |
| `TOOL_START` | `RealtimeToolStart` | `RealtimeFunctionCallEvent` |
| `TOOL_END` | `RealtimeToolEnd` | `RealtimeFunctionResultEvent` |
| `SESSION_CREATED` | `RealtimeRawModelEvent` (`session.created`) | `ListenEvents.SESSION_CREATED` |
| `SESSION_UPDATED` | `RealtimeRawModelEvent` (`session.updated`) | `ListenEvents.SESSION_UPDATED` |
| `SPEECH_STARTED` | `RealtimeRawModelEvent` (`input_audio_buffer.speech_started`) | `ListenEvents.INPUT_AUDIO_BUFFER_SPEECH_STARTED` |
| `SPEECH_STOPPED` | `RealtimeRawModelEvent` (`input_audio_buffer.speech_stopped`) | `ListenEvents.INPUT_AUDIO_BUFFER_SPEECH_STOPPED` |
| `CONVERSATION_ITEM_CREATED` | `RealtimeRawModelEvent` (`conversation.item.created`) | `ListenEvents.CONVERSATION_ITEM_CREATED` |
| `CONVERSATION_ITEM_TRUNCATED` | `RealtimeRawModelEvent` (`conversation.item.truncated`) | `ListenEvents.CONVERSATION_ITEM_TRUNCATED` |
| `ERROR` | `RealtimeRawModelEvent` (`error`) / `RealtimeError` | `ListenEvents.ERROR` |

> **Design note:** Both adapters target the same Azure OpenAI Realtime API wire protocol. The OpenAI Agents SDK surfaces most Realtime API events as `RealtimeRawModelEvent`, while SK maps them to `ListenEvents`. By routing through `RealtimeRawModelEvent` in the OpenAI adapter, the two adapters stay symmetrical — both keyed on the same underlying event type strings.
>
> **Typed-event vs raw-event precedence:** The OpenAI Agents SDK may emit both a typed event (e.g. `RealtimeAudio`) and a `RealtimeRawModelEvent` for the same underlying wire event. The adapter's `_map_event` match runs top-to-bottom — typed events are matched first (for `RealtimeAudioEnd`, `RealtimeAudioInterrupted`, `RealtimeToolStart`, `RealtimeToolEnd`, `RealtimeError`). The `RealtimeRawModelEvent` catch-all handles everything else including `response.audio.delta` for audio, `response.created`/`response.done` for agent lifecycle, and transcript/session/speech events. If a typed event is also emitted as a raw event, only the typed match fires.

**`VoiceEvent` dataclass** carries all event data in a normalized form:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class VoiceEventType(str, Enum):
    AUDIO_DELTA = "audio_delta"
    AUDIO_END = "audio_end"
    AUDIO_INTERRUPTED = "audio_interrupted"
    TRANSCRIPT_DELTA = "transcript_delta"
    TRANSCRIPT_DONE = "transcript_done"
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    TOOL_CALL_DONE = "tool_call_done"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    SESSION_CREATED = "session_created"
    SESSION_UPDATED = "session_updated"
    SPEECH_STARTED = "speech_started"
    SPEECH_STOPPED = "speech_stopped"
    CONVERSATION_ITEM_CREATED = "conversation_item_created"
    CONVERSATION_ITEM_TRUNCATED = "conversation_item_truncated"
    ERROR = "error"


@dataclass(frozen=True)
class VoiceEvent:
    event_type: VoiceEventType
    audio: bytes | None = None
    text: str | None = None
    agent_name: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result: str | None = None
    error: str | None = None
    raw_event: Any = field(default=None, repr=False)
```

Files:
* src/app/voice/events.py - New file containing `VoiceEventType` and `VoiceEvent`

Discrepancy references:
* Addresses DR-01: SK `SESSION_UPDATED` event has no direct OpenAI Agents SDK counterpart — included in enum but OpenAI adapter will never emit it

Success criteria:
* `VoiceEventType` enum contains all 14 event types
* `VoiceEvent` is a frozen dataclass with `raw_event` for SDK-specific access
* No SDK-specific imports in this file

Context references:
* .copilot-tracking/research/subagents/2026-03-26/semantic-kernel-realtime-abstraction-research.md (Lines 355-375) - VoiceEventType enum design
* .copilot-tracking/research/subagents/2026-03-26/openai-agents-sdk-voice-research.md (Lines 248-260) - RealtimeSessionEvent types

Dependencies:
* None (standard library only)

### Step 1.2: Create `src/app/voice/protocols.py`

Define the Protocol-based interfaces for voice sessions, listeners, and the session factory.

```python
from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable

from app.voice.events import VoiceEvent


@runtime_checkable
class VoiceEventListener(Protocol):
    """Cross-cutting event observer (logging, metrics, tracing)."""

    async def on_event(self, event: VoiceEvent) -> None: ...


@runtime_checkable
class VoiceSessionProtocol(Protocol):
    """Protocol for a realtime voice agent session.

    Implementations wrap SDK-specific clients (OpenAI Agents SDK,
    Semantic Kernel, etc.) and normalize events into VoiceEvent.
    """

    async def connect(self) -> None:
        """Establish the realtime connection to the model."""
        ...

    async def disconnect(self) -> None:
        """Close the realtime connection."""
        ...

    async def send_audio(self, audio_data: bytes) -> None:
        """Send PCM16 24kHz mono audio bytes to the model."""
        ...

    async def send_text(self, text: str) -> None:
        """Send a text message to the model (for text-based interaction)."""
        ...

    def events(self) -> AsyncIterator[VoiceEvent]:
        """Async iterator yielding normalized VoiceEvent from the model."""
        ...

    def add_listener(self, listener: VoiceEventListener) -> None:
        """Register a listener that receives all events."""
        ...

    def remove_listener(self, listener: VoiceEventListener) -> None:
        """Remove a previously registered listener."""
        ...

    async def __aenter__(self) -> VoiceSessionProtocol: ...
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None: ...
```

**Design decisions:**

1. **`@runtime_checkable`** — enables `isinstance(session, VoiceSessionProtocol)` for validation
2. **`add_listener` / `remove_listener`** — allows attaching/detaching observers at any time, not just at construction. This is the key user requirement.
3. **`events()` returns `AsyncIterator[VoiceEvent]`** — matches both SDKs' async generator pattern
4. **`send_text()`** — included for text-based fallback or hybrid interactions
5. **Context manager** — both SDKs support `async with` for session lifecycle

Files:
* src/app/voice/protocols.py - New file with Protocol definitions

Success criteria:
* Two protocols defined: `VoiceEventListener`, `VoiceSessionProtocol`
* `@runtime_checkable` on all protocols
* No SDK-specific imports

Context references:
* .copilot-tracking/research/subagents/2026-03-26/semantic-kernel-realtime-abstraction-research.md (Lines 376-430) - Protocol design
* Python typing.Protocol docs — structural subtyping

Dependencies:
* Step 1.1 (VoiceEvent import)

### Step 1.3: Create `src/app/voice/__init__.py`

Public API re-exports for the voice module:

```python
from app.voice.events import VoiceEvent, VoiceEventType
from app.voice.protocols import VoiceEventListener, VoiceSessionProtocol

__all__ = [
    "VoiceEvent",
    "VoiceEventType",
    "VoiceEventListener",
    "VoiceSessionProtocol",
]
```

Files:
* src/app/voice/__init__.py - New file

Success criteria:
* All public types importable from `app.voice`

Dependencies:
* Steps 1.1 and 1.2

## Implementation Phase 2: OpenAI Agents SDK Adapter

<!-- parallelizable: true -->

### Step 2.1: Create `src/app/voice/adapters/openai_agents.py`

Adapter wrapping OpenAI Agents SDK `RealtimeRunner` / `RealtimeSession` behind `VoiceSessionProtocol`.

Key implementation details:

1. **Constructor** takes agent configuration (instructions, tools, voice), Azure connection config, and optional listeners
2. **`connect()`** creates `RealtimeRunner`, calls `runner.run(model_config=...)`, enters the session context
3. **`disconnect()`** exits the session context
4. **`send_audio(bytes)`** calls `session.send_audio(audio_bytes)`
5. **`events()`** iterates `async for event in session:`, maps each to `VoiceEvent`, notifies listeners

**Event mapping logic:**

```python
from agents.realtime import (
    RealtimeAgent,
    RealtimeRunner,
    RealtimeSession,
    RealtimeAudio,
    RealtimeAudioEnd,
    RealtimeAudioInterrupted,
    RealtimeAgentStartEvent,
    RealtimeAgentEndEvent,
    RealtimeToolStart,
    RealtimeToolEnd,
    RealtimeError,
    RealtimeHistoryAdded,
    RealtimeRawModelEvent,
)
from agents import function_tool

from app.voice.events import VoiceEvent, VoiceEventType
from app.voice.protocols import VoiceEventListener, VoiceSessionProtocol


class OpenAIAgentsVoiceSession:
    """VoiceSessionProtocol adapter for OpenAI Agents SDK."""

    def __init__(
        self,
        agent: RealtimeAgent,
        model_config: dict,
        listeners: list[VoiceEventListener] | None = None,
    ) -> None:
        self._agent = agent
        self._model_config = model_config
        self._listeners: list[VoiceEventListener] = list(listeners or [])
        self._runner: RealtimeRunner | None = None
        self._session: RealtimeSession | None = None
        self._session_ctx: Any = None

    async def connect(self) -> None:
        self._runner = RealtimeRunner(self._agent)
        self._session_ctx = await self._runner.run(model_config=self._model_config)
        self._session = await self._session_ctx.__aenter__()

    async def disconnect(self) -> None:
        if self._session_ctx:
            await self._session_ctx.__aexit__(None, None, None)
            self._session_ctx = None
            self._session = None

    async def send_audio(self, audio_data: bytes) -> None:
        if self._session:
            await self._session.send_audio(audio_data)

    async def send_text(self, text: str) -> None:
        if self._session:
            await self._session.send_message(text)

    def add_listener(self, listener: VoiceEventListener) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: VoiceEventListener) -> None:
        self._listeners.remove(listener)

    async def _notify_listeners(self, event: VoiceEvent) -> None:
        for listener in self._listeners:
            await listener.on_event(event)

    async def events(self) -> AsyncIterator[VoiceEvent]:
        if not self._session:
            return
        async for raw_event in self._session:
            voice_event = self._map_event(raw_event)
            if voice_event:
                await self._notify_listeners(voice_event)
                yield voice_event

    def _map_event(self, event: Any) -> VoiceEvent | None:
        """Map SDK typed events first, fall through to raw model events.

        Typed events take precedence for: audio end, audio interrupted,
        tool start/end, error. Everything else is handled via
        RealtimeRawModelEvent to stay symmetrical with the SK adapter.
        """
        match event:
            case RealtimeAudioEnd():
                return VoiceEvent(
                    event_type=VoiceEventType.AUDIO_END,
                    raw_event=event,
                )
            case RealtimeAudioInterrupted():
                return VoiceEvent(
                    event_type=VoiceEventType.AUDIO_INTERRUPTED,
                    raw_event=event,
                )
            case RealtimeToolStart():
                return VoiceEvent(
                    event_type=VoiceEventType.TOOL_START,
                    tool_name=event.tool.name if hasattr(event, 'tool') else None,
                    raw_event=event,
                )
            case RealtimeToolEnd():
                return VoiceEvent(
                    event_type=VoiceEventType.TOOL_END,
                    tool_name=event.tool.name if hasattr(event, 'tool') else None,
                    tool_result=str(event.output) if hasattr(event, 'output') else None,
                    raw_event=event,
                )
            case RealtimeError():
                return VoiceEvent(
                    event_type=VoiceEventType.ERROR,
                    error=str(event.error),
                    raw_event=event,
                )
            case RealtimeRawModelEvent():
                return self._map_raw_model_event(event)
            case _:
                return None

    def _map_raw_model_event(self, event: Any) -> VoiceEvent | None:
        """Map raw Realtime API wire events to VoiceEvent.

        Both OpenAI Agents SDK and Semantic Kernel talk to the same
        Azure OpenAI Realtime API. By mapping from the raw wire events
        here, the two adapters stay symmetrical — both keyed on the
        same underlying event type strings.
        """
        raw = event.data if hasattr(event, 'data') else {}
        event_type = raw.get("type", "") if isinstance(raw, dict) else ""
        match event_type:
            # --- Audio events ---
            case "response.audio.delta":
                delta = raw.get("delta", "")
                # delta is base64-encoded PCM16; decode to bytes
                import base64
                audio_bytes = base64.b64decode(delta) if delta else b""
                return VoiceEvent(
                    event_type=VoiceEventType.AUDIO_DELTA,
                    audio=audio_bytes,
                    raw_event=event,
                )
            # --- Transcript events ---
            case "response.audio_transcript.delta":
                return VoiceEvent(
                    event_type=VoiceEventType.TRANSCRIPT_DELTA,
                    text=raw.get("delta", ""),
                    agent_name="assistant",
                    raw_event=event,
                )
            case "conversation.item.input_audio_transcription.delta":
                return VoiceEvent(
                    event_type=VoiceEventType.TRANSCRIPT_DELTA,
                    text=raw.get("delta", ""),
                    agent_name="user",
                    raw_event=event,
                )
            case "response.audio_transcript.done":
                return VoiceEvent(
                    event_type=VoiceEventType.TRANSCRIPT_DONE,
                    text=raw.get("transcript", ""),
                    agent_name="assistant",
                    raw_event=event,
                )
            case "conversation.item.input_audio_transcription.completed":
                return VoiceEvent(
                    event_type=VoiceEventType.TRANSCRIPT_DONE,
                    text=raw.get("transcript", ""),
                    agent_name="user",
                    raw_event=event,
                )
            # --- Agent / response lifecycle ---
            case "response.created":
                return VoiceEvent(
                    event_type=VoiceEventType.AGENT_START,
                    raw_event=event,
                )
            case "response.done":
                return VoiceEvent(
                    event_type=VoiceEventType.AGENT_END,
                    raw_event=event,
                )
            # --- Function calling ---
            case "response.function_call_arguments.done":
                call_id = raw.get("call_id", "")
                fn_name = raw.get("name", "")
                fn_args_str = raw.get("arguments", "{}")
                import json as _json
                try:
                    fn_args = _json.loads(fn_args_str)
                except (ValueError, TypeError):
                    fn_args = {"raw": fn_args_str}
                return VoiceEvent(
                    event_type=VoiceEventType.TOOL_CALL_DONE,
                    tool_name=fn_name,
                    tool_args=fn_args,
                    raw_event=event,
                )
            # --- Session lifecycle events ---
            case "session.created":
                return VoiceEvent(
                    event_type=VoiceEventType.SESSION_CREATED,
                    raw_event=event,
                )
            case "session.updated":
                return VoiceEvent(
                    event_type=VoiceEventType.SESSION_UPDATED,
                    raw_event=event,
                )
            # --- Speech detection events ---
            case "input_audio_buffer.speech_started":
                return VoiceEvent(
                    event_type=VoiceEventType.SPEECH_STARTED,
                    raw_event=event,
                )
            case "input_audio_buffer.speech_stopped":
                return VoiceEvent(
                    event_type=VoiceEventType.SPEECH_STOPPED,
                    raw_event=event,
                )
            # --- Conversation item events ---
            case "conversation.item.created":
                return VoiceEvent(
                    event_type=VoiceEventType.CONVERSATION_ITEM_CREATED,
                    raw_event=event,
                )
            case "conversation.item.truncated":
                return VoiceEvent(
                    event_type=VoiceEventType.CONVERSATION_ITEM_TRUNCATED,
                    raw_event=event,
                )
            # --- Error events ---
            case "error":
                return VoiceEvent(
                    event_type=VoiceEventType.ERROR,
                    error=raw.get("error", {}).get("message", str(raw)),
                    raw_event=event,
                )
            case _:
                return None

    async def __aenter__(self) -> "OpenAIAgentsVoiceSession":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()
```

Files:
* src/app/voice/adapters/openai_agents.py - New file

Discrepancy references:
* Addresses DD-01: SDK session lifecycle differs (runner.run() returns context manager) — adapter wraps this complexity

Success criteria:
* `OpenAIAgentsVoiceSession` satisfies `VoiceSessionProtocol` (verified by `isinstance` check)
* All RealtimeSessionEvent types are mapped to VoiceEvent
* `_notify_listeners()` called before yielding each event
* Context manager support for connect/disconnect

Context references:
* .copilot-tracking/research/subagents/2026-03-26/openai-agents-sdk-voice-research.md (Lines 155-230) - RealtimeAgent/RealtimeRunner/RealtimeSession API
* .copilot-tracking/research/subagents/2026-03-26/fastapi-websocket-voice-server-research.md (Lines 120-195) - Session lifecycle pattern from reference implementation

Dependencies:
* Phase 1 (events.py, protocols.py)
* `openai-agents>=0.13.0`

### Step 2.2: Create `src/app/voice/adapters/__init__.py`

```python
from app.voice.adapters.openai_agents import OpenAIAgentsVoiceSession

__all__ = ["OpenAIAgentsVoiceSession"]
```

Note: Semantic Kernel import is deferred (optional dependency, added in Phase 3).

Files:
* src/app/voice/adapters/__init__.py - New file

Success criteria:
* `OpenAIAgentsVoiceSession` importable from `app.voice.adapters`

Dependencies:
* Step 2.1

## Implementation Phase 3: Semantic Kernel Adapter

<!-- parallelizable: true -->

### Step 3.1: Create `src/app/voice/adapters/semantic_kernel.py`

Adapter wrapping SK `AzureRealtimeWebsocket` behind `VoiceSessionProtocol`.

Key differences from OpenAI adapter:
1. **Session creation**: SK uses `RealtimeClientBase` with `create_session()` / `close_session()` lifecycle
2. **Audio send**: SK wraps audio in `RealtimeAudioEvent(audio=AudioContent(data=base64_data))`
3. **Event receive**: SK yields `RealtimeEvents` union; match on type + `service_type`
4. **Function calling**: Handled automatically by SK Kernel if attached; events surface as `RealtimeFunctionCallEvent`

```python
from __future__ import annotations

import base64
from typing import Any, AsyncIterator

from app.voice.events import VoiceEvent, VoiceEventType
from app.voice.protocols import VoiceEventListener

try:
    from semantic_kernel.connectors.ai.open_ai import (
        AzureRealtimeExecutionSettings,
        AzureRealtimeWebsocket,
        ListenEvents,
    )
    from semantic_kernel.contents.realtime_events import (
        RealtimeAudioEvent,
        RealtimeTextEvent,
        RealtimeFunctionCallEvent,
        RealtimeFunctionResultEvent,
    )

    SK_AVAILABLE = True
except ImportError:
    SK_AVAILABLE = False


class SemanticKernelVoiceSession:
    """VoiceSessionProtocol adapter for Semantic Kernel."""

    def __init__(
        self,
        client: "AzureRealtimeWebsocket",
        settings: "AzureRealtimeExecutionSettings",
        kernel: Any = None,
        listeners: list[VoiceEventListener] | None = None,
    ) -> None:
        if not SK_AVAILABLE:
            raise ImportError(
                "semantic-kernel[realtime] is required. "
                "Install with: pip install 'semantic-kernel[realtime]'"
            )
        self._client = client
        self._settings = settings
        self._kernel = kernel
        self._listeners: list[VoiceEventListener] = list(listeners or [])

    async def connect(self) -> None:
        kwargs: dict[str, Any] = {"settings": self._settings}
        if self._kernel:
            kwargs["kernel"] = self._kernel
        await self._client.create_session(**kwargs)

    async def disconnect(self) -> None:
        await self._client.close_session()

    async def send_audio(self, audio_data: bytes) -> None:
        from semantic_kernel.contents import AudioContent

        audio_b64 = base64.b64encode(audio_data).decode("utf-8")
        await self._client.send(
            RealtimeAudioEvent(audio=AudioContent(data=audio_b64))
        )

    async def send_text(self, text: str) -> None:
        from semantic_kernel.contents import TextContent
        from semantic_kernel.contents.realtime_events import RealtimeTextEvent as SKTextEvent

        await self._client.send(SKTextEvent(text=TextContent(text=text)))

    def add_listener(self, listener: VoiceEventListener) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: VoiceEventListener) -> None:
        self._listeners.remove(listener)

    async def _notify_listeners(self, event: VoiceEvent) -> None:
        for listener in self._listeners:
            await listener.on_event(event)

    async def events(self) -> AsyncIterator[VoiceEvent]:
        async for raw_event in self._client.receive():
            voice_event = self._map_event(raw_event)
            if voice_event:
                await self._notify_listeners(voice_event)
                yield voice_event

    def _map_event(self, event: Any) -> VoiceEvent | None:
        match event:
            case RealtimeAudioEvent():
                audio_data = event.audio.data if event.audio else None
                if isinstance(audio_data, str):
                    audio_data = base64.b64decode(audio_data)
                return VoiceEvent(
                    event_type=VoiceEventType.AUDIO_DELTA,
                    audio=audio_data,
                    raw_event=event,
                )
            case RealtimeTextEvent():
                return VoiceEvent(
                    event_type=VoiceEventType.TRANSCRIPT_DELTA,
                    text=event.text.text if event.text else None,
                    raw_event=event,
                )
            case RealtimeFunctionCallEvent():
                return VoiceEvent(
                    event_type=VoiceEventType.TOOL_START,
                    tool_name=event.function_call.name if hasattr(event, 'function_call') else None,
                    raw_event=event,
                )
            case RealtimeFunctionResultEvent():
                return VoiceEvent(
                    event_type=VoiceEventType.TOOL_END,
                    tool_result=str(event.function_result) if hasattr(event, 'function_result') else None,
                    raw_event=event,
                )
            case _:
                # Map generic SK events by service_type
                service_type = getattr(event, "service_type", None)
                if service_type == ListenEvents.SESSION_CREATED:
                    return VoiceEvent(event_type=VoiceEventType.SESSION_CREATED, raw_event=event)
                elif service_type == ListenEvents.SESSION_UPDATED:
                    return VoiceEvent(event_type=VoiceEventType.SESSION_UPDATED, raw_event=event)
                elif service_type == ListenEvents.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                    return VoiceEvent(event_type=VoiceEventType.SPEECH_STARTED, raw_event=event)
                elif service_type == ListenEvents.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
                    return VoiceEvent(event_type=VoiceEventType.SPEECH_STOPPED, raw_event=event)
                elif service_type == ListenEvents.RESPONSE_CREATED:
                    return VoiceEvent(event_type=VoiceEventType.AGENT_START, raw_event=event)
                elif service_type == ListenEvents.RESPONSE_DONE:
                    return VoiceEvent(event_type=VoiceEventType.AGENT_END, raw_event=event)
                elif service_type == ListenEvents.RESPONSE_AUDIO_DONE:
                    return VoiceEvent(event_type=VoiceEventType.AUDIO_END, raw_event=event)
                elif service_type == ListenEvents.RESPONSE_AUDIO_TRANSCRIPT_DONE:
                    return VoiceEvent(
                        event_type=VoiceEventType.TRANSCRIPT_DONE,
                        text=str(getattr(event, "service_event", "")),
                        raw_event=event,
                    )
                elif service_type == ListenEvents.RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE:
                    se = getattr(event, "service_event", {})
                    fn_name = se.get("name", "") if isinstance(se, dict) else ""
                    fn_args_str = se.get("arguments", "{}") if isinstance(se, dict) else "{}"
                    import json as _json
                    try:
                        fn_args = _json.loads(fn_args_str)
                    except (ValueError, TypeError):
                        fn_args = {"raw": fn_args_str}
                    return VoiceEvent(
                        event_type=VoiceEventType.TOOL_CALL_DONE,
                        tool_name=fn_name,
                        tool_args=fn_args,
                        raw_event=event,
                    )
                elif service_type == ListenEvents.CONVERSATION_ITEM_CREATED:
                    return VoiceEvent(event_type=VoiceEventType.CONVERSATION_ITEM_CREATED, raw_event=event)
                elif service_type == ListenEvents.CONVERSATION_ITEM_TRUNCATED:
                    return VoiceEvent(event_type=VoiceEventType.CONVERSATION_ITEM_TRUNCATED, raw_event=event)
                elif service_type == ListenEvents.ERROR:
                    return VoiceEvent(
                        event_type=VoiceEventType.ERROR,
                        error=str(getattr(event, "service_event", "")),
                        raw_event=event,
                    )
                return None

    async def __aenter__(self) -> "SemanticKernelVoiceSession":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()
```

Files:
* src/app/voice/adapters/semantic_kernel.py - New file

Discrepancy references:
* Addresses DD-02: SK uses base64-encoded AudioContent while OpenAI SDK uses raw bytes — adapter handles encoding/decoding internally
* Addresses DR-02: SK `ListenEvents` has 28+ event types; only the most relevant are mapped — unmapped events return None

Success criteria:
* `SemanticKernelVoiceSession` satisfies `VoiceSessionProtocol`
* Audio data is properly encoded (base64) for SK send and decoded for VoiceEvent
* `SK_AVAILABLE` guard handles missing optional dependency gracefully
* All major SK event types mapped; unmapped events silently dropped

Context references:
* .copilot-tracking/research/subagents/2026-03-26/semantic-kernel-realtime-abstraction-research.md (Lines 30-110) - SK RealtimeClientBase API
* .copilot-tracking/research/subagents/2026-03-26/semantic-kernel-realtime-abstraction-research.md (Lines 112-185) - ListenEvents enum, event consumption pattern

Dependencies:
* Phase 1 (events.py, protocols.py)
* `semantic-kernel[realtime]>=1.41.0` (optional)

### Step 3.2: Update `pyproject.toml`

Add Semantic Kernel as an optional dependency group:

```toml
[project.optional-dependencies]
sk = [
    "semantic-kernel[realtime]>=1.41.0",
]
all = [
    "semantic-kernel[realtime]>=1.41.0",
]
```

This keeps `semantic-kernel` optional — users who only want the OpenAI Agents SDK backend don't need to install it.

Files:
* pyproject.toml - Modify existing file

Success criteria:
* `pip install .` installs only the OpenAI Agents SDK backend
* `pip install ".[sk]"` also installs `semantic-kernel[realtime]`
* `pip install ".[all]"` installs all optional backends

Dependencies:
* None

## Implementation Phase 4: Factory, Config, and Server Integration

<!-- parallelizable: false -->

### Step 4.1: Create `src/app/voice/factory.py`

Factory function that selects and creates the appropriate voice session adapter based on configuration.

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.voice.events import VoiceEvent, VoiceEventType
from app.voice.protocols import VoiceEventListener, VoiceSessionProtocol

if TYPE_CHECKING:
    from app.config import Settings


def create_voice_session(
    settings: "Settings",
    tools: list[Any] | None = None,
    listeners: list[VoiceEventListener] | None = None,
) -> VoiceSessionProtocol:
    """Create a voice session using the configured orchestrator backend."""

    if settings.orchestrator == "openai-agents":
        return _create_openai_agents_session(settings, tools=tools, listeners=listeners)
    elif settings.orchestrator == "semantic-kernel":
        return _create_semantic_kernel_session(settings, tools=tools, listeners=listeners)
    else:
        raise ValueError(f"Unknown orchestrator: {settings.orchestrator}")


def _create_openai_agents_session(
    settings: "Settings",
    tools: list[Any] | None = None,
    listeners: list[VoiceEventListener] | None = None,
) -> VoiceSessionProtocol:
    from agents.realtime import RealtimeAgent
    from app.voice.adapters.openai_agents import OpenAIAgentsVoiceSession

    agent = RealtimeAgent(
        name="Assistant",
        instructions=settings.agent_instructions,
        tools=tools or [],
    )

    model_config = {
        "url": settings.azure_realtime_url,
        "headers": settings.azure_headers,
    }

    return OpenAIAgentsVoiceSession(
        agent=agent,
        model_config=model_config,
        listeners=listeners,
    )


def _create_semantic_kernel_session(
    settings: "Settings",
    tools: list[Any] | None = None,
    listeners: list[VoiceEventListener] | None = None,
) -> VoiceSessionProtocol:
    from semantic_kernel import Kernel
    from semantic_kernel.connectors.ai.open_ai import (
        AzureRealtimeExecutionSettings,
        AzureRealtimeWebsocket,
    )
    from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
    from azure.identity import DefaultAzureCredential
    from app.voice.adapters.semantic_kernel import SemanticKernelVoiceSession

    kernel = Kernel()
    if tools:
        kernel.add_functions(plugin_name="tools", functions=tools)

    sk_settings = AzureRealtimeExecutionSettings(
        instructions=settings.agent_instructions,
        voice=settings.voice,
        turn_detection={"type": "server_vad", "silence_duration_ms": 800},
        function_choice_behavior=FunctionChoiceBehavior.Auto() if tools else None,
    )

    client = AzureRealtimeWebsocket(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_deployment=settings.azure_openai_deployment,
        azure_api_key=settings.azure_openai_api_key,
    )

    return SemanticKernelVoiceSession(
        client=client,
        settings=sk_settings,
        kernel=kernel if tools else None,
        listeners=listeners,
    )
```

Files:
* src/app/voice/factory.py - New file

Success criteria:
* `create_voice_session()` returns a `VoiceSessionProtocol` regardless of orchestrator
* SDK-specific imports are deferred to the branch that needs them (no top-level import of SK when using OpenAI)
* Tools and listeners are forwarded to the adapter

Context references:
* .copilot-tracking/research/subagents/2026-03-26/semantic-kernel-realtime-abstraction-research.md (Lines 440-460) - Factory pattern design
* .copilot-tracking/research/subagents/2026-03-26/fastapi-websocket-voice-server-research.md (Lines 490-540) - Settings integration

Dependencies:
* Phase 1 (protocols), Phase 2 (OpenAI adapter), Phase 3 (SK adapter)
* config.py with `orchestrator` field (Step 4.2)

### Step 4.2: Update `src/app/config.py`

Add the `orchestrator` field and `agent_instructions` to the Pydantic settings:

```python
from typing import Literal

class Settings(BaseSettings):
    # ... existing fields ...

    orchestrator: Literal["openai-agents", "semantic-kernel"] = "openai-agents"
    agent_instructions: str = "You are a helpful voice assistant. Keep responses concise."
```

Also add to `.env.example`:

```env
ORCHESTRATOR=openai-agents
AGENT_INSTRUCTIONS=You are a helpful voice assistant. Keep responses concise.
```

Files:
* src/app/config.py - Modify existing file
* .env.example - Modify existing file

Success criteria:
* `orchestrator` defaults to `"openai-agents"` (backward compatible)
* `Literal` type constrains values to supported backends
* `.env.example` documents the new field

Dependencies:
* None

### Step 4.3: Refactor `src/app/session_manager.py`

Replace SDK-specific session management with protocol-based management.

**Before** (SDK-specific):
```python
from agents.realtime import RealtimeRunner, RealtimeSession
# Direct SDK usage
```

**After** (protocol-based):
```python
from app.voice.protocols import VoiceSessionProtocol, VoiceEventListener
from app.voice.factory import create_voice_session

class VoiceSessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, VoiceSessionProtocol] = {}

    async def create(
        self,
        session_id: str,
        settings: Settings,
        tools: list | None = None,
        listeners: list[VoiceEventListener] | None = None,
    ) -> VoiceSessionProtocol:
        session = create_voice_session(settings, tools=tools, listeners=listeners)
        await session.connect()
        self._sessions[session_id] = session
        return session

    async def get(self, session_id: str) -> VoiceSessionProtocol | None:
        return self._sessions.get(session_id)

    async def remove(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            await session.disconnect()
```

Files:
* src/app/session_manager.py - Modify existing file

Discrepancy references:
* Addresses DD-01: Different session lifecycle patterns — session_manager only calls protocol methods

Success criteria:
* No SDK-specific imports in session_manager.py
* All session operations go through `VoiceSessionProtocol`
* Session lifecycle (create, get, remove) is SDK-agnostic

Dependencies:
* Steps 4.1, 4.2

### Step 4.4: Refactor `src/app/main.py`

Update WebSocket endpoint to use factory + protocol instead of direct SDK.

**Key changes:**
1. Import `create_voice_session` instead of SDK-specific classes
2. WebSocket handler works with `VoiceSessionProtocol`
3. Event forwarding uses `VoiceEvent` types instead of SDK-specific events
4. Listeners are attached at session creation time

```python
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    settings = get_settings()

    listeners = [LoggingVoiceEventListener()]

    session = create_voice_session(settings, tools=tools, listeners=listeners)
    async with session:
        async def forward_events():
            async for event in session.events():
                match event.event_type:
                    case VoiceEventType.AUDIO_DELTA:
                        audio_b64 = base64.b64encode(event.audio).decode()
                        await websocket.send_text(json.dumps({"type": "audio", "audio": audio_b64}))
                    case VoiceEventType.TRANSCRIPT_DELTA:
                        await websocket.send_text(json.dumps({"type": "transcript", "text": event.text}))
                    case VoiceEventType.AGENT_START:
                        await websocket.send_text(json.dumps({"type": "agent_start"}))
                    case VoiceEventType.ERROR:
                        await websocket.send_text(json.dumps({"type": "error", "error": event.error}))

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
```

Files:
* src/app/main.py - Modify existing file

Success criteria:
* No SDK-specific imports in main.py
* WebSocket handler uses `VoiceSessionProtocol` only
* Events are matched on `VoiceEventType` enum values
* Listeners are created and attached at session creation

Dependencies:
* Steps 4.1, 4.2, 4.3

## Implementation Phase 5: Example Listeners

<!-- parallelizable: true -->

### Step 5.1: Create `src/app/voice/listeners/logging_listener.py`

A simple logging listener demonstrating the `VoiceEventListener` protocol:

```python
from __future__ import annotations

import logging

from app.voice.events import VoiceEvent, VoiceEventType

logger = logging.getLogger(__name__)


class LoggingVoiceEventListener:
    """Logs all voice events for debugging and development."""

    async def on_event(self, event: VoiceEvent) -> None:
        match event.event_type:
            case VoiceEventType.AUDIO_DELTA:
                logger.debug("Audio delta: %d bytes", len(event.audio) if event.audio else 0)
            case VoiceEventType.AUDIO_END:
                logger.info("Audio output completed")
            case VoiceEventType.AUDIO_INTERRUPTED:
                logger.info("Audio interrupted by user speech")
            case VoiceEventType.TRANSCRIPT_DELTA:
                logger.info("Transcript: %s", event.text)
            case VoiceEventType.TRANSCRIPT_DONE:
                logger.info("Transcript complete: %s", event.text)
            case VoiceEventType.AGENT_START:
                logger.info("Agent started: %s", event.agent_name)
            case VoiceEventType.AGENT_END:
                logger.info("Agent ended: %s", event.agent_name)
            case VoiceEventType.TOOL_START:
                logger.info("Tool call started: %s", event.tool_name)
            case VoiceEventType.TOOL_CALL_DONE:
                logger.info("Tool call args received: %s args=%s", event.tool_name, event.tool_args)
            case VoiceEventType.TOOL_END:
                logger.info("Tool call ended: %s result=%s", event.tool_name, event.tool_result)
            case VoiceEventType.SESSION_CREATED:
                logger.info("Session created")
            case VoiceEventType.SESSION_UPDATED:
                logger.info("Session updated")
            case VoiceEventType.SPEECH_STARTED:
                logger.info("User speech started")
            case VoiceEventType.SPEECH_STOPPED:
                logger.info("User speech stopped")
            case VoiceEventType.CONVERSATION_ITEM_CREATED:
                logger.debug("Conversation item created")
            case VoiceEventType.CONVERSATION_ITEM_TRUNCATED:
                logger.info("Conversation item truncated")
            case VoiceEventType.ERROR:
                logger.error("Voice session error: %s", event.error)
            case _:
                logger.debug("Voice event: %s", event.event_type)
```

Files:
* src/app/voice/listeners/logging_listener.py - New file

Success criteria:
* `LoggingVoiceEventListener` satisfies `VoiceEventListener` protocol
* All VoiceEventType values handled in match
* Uses Python `logging` module, not print statements

Dependencies:
* Phase 1 (events.py)

### Step 5.2: Create `src/app/voice/listeners/__init__.py`

```python
from app.voice.listeners.logging_listener import LoggingVoiceEventListener

__all__ = ["LoggingVoiceEventListener"]
```

Files:
* src/app/voice/listeners/__init__.py - New file

Success criteria:
* `LoggingVoiceEventListener` importable from `app.voice.listeners`

Dependencies:
* Step 5.1

## Implementation Phase 6: Validation

<!-- parallelizable: false -->

### Step 6.1: Run full project validation

Execute all validation commands for the project:
* `python -m py_compile src/app/voice/events.py` (repeat for all new files)
* `python -c "from app.voice import VoiceEvent, VoiceSessionProtocol"` — verify imports
* Run type checker if configured
* Verify `isinstance(OpenAIAgentsVoiceSession(...), VoiceSessionProtocol)` works at runtime

### Step 6.2: Fix minor validation issues

Iterate on import errors, type errors, and missing __init__.py files. Apply fixes directly when corrections are straightforward and isolated.

### Step 6.3: Report blocking issues

When validation failures require changes beyond minor fixes:
* Document the issues and affected files
* Provide the user with next steps
* Recommend additional research and planning rather than inline fixes

## Dependencies

* `openai-agents>=0.13.0` — OpenAI Agents SDK (required)
* `semantic-kernel[realtime]>=1.41.0` — Semantic Kernel (optional)
* `fastapi>=0.115.0` — WebSocket endpoints
* `pydantic>=2.0.0` — Event models
* `pydantic-settings>=2.0.0` — Configuration
* Python 3.10+ — `typing.Protocol`, `match/case`, `X | Y` union syntax

## Success Criteria

* FastAPI WebSocket handler imports zero SDK-specific classes
* Changing `ORCHESTRATOR` env var switches the backend without code changes
* `VoiceEventListener.on_event()` receives normalized `VoiceEvent` regardless of backend
* Both adapters pass `isinstance(session, VoiceSessionProtocol)` check
* SK adapter gracefully fails with `ImportError` when `semantic-kernel` not installed
