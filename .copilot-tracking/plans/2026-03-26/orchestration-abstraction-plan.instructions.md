---
applyTo: '.copilot-tracking/changes/2026-03-26/orchestration-abstraction-changes.md'
---
<!-- markdownlint-disable-file -->
# Implementation Plan: Orchestration Abstraction Layer for Voice Agents (Stage 2)

> **Prerequisite:** Stage 1 (direct OpenAI voice agent) must be implemented first.
> See .copilot-tracking/plans/2026-03-30/direct-openai-voice-agent-plan.instructions.md
>
> This plan refactors the Stage 1 codebase to add a Protocol-based abstraction layer.
> The key refactor targets are:
> * `src/app/main.py` — replace direct SDK usage with `create_voice_session()` factory
> * `src/app/agent.py` — stays unchanged; agent definition is SDK-specific by design
> * New `src/app/voice/` module — events, protocols, adapters, factory, listeners

## Overview

Introduce a Protocol-based orchestration abstraction that decouples the voice agent relay server from any single SDK, enabling swappable backends (OpenAI Agents SDK, Semantic Kernel, future Microsoft Foundry Agents) with a unified event listener system.

## Objectives

### User Requirements

* Abstract the orchestration so switching from OpenAI Agents SDK to Semantic Kernel or Microsoft Foundry Agents is possible without rewriting the server — Source: user conversation
* Support an event listener pattern that works across all SDKs — Source: user conversation ("attach listeners like for the open ai agents sdk")
* Reference Semantic Kernel contact center pattern (`routes/call.py`) as an example of the SK integration approach — Source: user-provided link

### Derived Objectives

* Define a unified `VoiceEvent` model and `VoiceEventType` enum normalizing events across SDKs — Derived from: both SDKs emit different event types for the same concepts (audio delta, transcript, tool calls, etc.)
* Use `typing.Protocol` for the session interface instead of ABC — Derived from: SK already uses ABC (`RealtimeClientBase`); Protocols allow structural subtyping without forced inheritance and work better for adapter patterns
* Implement adapters for OpenAI Agents SDK and Semantic Kernel that wrap SDK-specific session objects behind the unified protocol — Derived from: the two SDKs have different class hierarchies, method names, and event types
* Design a `VoiceEventListener` protocol for attaching cross-cutting concerns (observability, logging, metrics) to any session — Derived from: user's desire to "attach listeners" and the observability focus of the project
* Provide a factory-based session creation pattern so the active SDK is selected via configuration — Derived from: swapping backends should be a config change, not a code change
* Keep the FastAPI WebSocket endpoint SDK-agnostic by depending only on the protocol, not concrete implementations — Derived from: clean separation of concerns

## Context Summary

### Project Files

* src/app/main.py - FastAPI application with WebSocket endpoint (to be refactored to use protocols)
* src/app/config.py - Pydantic BaseSettings (to be extended with `orchestrator` field)
* src/app/models.py - Pydantic message models (WebSocket messages)
* src/app/agent.py - OpenAI Agents SDK RealtimeAgent + tools (to become one of two adapters)
* src/app/session_manager.py - WebSocket relay manager (to depend on protocols, not SDK)

### References

* .copilot-tracking/research/subagents/2026-03-26/semantic-kernel-realtime-abstraction-research.md - SK realtime API, event model comparison, Protocol design, adapter examples
* .copilot-tracking/research/subagents/2026-03-26/openai-agents-sdk-voice-research.md - OpenAI Agents SDK RealtimeAgent/RealtimeSession event types and session lifecycle
* .copilot-tracking/research/subagents/2026-03-26/fastapi-websocket-voice-server-research.md - FastAPI WebSocket relay patterns, reference implementation analysis
* .copilot-tracking/research/2026-03-26/voice-agent-sample-research.md - Consolidated research with selected architecture

### Standards References

* Python `typing.Protocol` docs — structural subtyping without inheritance
* Pydantic `BaseModel` — used for `VoiceEvent` data model
* OpenAI Agents SDK events — `RealtimeAudio`, `RealtimeAudioEnd`, `RealtimeAgentStartEvent`, `RealtimeToolStart`, etc.
* Semantic Kernel events — `RealtimeAudioEvent`, `RealtimeTextEvent`, `RealtimeFunctionCallEvent`, `ListenEvents` enum

## Implementation Checklist

### [ ] Implementation Phase 1: Core Protocols and Event Model

<!-- parallelizable: true -->

* [ ] Step 1.1: Create `src/app/voice/events.py` — `VoiceEventType` enum and `VoiceEvent` dataclass
  * Details: .copilot-tracking/details/2026-03-26/orchestration-abstraction-details.md § Step 1.1
* [ ] Step 1.2: Create `src/app/voice/protocols.py` — `VoiceSessionProtocol`, `VoiceEventListener`
  * Details: .copilot-tracking/details/2026-03-26/orchestration-abstraction-details.md § Step 1.2
* [ ] Step 1.3: Create `src/app/voice/__init__.py` — public API re-exports
  * Details: .copilot-tracking/details/2026-03-26/orchestration-abstraction-details.md § Step 1.3

### [ ] Implementation Phase 2: OpenAI Agents SDK Adapter

<!-- parallelizable: true -->

* [ ] Step 2.1: Create `src/app/voice/adapters/openai_agents.py` — `OpenAIAgentsVoiceSession` implementing `VoiceSessionProtocol`
  * Details: .copilot-tracking/details/2026-03-26/orchestration-abstraction-details.md § Step 2.1
* [ ] Step 2.2: Create `src/app/voice/adapters/__init__.py` — adapter re-exports
  * Details: .copilot-tracking/details/2026-03-26/orchestration-abstraction-details.md § Step 2.2

### [ ] Implementation Phase 3: Semantic Kernel Adapter

<!-- parallelizable: true -->

* [ ] Step 3.1: Create `src/app/voice/adapters/semantic_kernel.py` — `SemanticKernelVoiceSession` implementing `VoiceSessionProtocol`
  * Details: .copilot-tracking/details/2026-03-26/orchestration-abstraction-details.md § Step 3.1
* [ ] Step 3.2: Update `pyproject.toml` — add `semantic-kernel[realtime]` as optional dependency
  * Details: .copilot-tracking/details/2026-03-26/orchestration-abstraction-details.md § Step 3.2

### [ ] Implementation Phase 4: Factory, Config, and Server Integration

<!-- parallelizable: false -->

* [ ] Step 4.1: Create `src/app/voice/factory.py` — `create_voice_session()` factory function selecting adapter from config
  * Details: .copilot-tracking/details/2026-03-26/orchestration-abstraction-details.md § Step 4.1
* [ ] Step 4.2: Update `src/app/config.py` — add `orchestrator: Literal["openai-agents", "semantic-kernel"]` field
  * Details: .copilot-tracking/details/2026-03-26/orchestration-abstraction-details.md § Step 4.2
* [ ] Step 4.3: Refactor `src/app/session_manager.py` — replace SDK-specific code with protocol-based session management
  * Details: .copilot-tracking/details/2026-03-26/orchestration-abstraction-details.md § Step 4.3
* [ ] Step 4.4: Refactor `src/app/main.py` — WebSocket endpoint uses factory + protocol, not direct SDK
  * Details: .copilot-tracking/details/2026-03-26/orchestration-abstraction-details.md § Step 4.4

### [ ] Implementation Phase 5: Example Listeners

<!-- parallelizable: true -->

* [ ] Step 5.1: Create `src/app/voice/listeners/logging_listener.py` — `LoggingVoiceEventListener` for debug/dev output
  * Details: .copilot-tracking/details/2026-03-26/orchestration-abstraction-details.md § Step 5.1
* [ ] Step 5.2: Create `src/app/voice/listeners/__init__.py` — listener re-exports
  * Details: .copilot-tracking/details/2026-03-26/orchestration-abstraction-details.md § Step 5.2

### [ ] Implementation Phase 6: Validation

<!-- parallelizable: false -->

* [ ] Step 6.1: Run full project validation
  * Execute lint and type checking (`pyright` or `mypy`) on all new files
  * Verify imports resolve correctly across the voice module
  * Verify pyproject.toml dependencies are correct
* [ ] Step 6.2: Fix minor validation issues
  * Iterate on lint errors, type errors, and import issues
  * Apply fixes directly when corrections are straightforward
* [ ] Step 6.3: Report blocking issues
  * Document issues requiring additional research
  * Provide user with next steps and recommended follow-on planning

## Planning Log

See .copilot-tracking/plans/logs/2026-03-26/orchestration-abstraction-log.md for discrepancy tracking, implementation paths considered, and suggested follow-on work.

## Dependencies

* `openai-agents>=0.13.0` — OpenAI Agents SDK with RealtimeAgent/RealtimeRunner
* `semantic-kernel[realtime]>=1.41.0` — Semantic Kernel with realtime audio support (optional dependency)
* `fastapi>=0.115.0` — WebSocket endpoints
* `pydantic>=2.0.0` — Event models and settings
* `pydantic-settings>=2.0.0` — Configuration management
* Python 3.10+ — required for `typing.Protocol`, `match/case`, type union syntax

## Success Criteria

* The FastAPI WebSocket endpoint (`main.py`) depends only on `VoiceSessionProtocol` — not on any SDK-specific classes — Traces to: user requirement for SDK-swappable orchestration
* Switching from OpenAI Agents SDK to Semantic Kernel requires only changing `ORCHESTRATOR=semantic-kernel` in `.env` — Traces to: user requirement for easy switching
* `VoiceEventListener` instances attached to a session receive all normalized events regardless of backend SDK — Traces to: user requirement for attachable listeners
* Both adapters map their SDK's events to the unified `VoiceEvent` model with `VoiceEventType` — Traces to: derived objective for consistent event normalization
* `VoiceEvent.raw_event` preserves the original SDK event for advanced consumers — Traces to: research finding that raw event access is sometimes needed
