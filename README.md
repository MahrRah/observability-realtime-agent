# Real-Time Voice Agent with Observability

A sample project demonstrating a real-time voice agent with end-to-end OpenTelemetry
observability. Built with the OpenAI Agents SDK, Azure OpenAI Realtime API, Azure
Monitor, and a browser-based frontend.

## Architecture

```text
Browser (WebSocket) → FastAPI Server (RealtimeRunner) → Azure OpenAI Realtime API
                                 │
                          OpenTelemetry
                       (traces + metrics)
                                 │
                        Azure Monitor /
                     Application Insights
```

The server acts as a relay: microphone audio flows from the browser through
FastAPI to Azure OpenAI; agent audio and transcripts flow back. Every session,
response, tool call, and error is instrumented with distributed traces and
metrics exported to Application Insights via `azure-monitor-opentelemetry`.

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- Azure CLI (`az`) logged in
- Azure OpenAI resource with a `gpt-4o-realtime-preview` deployment
- Entra ID identity with **Cognitive Services OpenAI User** role on the resource
- Modern browser (Chrome 74+, Edge 79+, Firefox 76+, Safari 14.1+)

## Setup

### 1. Deploy Azure Resources

The included `provision.sh` script creates the resource group, deploys the Bicep
template, and writes a `.env` file with the outputs:

```bash
./provision.sh
```

You can override defaults with environment variables:

```bash
RESOURCE_GROUP=my-rg LOCATION=eastus2 OPENAI_ACCOUNT_NAME=my-oai ./provision.sh
```

Alternatively, deploy manually:

```bash
az deployment group create \
  --resource-group <your-rg> \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam
```

### 2. Configure Environment

If you used `provision.sh`, the `.env` file is already populated. Otherwise,
copy the example and fill in your values:

```bash
cp .env.example .env
```

Authentication uses `AzureCliCredential`, so make sure you are logged in with
`az login`.

### 3. Install and Run

```bash
uv venv
uv sync
uv run uvicorn app.main:app --reload --env-file .env
```

### 4. Open Browser

Navigate to `http://localhost:8000` and click **Connect**.

## Project Structure

```text
├── infra/                        # Bicep IaC for Azure OpenAI + App Insights
├── src/app/                      # FastAPI server + agent
│   ├── main.py                   # WebSocket endpoint + lifespan
│   ├── config.py                 # Pydantic settings
│   ├── agent.py                  # RealtimeAgent + tools
│   ├── constants/                # Observability & event-type constants
│   │   ├── realtime_event_types.py
│   │   └── observability/
│   │       ├── attributes.py     # OTel attribute keys
│   │       ├── metric.py         # Metric names
│   │       └── span.py           # Span names
│   └── listener/
│       ├── telemetry_context.py  # OTel span context management
│       ├── telemetry_listener.py # OTel traces + metrics listener
│       └── websocket_handler.py  # Browser WebSocket relay
├── static/                       # Browser frontend
│   ├── index.html                # UI + audio logic
│   └── audio-processor.js        # AudioWorklet
├── provision.sh                  # One-step Azure provisioning
├── pyproject.toml                # Dependencies
└── .env.example                  # Environment template
```
