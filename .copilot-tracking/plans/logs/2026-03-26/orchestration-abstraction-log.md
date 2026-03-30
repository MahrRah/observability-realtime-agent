<!-- markdownlint-disable-file -->
# Planning Log: Orchestration Abstraction Layer for Voice Agents

## Discrepancy Log

Gaps and differences identified between research findings and the implementation plan.

### Unaddressed Research Items

* DR-01: SK `SESSION_UPDATED` event has no direct OpenAI Agents SDK counterpart
  * Source: .copilot-tracking/research/subagents/2026-03-26/semantic-kernel-realtime-abstraction-research.md (Lines 112-140)
  * Reason: Included in `VoiceEventType` enum but OpenAI adapter will never emit it — SK-only event. This is expected; not all SDKs emit all event types.
  * Impact: low

* DR-02: SK `ListenEvents` has 28+ event types; only 17 are mapped in the abstraction
  * Source: .copilot-tracking/research/subagents/2026-03-26/semantic-kernel-realtime-abstraction-research.md (Lines 118-145)
  * Reason: The 17 mapped events cover the user-facing interaction model (audio, transcripts, tools, function call arguments, session, conversation items, errors). Low-level protocol events (`RATE_LIMITS_UPDATED`, etc.) are accessible via `raw_event`.
  * Impact: low

* DR-03: SK `audio_output_callback` for low-latency audio playback not exposed in protocol
  * Source: .copilot-tracking/research/subagents/2026-03-26/semantic-kernel-realtime-abstraction-research.md (Lines 30-35)
  * Reason: The protocol exposes audio through the event stream. A callback bypassing the event loop would break the listener pattern. Can be added as an optional protocol extension if latency becomes an issue.
  * Impact: medium

* DR-04: OpenAI Agents SDK `RealtimeHandoffEvent` and `RealtimeGuardrailTripped` not mapped
  * Source: .copilot-tracking/research/subagents/2026-03-26/openai-agents-sdk-voice-research.md (Lines 248-260)
  * Reason: Handoffs and guardrails are SDK-specific features not yet supported in SK. Adding them to the unified enum would create events that only one adapter emits. Accessible via `raw_event`.
  * Impact: low

* DR-05: Microsoft Foundry Agents do not support voice/realtime
  * Source: .copilot-tracking/research/subagents/2026-03-26/openai-agents-sdk-voice-research.md (Lines 300-340)
  * Reason: Foundry Agent Service is text-only. The user mentioned it as "if possible." The Protocol design accommodates a future Foundry adapter if/when voice support is added — the adapter would implement `VoiceSessionProtocol` and map Foundry events to `VoiceEvent`.
  * Impact: low — future work item

* DR-06: SK function calling uses Kernel plugins (different API than OpenAI's `@function_tool`)
  * Source: .copilot-tracking/research/subagents/2026-03-26/semantic-kernel-realtime-abstraction-research.md (Lines 200-230)
  * Reason: The factory function handles this difference — OpenAI tools are `@function_tool` decorated callables; SK tools are added to the Kernel. The `tools` parameter in the factory accepts a generic list and each backend interprets it. This may need refinement for cross-SDK tool portability.
  * Impact: medium

* DR-07: Additional OpenAI Agents SDK events not mapped in VoiceEventType or documented in DR-04
  * Source: .copilot-tracking/research/subagents/2026-03-26/openai-agents-sdk-voice-research.md (session events list)
  * Reason: DR-04 covers `RealtimeHandoffEvent` and `RealtimeGuardrailTripped`, but four additional events are also unmapped and undocumented: `RealtimeToolApprovalRequired` (tool approval workflows), `RealtimeHistoryUpdated` (distinct from `RealtimeHistoryAdded`), `RealtimeRawModelEvent` (raw passthrough), and `RealtimeInputAudioTimeoutTriggered` (input timeout handling). All are accessible via `raw_event`.
  * Impact: low — advanced use cases; accessible via `raw_event`

* DR-08: Step 1.2 success criteria claims "Three protocols defined" including `VoiceSessionFactory`, but code defines only two
  * Source: .copilot-tracking/research/subagents/2026-03-26/semantic-kernel-realtime-abstraction-research.md (Lines 430-445, VoiceSessionFactory protocol)
  * Reason: Research proposes a `VoiceSessionFactory` protocol, and the plan step 1.2 success criteria references it. However, the step 1.2 code only defines `VoiceEventListener` and `VoiceSessionProtocol`. The factory is implemented as a concrete function in Step 4.1 instead. The success criteria is inconsistent with the implementation.
  * Impact: medium — misleading success criteria; implementer may search for a missing protocol definition

* DR-09: Phase 3 lacks a step to update `src/app/voice/adapters/__init__.py` with SK adapter import
  * Source: .copilot-tracking/details/2026-03-26/orchestration-abstraction-details.md Step 2.2 note ("Semantic Kernel import is deferred, added in Phase 3")
  * Reason: Step 2.2 creates `adapters/__init__.py` with only the OpenAI adapter and notes the SK import will be added in Phase 3. However, Phase 3 contains no step to update `adapters/__init__.py`. The factory (Step 4.1) imports the SK adapter directly, so this is not blocking, but the convenience API is incomplete and the deferred note is unfulfilled.
  * Impact: low — not blocking; factory bypasses __init__.py

### Plan Deviations from Research

* DD-01: SDK session lifecycle differs — OpenAI uses `runner.run()` returning a context manager; SK uses `create_session()` / `close_session()`
  * Research recommends: Both patterns documented in subagent research
  * Plan implements: Each adapter wraps its SDK's lifecycle internally, exposing only `connect()` / `disconnect()` / context manager
  * Rationale: The protocol hides lifecycle differences. The adapter pattern is specifically designed for this.

* DD-02: Audio data encoding differs — OpenAI Agents SDK uses raw bytes; SK uses base64-encoded `AudioContent`
  * Research recommends: Document both formats
  * Plan implements: Protocol uses raw bytes (`send_audio(bytes)`, `VoiceEvent.audio: bytes`). SK adapter handles base64 encoding/decoding internally.
  * Rationale: Raw bytes is the more natural representation. The adapter bears the encoding cost.

* DD-03: Tool registration differs — OpenAI uses `@function_tool` decorator; SK uses Kernel plugins
  * Research recommends: Both approaches documented
  * Plan implements: Factory function accepts a generic `tools` list and each backend-specific creator interprets it differently. OpenAI tools are passed directly to `RealtimeAgent(tools=...)`. SK tools are added to a `Kernel`.
  * Rationale: Full tool portability across SDKs is a larger undertaking (different argument schemas, decorators). The current approach defers this — each backend uses its native tool format.

* DD-04: Research proposes `VoiceSessionFactory` protocol; plan uses concrete factory function
  * Research recommends: Define a `VoiceSessionFactory` Protocol with a `create_session()` method (.copilot-tracking/research/subagents/2026-03-26/semantic-kernel-realtime-abstraction-research.md, Lines 430-445)
  * Plan implements: A concrete `create_voice_session()` function in `src/app/voice/factory.py` (Step 4.1) that uses an if/elif branch on `settings.orchestrator`
  * Rationale: A concrete function is simpler for two backends and avoids an unnecessary abstraction layer. If a third backend is added, the function can be refactored to a registry or protocol. However, the deviation is undocumented in the original planning log and the Step 1.2 success criteria still references the dropped `VoiceSessionFactory` protocol.

* DD-05: All 13 plan-to-details line number cross-references are inaccurate
  * Research recommends: N/A (internal plan consistency issue)
  * Plan implements: Line references in the plan checklist (e.g., "Details Lines 19-76" for Step 1.1) do not match actual positions in the details file. Offsets range from -3 to +273 lines. For example, Step 4.1 references "Lines 408-460" but actual content starts at line 617; Step 5.2 references "Lines 662-675" but starts at line 935.
  * Rationale: References appear to have been estimated or calculated against an earlier draft of the details file. Steps are identifiable by their descriptive headers, so navigation is possible but requires searching by name rather than line number.

## Implementation Paths Considered

### Selected: Protocol-Based Abstraction with Adapter Pattern

* Approach: Define `VoiceSessionProtocol` using `typing.Protocol`, implement `OpenAIAgentsVoiceSession` and `SemanticKernelVoiceSession` adapters, use factory for instantiation, attach `VoiceEventListener` instances for cross-cutting concerns.
* Rationale: Protocols provide structural subtyping without forced inheritance. Both SDKs use async generators for events — the protocol mirrors this naturally. Adapters encapsulate SDK differences. Listeners decouple event observation from the session.
* Evidence: .copilot-tracking/research/subagents/2026-03-26/semantic-kernel-realtime-abstraction-research.md (Lines 350-460)

### IP-01: ABC-Based Abstraction

* Approach: Define `VoiceSessionBase` as an abstract base class with abstract methods. Adapters inherit from the ABC.
* Trade-offs: More familiar OOP pattern. Forces inheritance which is awkward when wrapping third-party SDKs. SK already uses its own ABC (`RealtimeClientBase`) — multiple inheritance chains become fragile. Cannot use with classes not designed to inherit from the ABC.
* Rejection rationale: Protocol is strictly more flexible — it allows structural subtyping and works with any class that has the right methods, even if it doesn't inherit from the base.

### IP-02: Event Emitter Pattern (Callback-Only)

* Approach: Instead of `events()` async iterator, use an EventEmitter/PubSub pattern where consumers register callbacks per event type. No async iteration.
* Trade-offs: More flexible routing (subscribe to specific events). Familiar from Node.js EventEmitter pattern. However, breaks the natural async control flow that both SDKs use. Harder to compose with `asyncio.create_task`. Callbacks complicate error handling and backpressure.
* Rejection rationale: Both SDKs are designed around async generators. The protocol should match this pattern. Listeners provide the "subscribe to all events" capability; selective filtering can be implemented in the listener.

### IP-03: Direct SDK Dependency Injection (No Abstraction Layer)

* Approach: Pass the SDK client directly to the WebSocket handler. Each handler function is SDK-specific. Use different FastAPI router modules per SDK.
* Trade-offs: Simplest initial implementation. No abstraction layer to maintain. But duplicates handler logic across SDKs. Adding a third SDK requires a third copy of the handler. No unified event model for observability.
* Rejection rationale: Violates the user's core requirement of being able to "attach listeners" across SDKs. Duplication grows linearly with SDK count.

## Suggested Follow-On Work

Items identified during planning that fall outside current scope.

* WI-01: Cross-SDK tool portability layer — Define a common tool decorator that works with both OpenAI's `@function_tool` and SK's Kernel plugin system (medium priority)
  * Source: DD-03 (tool registration differences)
  * Dependency: Phase 4 completion

* WI-02: Microsoft Foundry Agents adapter (future) — When Foundry adds voice/realtime support, implement `FoundryVoiceSession` adapter (low priority)
  * Source: DR-05 (Foundry has no voice support today)
  * Dependency: Microsoft Foundry Agents gaining realtime voice APIs

* WI-03: OpenTelemetry tracing listener — Implement `OTelVoiceEventListener` that emits spans for session lifecycle, audio duration, tool calls, and latency metrics (high priority)
  * Source: Project name "observability-realtime-agent" implies tracing is core
  * Dependency: Phase 5 completion (listener pattern established)

* WI-04: Event filtering in listeners — Add `event_types: set[VoiceEventType]` filter parameter to `VoiceEventListener` so listeners can subscribe to specific events (low priority)
  * Source: Subagent clarifying question #2
  * Dependency: Phase 5 completion

* WI-05: Low-latency audio callback path — Add optional `audio_callback` to protocol for bypassing the event loop for audio playback (medium priority)
  * Source: DR-03 (SK `audio_output_callback` not exposed)
  * Dependency: Phase 1 completion (protocol extension)

* WI-06: Integration tests with mock voice sessions — Create test fixtures that simulate VoiceSessionProtocol for testing WebSocket handler and listeners without Azure dependencies (high priority)
  * Source: Testability benefit of Protocol pattern
  * Dependency: Phase 4 completion
