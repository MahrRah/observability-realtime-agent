from __future__ import annotations

import json
import logging
import struct
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from agents.realtime import RealtimeInputAudioTranscriptionConfig, RealtimeRunner
from azure.identity.aio import AzureCliCredential
from azure.monitor.opentelemetry import configure_azure_monitor
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from opentelemetry import trace
from opentelemetry.instrumentation.openai_agents_realtime import OpenAIAgentsRealtimeInstrumentor

from app.agent import create_agent
from app.config import AppSettings, ServerSettings
from app.listener import WebSocketEventHandler

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s \033[1m%(name)s\033[0m  —  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("azure.monitor.opentelemetry.exporter.export._base").setLevel(logging.WARNING)

configure_azure_monitor()

OpenAIAgentsRealtimeInstrumentor().instrument()

TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Eagerly acquire a token so the first WebSocket connection isn't delayed."""
    _app.state.settings = AppSettings()
    logger.info("Warming up Azure credential...")
    async with AzureCliCredential() as credential:
        token = await credential.get_token(TOKEN_SCOPE)
        _app.state.access_token = token.token
    logger.info("Credential ready.")
    yield


app = FastAPI(title="Voice Agent", lifespan=lifespan)


@app.websocket("/ws/{session_id}")
@tracer.start_as_current_span("websocket_session", kind=trace.SpanKind.SERVER)
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    trace.get_current_span().set_attribute("session.id", session_id)
    settings = app.state.settings

    agent = create_agent(
        instructions=settings.agent_instructions,
    )

    runner = RealtimeRunner(agent)
    access_token = app.state.access_token
    model_config: dict[str, Any] = {
        "url": settings.azure_realtime_url,
        "headers": {"Authorization": f"Bearer {access_token}"},
        "initial_model_settings": {
            "voice": settings.voice,
            "modalities": ["audio"],
            "output_audio_format": "pcm16",
            "input_audio_format": "pcm16",
            "input_audio_transcription": RealtimeInputAudioTranscriptionConfig(model="whisper-1"),
        },
    }

    session = await runner.run(model_config=model_config)
    async with session:
        logger.info("Session %s starting", session_id)
        ws_handler = WebSocketEventHandler(websocket, session_id)
        session.model.add_listener(ws_handler)

        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)
                if msg.get("type") == "audio":
                    audio_data: list[int] = msg["data"]
                    audio_bytes = struct.pack(f"{len(audio_data)}h", *audio_data)
                    await session.send_audio(audio_bytes)
        except WebSocketDisconnect:
            logger.info("Session %s: browser disconnected", session_id)
    logger.info("Session %s: session closed", session_id)


# Serve static files (browser frontend) — must be last
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    server = ServerSettings()
    uvicorn.run("app.main:app", host=server.host, port=server.port, reload=True)
