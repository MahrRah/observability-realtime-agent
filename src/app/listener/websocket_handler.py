"""Handler for forwarding realtime session events to a browser WebSocket."""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.realtime.model import RealtimeModelListener
from agents.realtime.model_events import RealtimeModelEvent
from agents.realtime.openai_realtime import get_server_event_type_adapter
from fastapi import WebSocket

from app.constants.realtime_event_types import RealtimeEventType

logger = logging.getLogger(__name__)


class WebSocketEventHandler(RealtimeModelListener):
    """Forwards RealtimeModel events to a browser WebSocket."""

    def __init__(self, websocket: WebSocket, session_id: str) -> None:
        self.ws = websocket
        self.session_id = session_id

    async def on_event(self, event: RealtimeModelEvent) -> None:
        """Route incoming realtime events to appropriate handler."""
        if event.type != "raw_server_event":
            return

        parsed_event = get_server_event_type_adapter().validate_python(event.data)

        match parsed_event.type:
            case RealtimeEventType.AUDIO_DELTA:
                await self._send({"type": RealtimeEventType.AUDIO_DELTA, "delta": parsed_event.delta})

            case RealtimeEventType.AUDIO_DONE:
                await self._send({"type": RealtimeEventType.AUDIO_DONE})

            case RealtimeEventType.SPEECH_STARTED:
                await self._send({"type": RealtimeEventType.SPEECH_STARTED})

            case RealtimeEventType.TRANSCRIPT_DELTA:
                await self._send(
                    {
                        "type": RealtimeEventType.TRANSCRIPT_DELTA,
                        "delta": parsed_event.delta,
                    }
                )

            case RealtimeEventType.TRANSCRIPT_DONE:
                await self._send(
                    {
                        "type": RealtimeEventType.TRANSCRIPT_DONE,
                        "transcript": parsed_event.transcript,
                    }
                )

            case RealtimeEventType.INPUT_TRANSCRIPTION_COMPLETED:
                await self._send(
                    {
                        "type": RealtimeEventType.INPUT_TRANSCRIPTION_COMPLETED,
                        "transcript": parsed_event.transcript,
                    }
                )

            case RealtimeEventType.RESPONSE_DONE:
                await self._send({"type": RealtimeEventType.RESPONSE_DONE})

            case RealtimeEventType.ERROR:
                error_msg = (
                    parsed_event.error.message if hasattr(parsed_event.error, "message") else str(parsed_event.error)
                )
                await self._send({"type": RealtimeEventType.ERROR, "error": error_msg})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _send(self, payload: dict[str, Any]) -> None:
        """Serialize *payload* as JSON and send it over the WebSocket."""
        await self.ws.send_text(json.dumps(payload))
