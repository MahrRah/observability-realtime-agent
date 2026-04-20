"""OpenTelemetry instrumentation for OpenAI Agents SDK Realtime (Voice) API.

Usage::

    from opentelemetry.instrumentation.openai_agents_realtime import (
        OpenAIAgentsRealtimeInstrumentor,
    )

    OpenAIAgentsRealtimeInstrumentor().instrument()
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Collection
from typing import Any

import wrapt
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor

from opentelemetry import trace
from opentelemetry.instrumentation.openai_agents_realtime._constants import (
    Attributes,
    MetricName,
    RealtimeEventType,
    SpanName,
)
from opentelemetry.instrumentation.openai_agents_realtime._listener import (
    RealtimeTelemetryListener,
)
from opentelemetry.instrumentation.openai_agents_realtime._telemetry_context import (
    TelemetryContext,
)
from opentelemetry.instrumentation.openai_agents_realtime.package import _instruments
from opentelemetry.instrumentation.openai_agents_realtime.version import __version__

__all__ = [
    "Attributes",
    "MetricName",
    "OpenAIAgentsRealtimeInstrumentor",
    "RealtimeEventType",
    "RealtimeTelemetryListener",
    "SpanName",
    "TelemetryContext",
    "__version__",
]

logger = logging.getLogger(__name__)


class OpenAIAgentsRealtimeInstrumentor(BaseInstrumentor):
    """Auto-instruments OpenAI Agents SDK realtime sessions with OTel telemetry.

    Wraps ``RealtimeRunner.run()`` to inject a ``RealtimeTelemetryListener``
    onto every session, and wraps ``RealtimeSession.__aexit__`` to auto-cleanup.

    Usage::

        OpenAIAgentsRealtimeInstrumentor().instrument(),
        )
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        async def _wrap_run(wrapped, instance, args, kwargs):
            session = await wrapped(*args, **kwargs)
            try:
                listener = RealtimeTelemetryListener()
                session.model.add_listener(listener)
                if not hasattr(session, "_auto_telemetry_listeners"):
                    session._auto_telemetry_listeners = []
                session._auto_telemetry_listeners.append(listener)
            except Exception:
                logger.warning("Failed to auto-attach telemetry listener", exc_info=True)
            return session

        async def _wrap_aexit(wrapped, instance, args, kwargs):
            try:
                for listener in getattr(instance, "_auto_telemetry_listeners", []):
                    if hasattr(listener, "cleanup"):
                        listener.cleanup()
            except Exception:
                logger.debug("Error during auto telemetry cleanup", exc_info=True)
            return await wrapped(*args, **kwargs)

        wrapt.wrap_function_wrapper("agents.realtime.runner", "RealtimeRunner.run", _wrap_run)
        wrapt.wrap_function_wrapper("agents.realtime.session", "RealtimeSession.__aexit__", _wrap_aexit)

    def _uninstrument(self, **kwargs: Any) -> None:
        from agents.realtime import runner as runner_module
        from agents.realtime import session as session_module

        if hasattr(runner_module.RealtimeRunner.run, "__wrapped__"):
            runner_module.RealtimeRunner.run = runner_module.RealtimeRunner.run.__wrapped__
        if hasattr(session_module.RealtimeSession.__aexit__, "__wrapped__"):
            session_module.RealtimeSession.__aexit__ = session_module.RealtimeSession.__aexit__.__wrapped__