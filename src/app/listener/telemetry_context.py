from __future__ import annotations

import logging
from contextvars import Token

from opentelemetry.context import Context, attach, detach, get_current
from opentelemetry.trace import Span, set_span_in_context

logger = logging.getLogger(__name__)


class TelemetryContext:
    """Manages OpenTelemetry span lifecycle for a single realtime session.

    Uses ``opentelemetry.context.attach`` / ``detach`` to keep the *current*
    OTel context in sync with anchor spans.  A stored ``Token`` allows the
    previous context to be restored when the span ends.

    When a ``context`` argument is supplied to ``start_anchor_span`` the span is
    recorded **without** becoming the current span (no ``attach`` call), which
    is the correct behaviour for child spans whose lifetime may overlap with
    siblings.
    """

    def __init__(self, session_id: str | None = None, root_span: Span | None = None) -> None:
        self.session_id: str | None = session_id
        self.root_span: Span | None = root_span
        self._anchors: dict[str, tuple[Span, Token[Context] | None]] = {}

    def get_span_context(self, key: str | None = None, context: Context | None = None) -> Context:
        """Return a ``Context`` scoped to the given anchor span, root span, or current context."""
        if key and key in self._anchors:
            span, _ = self._anchors[key]
            return set_span_in_context(span, context=context)
        if self.root_span:
            return set_span_in_context(self.root_span)
        return get_current()

    def start_anchor_span(self, key: str, span: Span, context: Context | None = None) -> Span:
        """Attach a span and store it as an anchor.

        If *context* is ``None`` the span is attached to the current context
        (making it the *current* span) and the token is stored for later
        ``detach``.  If *context* is provided a fire-and-forget ``attach`` is
        performed so the span becomes the *current* span for log correlation,
        but no token is stored — avoiding cross-task ``detach`` errors.
        """
        new_context = set_span_in_context(span, context=context)
        token: Token[Context] | None = None
        if context is None:
            token = attach(new_context)
        else:
            try:
                attach(new_context)
            except Exception:
                pass
        self._anchors[key] = (span, token)
        return span

    def get_anchor_span(self, key: str, attach_to_current_context: bool = True) -> Span | None:
        """Get an anchor span by key.

        When *attach_to_current_context* is ``True`` (default) a fire-and-forget
        ``attach`` is performed so the span becomes the *current* span for log
        correlation.
        """
        anchor = self._anchors.get(key)
        if anchor:
            span, _ = anchor
            if attach_to_current_context:
                try:
                    attach(set_span_in_context(span))
                except Exception:
                    pass
            return span
        return None

    def end_anchor_span(self, key: str | None) -> None:
        if not key:
            return
        anchor = self._anchors.pop(key, None)
        if anchor:
            span, token = anchor
            if token is not None:
                try:
                    detach(token)
                except Exception:
                    logger.debug("Unable to detach span for %s", key)
            try:
                if span.is_recording():
                    span.end()
            except Exception:
                logger.debug("Unable to end span for %s", key)

    def cleanup(self) -> None:
        for key in list(self._anchors.keys()):
            anchor = self._anchors.pop(key, None)
            if anchor:
                span, token = anchor
                if token is not None:
                    try:
                        detach(token)
                    except Exception:
                        pass
                try:
                    if span.is_recording():
                        span.end()
                except Exception:
                    logger.debug("Failed to close anchor span during cleanup: %s", key)
        if self.root_span and self.root_span.is_recording():
            try:
                self.root_span.end()
            except Exception:
                logger.debug("Failed to close root span during cleanup")
            self.root_span = None
