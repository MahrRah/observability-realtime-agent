---
applyTo: '.copilot-tracking/changes/2026-03-30/direct-openai-voice-agent-changes.md'
---
<!-- markdownlint-disable-file -->
# Implementation Plan: Direct OpenAI Voice Agent (Stage 1)

## Overview

Build the end-to-end voice agent sample using OpenAI Agents SDK directly — FastAPI server, Bicep IaC, and browser frontend — with no abstraction layer. This is Stage 1; the orchestration abstraction (VoiceEvent, VoiceSessionProtocol, Semantic Kernel adapter) follows as Stage 2.

## Objectives

### User Requirements

* Build a working voice agent with OpenAI Agents SDK + FastAPI + Pydantic — Source: user conversation
* Deploy Azure OpenAI realtime model via Bicep IaC — Source: user conversation
* Browser frontend for microphone audio input — Source: user conversation
* Get it running first, abstract later — Source: user conversation (2026-03-30)

### Derived Objectives

* Use the reference implementation pattern from `openai/openai-agents-python/examples/realtime/` as the baseline — Derived from: research confirms this is the production-ready pattern
* Keep the server minimal so the abstraction refactor (Stage 2) has a clean target — Derived from: planning ahead for Stage 2 without over-engineering Stage 1
* Wire basic event logging (Python `logging`) for observability groundwork — Derived from: project name "observability-realtime-agent"

## Context Summary

### Research

* .copilot-tracking/research/2026-03-26/voice-agent-sample-research.md — consolidated research with full code examples, selected architecture, project structure
* .copilot-tracking/research/subagents/2026-03-26/openai-agents-sdk-voice-research.md — RealtimeAgent/RealtimeRunner API details
* .copilot-tracking/research/subagents/2026-03-26/bicep-azure-openai-realtime-research.md — Bicep templates
* .copilot-tracking/research/subagents/2026-03-26/browser-audio-frontend-research.md — AudioWorklet patterns
* .copilot-tracking/research/subagents/2026-03-26/fastapi-websocket-voice-server-research.md — FastAPI relay patterns

### Stage 2 Reference

* .copilot-tracking/plans/2026-03-26/orchestration-abstraction-plan.instructions.md — the abstraction plan to implement after Stage 1
* .copilot-tracking/details/2026-03-26/orchestration-abstraction-details.md — VoiceEvent, protocols, adapters, factory

### Project Files (all new)

* src/app/main.py — FastAPI app + WebSocket endpoint
* src/app/config.py — Pydantic settings
* src/app/agent.py — RealtimeAgent + tools
* src/app/realtime_listener.py — Event listener for errors + conversation items
* static/index.html — Browser UI
* static/audio-processor.js — AudioWorklet processor
* infra/main.bicep — Azure OpenAI + realtime model
* infra/main.bicepparam — Parameter file
* pyproject.toml — Dependencies
* .env.example — Environment variable template

## Implementation Checklist

### [x] Implementation Phase 1: Project Scaffold and Config

<!-- parallelizable: true -->

* [x] Step 1.1: Create `pyproject.toml` with dependencies
  * Details: .copilot-tracking/details/2026-03-30/direct-openai-voice-agent-details.md § Step 1.1
* [x] Step 1.2: Create `src/app/__init__.py` (empty)
  * Details: .copilot-tracking/details/2026-03-30/direct-openai-voice-agent-details.md § Step 1.2
* [x] Step 1.3: Create `src/app/config.py` — Pydantic settings
  * Details: .copilot-tracking/details/2026-03-30/direct-openai-voice-agent-details.md § Step 1.3
* [x] Step 1.4: Create `.env.example`
  * Details: .copilot-tracking/details/2026-03-30/direct-openai-voice-agent-details.md § Step 1.4
* [x] Step 1.5: Create `.gitignore`
  * Details: .copilot-tracking/details/2026-03-30/direct-openai-voice-agent-details.md § Step 1.5

### [x] Implementation Phase 2: Agent and Server

<!-- parallelizable: false -->

* [x] Step 2.1: Create `src/app/agent.py` — RealtimeAgent + example tools
  * Details: .copilot-tracking/details/2026-03-30/direct-openai-voice-agent-details.md § Step 2.1
* [x] Step 2.2: Create `src/app/main.py` — FastAPI app + WebSocket relay
  * Details: .copilot-tracking/details/2026-03-30/direct-openai-voice-agent-details.md § Step 2.2
* [x] Step 2.3: Create `src/app/realtime_listener.py` — Event listener for errors and conversation items
  * Details: .copilot-tracking/details/2026-03-30/direct-openai-voice-agent-details.md § Step 2.3

### [x] Implementation Phase 3: Browser Frontend

<!-- parallelizable: true -->

* [x] Step 3.1: Create `static/audio-processor.js` — AudioWorklet processor
  * Details: .copilot-tracking/details/2026-03-30/direct-openai-voice-agent-details.md § Step 3.1
* [x] Step 3.2: Create `static/index.html` — Browser UI with audio capture and playback
  * Details: .copilot-tracking/details/2026-03-30/direct-openai-voice-agent-details.md § Step 3.2

### [x] Implementation Phase 4: Infrastructure as Code

<!-- parallelizable: true -->

* [x] Step 4.1: Create `infra/main.bicep` — Azure OpenAI + realtime model deployment
  * Details: .copilot-tracking/details/2026-03-30/direct-openai-voice-agent-details.md § Step 4.1
* [x] Step 4.2: Create `infra/main.bicepparam` — Parameter file
  * Details: .copilot-tracking/details/2026-03-30/direct-openai-voice-agent-details.md § Step 4.2

### [x] Implementation Phase 5: Documentation

<!-- parallelizable: true -->

* [x] Step 5.1: Create `README.md` — Setup, usage, and architecture
  * Details: .copilot-tracking/details/2026-03-30/direct-openai-voice-agent-details.md § Step 5.1

### [x] Implementation Phase 6: Validation

<!-- parallelizable: false -->

* [x] Step 6.1: Verify Python imports and syntax
  * `cd src && python -m py_compile app/main.py`
  * `cd src && python -m py_compile app/config.py`
  * `cd src && python -m py_compile app/agent.py`
  * `cd src && python -m py_compile app/realtime_listener.py`
* [x] Step 6.2: Verify Bicep linting — skipped (az cli not required for Stage 1)
* [x] Step 6.3: Fix minor validation issues — none found
* [x] Step 6.4: Report blocking issues — none

## Planning Log

See .copilot-tracking/plans/logs/2026-03-30/direct-openai-voice-agent-log.md for discrepancy tracking, staging strategy rationale, and follow-on work.

## Dependencies

* `openai-agents>=0.13.0` with `[voice]` extra — RealtimeAgent + RealtimeRunner
* `fastapi>=0.115.0` — WebSocket endpoints
* `uvicorn[standard]>=0.30.0` — ASGI server
* `pydantic-settings>=2.0.0` — Environment config
* Python 3.10+
* Azure OpenAI with realtime model (deployed via Bicep)
* Modern browser with AudioWorklet support

## Success Criteria

* `uvicorn app.main:app` starts the server without errors — Traces to: working sample
* Browser connects via WebSocket, sends audio, receives agent audio and transcripts — Traces to: end-to-end voice interaction
* Bicep deploys Azure OpenAI with realtime model — Traces to: IaC requirement
* No abstraction layer code exists in Stage 1 (no `voice/` module, no VoiceEvent, no protocols) — Traces to: "start direct, abstract later"
* Stage 2 plan (.copilot-tracking/plans/2026-03-26/orchestration-abstraction-plan.instructions.md) remains intact and references the files created here — Traces to: clean refactor path
