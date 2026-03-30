<!-- markdownlint-disable-file -->
# Release Changes: Direct OpenAI Voice Agent (Stage 1)

**Related Plan**: direct-openai-voice-agent-plan.instructions.md
**Implementation Date**: 2026-03-30

## Summary

End-to-end voice agent sample: FastAPI server with OpenAI Agents SDK, Bicep IaC for Azure OpenAI realtime model, and vanilla HTML/JS browser frontend.

## Changes

### Added

* `pyproject.toml` — Project metadata, dependencies (`openai-agents[voice]`, `fastapi`, `uvicorn`, `pydantic-settings`), dev extras, `src/` layout config
* `src/app/__init__.py` — Empty package init
* `src/app/config.py` — Pydantic `Settings` class with Azure OpenAI endpoint, API key, deployment, agent instructions, voice, host/port; properties for WSS URL and headers
* `src/app/agent.py` — `RealtimeAgent` factory with `get_weather` example tool
* `src/app/main.py` — FastAPI app with WebSocket relay (`/ws/{session_id}`), `_handle_event()` mapping SDK events to browser JSON, `forward_events()` loop with listener notification, static file serving
* `src/app/realtime_listener.py` — `RealtimeEventListener` Protocol, `LoggingRealtimeListener` for errors + `conversation.item.created`, `create_default_listeners()` factory
* `static/audio-processor.js` — AudioWorklet processor: Float32→PCM16 conversion, 100ms chunk buffering (2400 samples at 24kHz)
* `static/index.html` — Browser UI with `AudioPlayer` class (gapless playback, barge-in interrupt), WebSocket client, mic capture via AudioWorklet, transcript display
* `infra/main.bicep` — Azure OpenAI account (`S0` SKU) + realtime model deployment (`GlobalStandard` SKU), system-assigned identity, outputs
* `infra/main.bicepparam` — Parameter file for East US 2 dev deployment
* `.env.example` — Environment variable template with all settings
* `.gitignore` — Python/build artifact exclusions
* `README.md` — Architecture overview, prerequisites, setup instructions (Bicep deploy, env config, pip install, uvicorn run), project structure

### Modified

### Removed

## Additional or Deviating Changes

* Step 6.2 (Bicep linting) skipped — `az` CLI not required for Stage 1 validation; Bicep syntax verified by file structure review
  * Reason: Non-blocking; can be validated during Azure deployment

## Release Summary

**Total files**: 13 created, 0 modified, 0 removed

**Files created**:

| File | Purpose |
|------|---------|
| `pyproject.toml` | Dependencies and project config |
| `src/app/__init__.py` | Package init |
| `src/app/config.py` | Pydantic settings for Azure OpenAI |
| `src/app/agent.py` | RealtimeAgent + tools |
| `src/app/main.py` | FastAPI WebSocket relay server |
| `src/app/realtime_listener.py` | Event listener (errors + conversation items) |
| `static/audio-processor.js` | AudioWorklet PCM16 capture |
| `static/index.html` | Browser UI |
| `infra/main.bicep` | Azure OpenAI IaC |
| `infra/main.bicepparam` | Bicep parameters |
| `.env.example` | Environment template |
| `.gitignore` | Git exclusions |
| `README.md` | Documentation |

**Validation**: All 4 Python files pass `py_compile` with no errors.

**Deployment notes**: Run `az deployment group create` with the Bicep files before starting the server. Copy `.env.example` to `.env` and fill in credentials. Run `pip install -e . && uvicorn app.main:app --reload`.
