<!-- markdownlint-disable-file -->
# Planning Log: Direct OpenAI Voice Agent (Stage 1) + Staging Strategy

## Discrepancy Log

### Unaddressed Research Items

* DR-01: OpenTelemetry tracing not included in Stage 1
  * Source: .copilot-tracking/research/2026-03-26/voice-agent-sample-research.md (Potential Next Research)
  * Reason: Deferred to follow-on work. Stage 1 uses Python `logging` for basic observability. OTel integration is better added alongside the abstraction layer (Stage 2) where the listener pattern provides a natural hook.
  * Impact: low — logging provides baseline observability

* DR-02: Azure Entra ID auth not included (API key only)
  * Source: .copilot-tracking/research/2026-03-26/voice-agent-sample-research.md (Potential Next Research)
  * Reason: API key auth is simpler for a sample project and sufficient for getting started. Entra ID can be added later by replacing `azure_headers` with a token provider.
  * Impact: low — acceptable for dev/sample

* DR-03: No session manager class in Stage 1
  * Source: .copilot-tracking/research/subagents/2026-03-26/fastapi-websocket-voice-server-research.md (RealtimeWebSocketManager)
  * Reason: Single-session-per-connection pattern in the WebSocket endpoint is sufficient. The reference `RealtimeWebSocketManager` pattern adds complexity without benefit for the sample's scope. Stage 2 adds `VoiceSessionManager` as part of the factory integration.
  * Impact: low — session cleanup handled in `finally` block

* DR-04: Audio chunk format uses JSON array instead of base64
  * Source: .copilot-tracking/research/subagents/2026-03-26/browser-audio-frontend-research.md (recommends base64)
  * Reason: The reference implementation uses `struct.pack` on a JSON int array. This is bandwidth-inefficient (~4x overhead vs base64) but keeps the code clear and matches the OpenAI SDK examples. Can be optimized in Stage 2 or as a follow-on.
  * Impact: medium — higher bandwidth but acceptable for development

* DR-05: No audio level visualization in Stage 1
  * Source: .copilot-tracking/research/subagents/2026-03-26/browser-audio-frontend-research.md (Audio Level Visualization)
  * Reason: Nice-to-have UI feature. The research provides the pattern with `AnalyserNode`. Deferred to follow-on work to keep Stage 1 minimal.
  * Impact: low — cosmetic

### Plan Deviations from Research

* DD-01: No Pydantic models for WebSocket messages
  * Research recommends: `AudioMessage`, `TranscriptEvent`, `ErrorEvent` Pydantic models
  * Plan implements: Plain dict + json.dumps/loads for WebSocket messages
  * Rationale: Pydantic validation adds ceremony without safety benefit for an internal WebSocket protocol between our own frontend and backend. The message shapes are simple. Can be added if the protocol grows more complex.

* DD-02: Event handling inlined in main.py instead of separate module
  * Research recommends: Separate event handling module
  * Plan implements: `_handle_event()` function in main.py
  * Rationale: Single file is more approachable for a sample. Stage 2 naturally extracts this into the adapter's `_map_event()` method.

* DD-03: Package layout — pyproject.toml needs `[tool.setuptools.packages.find]` with `where = ["src"]`
  * Research recommends: N/A (internal consistency issue)
  * Plan implements: Added `[tool.setuptools.packages.find]` section. Uvicorn command is `uvicorn app.main:app` (not `src.app.main:app`). Imports use `from app.agent` which resolves correctly when `src/` is on the path via the find config.
  * Rationale: Standard setuptools `src` layout. Detected by plan validator, remediated.

* DD-03: Missing pyproject.toml setuptools src layout config and inconsistent uvicorn module path
  * Research recommends: `src/app/` project structure (Scenario 4) with functional `pip install -e .` and working `uvicorn` command
  * Plan implements: `src/app/` layout with imports `from app.agent import create_agent` (correct for src layout) but uvicorn command `uvicorn src.app.main:app` (incorrect for src layout) and no `[tool.setuptools.packages.find]` in pyproject.toml to register `src/` as the package root
  * Rationale: None — this is a defect. The `__main__` block in main.py correctly uses `"app.main:app"`, but the plan's success criteria, README, and validation steps all reference `uvicorn src.app.main:app`. Without `[tool.setuptools.packages.find]` with `where = ["src"]` in pyproject.toml, `pip install -e .` will not discover the `app` package, and the `from app.agent` / `from app.config` imports will fail at runtime. **Fix required in Step 1.1 (pyproject.toml) and all uvicorn references.**

## Staging Strategy

### Stage 1: Direct OpenAI Implementation (this plan)

**Goal:** Get a working end-to-end voice agent with minimal abstraction.

Files created:
* pyproject.toml, .env.example, .gitignore — project scaffold
* src/app/__init__.py, config.py, agent.py, main.py — server
* static/index.html, audio-processor.js — frontend
* infra/main.bicep, main.bicepparam — IaC
* README.md — documentation

**SDK coupling:** `main.py` directly imports and uses `RealtimeRunner`, `RealtimeSession`, and all typed event classes. This is intentional — the code is simple and readable.

### Stage 2: Orchestration Abstraction (existing plan from 2026-03-26)

**Goal:** Refactor to enable SDK swapping and event listeners.

**Prerequisite:** Stage 1 complete.

**Plan:** .copilot-tracking/plans/2026-03-26/orchestration-abstraction-plan.instructions.md
**Details:** .copilot-tracking/details/2026-03-26/orchestration-abstraction-details.md

**Key refactors:**
1. Create `src/app/voice/` module (events.py, protocols.py, adapters/, factory.py, listeners/)
2. `main.py` → replace `RealtimeRunner`/`RealtimeSession` with `create_voice_session()`
3. `_handle_event()` in main.py → becomes unnecessary; events consumed via `session.events()` + `VoiceEventType` match
4. `agent.py` → unchanged; `create_agent()` is called by the factory

**What stays the same:**
* Frontend (static/) — no changes; WebSocket message format is the contract
* IaC (infra/) — no changes
* Config (config.py) — adds `orchestrator` field
* pyproject.toml — adds optional `semantic-kernel[realtime]` dependency group

## Implementation Paths Considered

### Selected: Two-Stage Approach (Direct → Abstract)

* Approach: Build working sample first with direct SDK usage, then refactor to add abstraction
* Rationale: User explicitly requested "start with OpenAI, abstract later." This approach provides a working demo faster and validates the architecture before adding complexity. The abstraction plan already exists in full detail from 2026-03-26.
* Evidence: User conversation (2026-03-30)

### IP-01: Abstraction-First (Original Plan)

* Approach: Build the abstraction layer simultaneously with the first implementation
* Trade-offs: Cleaner architecture from day 1, but slower to get a working demo. Risk of over-engineering abstractions before understanding real usage patterns.
* Rejection rationale: User preference for incremental approach. The abstraction plan is preserved as Stage 2.

### IP-02: Never Abstract (Keep Direct SDK)

* Approach: Use OpenAI Agents SDK directly and only add SK support by duplicating the endpoint
* Trade-offs: Simplest forever. But violates user's stated goal of SDK-swappable orchestration and misses the observability benefit of unified event listeners.
* Rejection rationale: Contradicts user requirements.

## Suggested Follow-On Work

* WI-01: OpenTelemetry tracing listener — Add OTel spans for session lifecycle, audio duration, tool calls (high priority)
  * Source: DR-01, project name "observability-realtime-agent"
  * Dependency: Stage 2 completion (listener pattern required)

* WI-02: Base64 audio encoding optimization — Replace JSON int array with base64 for WebSocket audio transport (low priority)
  * Source: DR-04
  * Dependency: None (can be done in Stage 1 or Stage 2)

* WI-03: Azure Entra ID authentication — Replace API key with managed identity / token auth (medium priority)
  * Source: DR-02
  * Dependency: None

* WI-04: Audio level visualization — Add real-time audio level meter to the frontend UI (low priority)
  * Source: DR-05
  * Dependency: None

* WI-05: Multi-agent handoff demo — Add a second RealtimeAgent with handoff to demonstrate the SDK's multi-agent capabilities (medium priority)
  * Source: .copilot-tracking/research/subagents/2026-03-26/openai-agents-sdk-voice-research.md
  * Dependency: Stage 1 completion
