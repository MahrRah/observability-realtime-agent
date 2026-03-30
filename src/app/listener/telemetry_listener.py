from __future__ import annotations

import contextlib
import logging
from typing import Any

from agents.realtime.model import RealtimeModelListener
from agents.realtime.model_events import RealtimeModelEvent
from agents.realtime.openai_realtime import get_server_event_type_adapter
from openai.types.realtime import (
    ConversationItemAdded,
    ConversationItemInputAudioTranscriptionCompletedEvent,
    ConversationItemInputAudioTranscriptionFailedEvent,
    ConversationItemTruncatedEvent,
    InputAudioBufferSpeechStartedEvent,
    InputAudioBufferSpeechStoppedEvent,
    RateLimitsUpdatedEvent,
    RealtimeConversationItemFunctionCallOutput,
    RealtimeErrorEvent,
    RealtimeResponseUsage,
    RealtimeSessionCreateRequest,
    ResponseAudioDeltaEvent,
    ResponseAudioTranscriptDeltaEvent,
    ResponseAudioTranscriptDoneEvent,
    ResponseCreatedEvent,
    ResponseDoneEvent,
    ResponseFunctionCallArgumentsDoneEvent,
    SessionCreatedEvent,
    SessionUpdatedEvent,
)
from openai.types.realtime.realtime_audio_formats import AudioPCM
from openai.types.realtime.realtime_audio_input_turn_detection import ServerVad
from opentelemetry import metrics, trace
from opentelemetry.trace import SpanKind, StatusCode, get_current_span

from app.constants.observability.attributes import Attributes
from app.constants.observability.metric import MetricName
from app.constants.observability.span import SpanName
from app.constants.realtime_event_types import RealtimeEventType
from app.listener.telemetry_context import TelemetryContext

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

UNKNOWN_ID = "unknown"


# ─── Metrics ───────────────────────────────────────────


_tokens_counter = meter.create_counter(MetricName.TOKENS, description="Token usage by category")
_function_call_counter = meter.create_counter(MetricName.FUNCTION_CALL)
_function_success_counter = meter.create_counter(MetricName.FUNCTION_SUCCESS)
_error_counter = meter.create_counter(MetricName.ERROR, description="Error events by type")
_rate_limit_remaining = meter.create_gauge(
    "gen_ai.realtime.rate_limit.remaining",
    description="Remaining rate limit budget",
)


class RealtimeTelemetryListener(RealtimeModelListener):
    """OpenTelemetry event listener for OpenAI Realtime API sessions."""

    def __init__(
        self,
        session_id: str,
        *,
        track_delta_events: bool = False,
    ) -> None:
        self.session_id = session_id
        self.track_delta_events = track_delta_events

        self._otel = TelemetryContext(session_id=session_id, root_span=get_current_span())

        self._function_call_map: dict[str, str] = {}

    def cleanup(self) -> None:
        """End all open spans and record a session-outcome metric."""

        self._otel.cleanup()
        logger.info("OTEL context cleaned up for session %s", self.session_id)

    async def on_event(self, event: RealtimeModelEvent) -> None:
        if event.type != "raw_server_event":
            return

        parsed = get_server_event_type_adapter().validate_python(event.data)

        match parsed.type:
            case RealtimeEventType.SESSION_CREATED:
                self._handle_session_created(parsed)
            case RealtimeEventType.SESSION_UPDATED:
                self._handle_session_updated(parsed)
            case RealtimeEventType.SPEECH_STARTED:
                self._handle_speech_started(parsed)
            case RealtimeEventType.SPEECH_STOPPED:
                self._handle_speech_stopped(parsed)
            case RealtimeEventType.RESPONSE_CREATED:
                self._handle_response_created(parsed)
            case RealtimeEventType.RESPONSE_DONE:
                self._handle_response_done(parsed)
            case RealtimeEventType.FUNCTION_CALL:
                self._handle_function_call_arguments_done(parsed)
            case RealtimeEventType.CONVERSATION_ITEM_ADDED:
                self._handle_conversation_item_added(parsed)
            case RealtimeEventType.AUDIO_DELTA:
                self._handle_response_audio_delta(parsed)
            case RealtimeEventType.TRANSCRIPT_DELTA:
                self._handle_response_transcription_delta(parsed)
            case RealtimeEventType.TRANSCRIPT_DONE:
                self._handle_response_audio_transcript_done(parsed)
            case RealtimeEventType.INPUT_TRANSCRIPTION_COMPLETED:
                self._handle_input_audio_transcription_completed(parsed)
            case RealtimeEventType.INPUT_TRANSCRIPTION_FAILED:
                self._handle_input_audio_transcription_failed(parsed)
            case RealtimeEventType.CONVERSATION_ITEM_TRUNCATED:
                self._handle_conversation_item_truncated(parsed)
            case RealtimeEventType.ERROR:
                self._handle_error(parsed)
            case RealtimeEventType.RATE_LIMITS_UPDATED:
                self._handle_rate_limits_updated(parsed)
            case _:
                logger.debug("Unhandled raw server event: %s", parsed.type)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _handle_session_created(self, event: SessionCreatedEvent) -> None:
        logger.info("Session created: %s", event.session.id)
        ctx = self._otel.get_span_context()
        span = tracer.start_span(SpanName.SESSION_CREATED, context=ctx, kind=SpanKind.INTERNAL)
        self._otel.start_anchor_span("session", span, context=ctx)

        oai_session_id = getattr(event.session, "id", None)
        if oai_session_id:
            self._otel.session_id = oai_session_id
            span.set_attribute(Attributes.SESSION_ID, oai_session_id)
            if self._otel.root_span is not None:
                with contextlib.suppress(Exception):
                    self._otel.root_span.set_attribute(Attributes.SESSION_ID, oai_session_id)

        span.set_attribute(Attributes.EVENT_NAME, RealtimeEventType.SESSION_CREATED)

    def _handle_session_updated(self, event: SessionUpdatedEvent) -> None:
        span = self._otel.get_anchor_span("session")
        if span and isinstance(event.session, RealtimeSessionCreateRequest):
            span.set_attributes(_extract_session_attributes(event.session))

    def _handle_speech_started(self, event: InputAudioBufferSpeechStartedEvent) -> None:
        ctx = self._otel.get_span_context(key="session")
        span = tracer.start_span(SpanName.USER_INPUT, context=ctx, kind=SpanKind.INTERNAL)
        response_id = event.response.id or UNKNOWN_ID

        self._otel.start_anchor_span(response_id, span, context=ctx)

        if self._otel.session_id:
            span.set_attribute(Attributes.SESSION_ID, self._otel.session_id)
        span.set_attribute(Attributes.EVENT_NAME, RealtimeEventType.USER_INPUT)
        span.set_attribute(Attributes.ITEM_ID, event.item_id or UNKNOWN_ID)
        span.set_attribute(Attributes.RESPONSE_ID, response_id)

    def _handle_speech_stopped(self, event: InputAudioBufferSpeechStoppedEvent) -> None:
        self._otel.end_anchor_span(event.response_id)

    def _handle_response_created(self, event: ResponseCreatedEvent) -> None:
        ctx = self._otel.get_span_context(key="session")
        span = tracer.start_span(SpanName.ASSISTANT_RESPONSE, context=ctx, kind=SpanKind.INTERNAL)
        response_id = event.response.id or UNKNOWN_ID
        self._otel.start_anchor_span(response_id, span, context=ctx)

        if self._otel.session_id:
            span.set_attribute(Attributes.SESSION_ID, self._otel.session_id)
        span.set_attribute(Attributes.EVENT_NAME, RealtimeEventType.RESPONSE_CREATED)
        span.set_attribute(Attributes.RESPONSE_ID, response_id)

    def _handle_response_done(self, event: ResponseDoneEvent) -> None:
        response_id = event.response.id or UNKNOWN_ID
        span = self._otel.get_anchor_span(response_id)

        if span:
            if event.response.status:
                span.set_attribute(Attributes.RESPONSE_STATUS, event.response.status)
                finish_reasons = _map_status_to_finish_reasons(event.response.status, event.response.status_details)
                if finish_reasons:
                    span.set_attribute(Attributes.RESPONSE_FINISH_REASONS, finish_reasons)

            # Status details for non-completed responses
            if event.response.status_details:
                if event.response.status_details.reason:
                    span.set_attribute(
                        Attributes.RESPONSE_STATUS_REASON,
                        event.response.status_details.reason,
                    )
                if event.response.status_details.error:
                    err = event.response.status_details.error
                    span.set_status(
                        StatusCode.ERROR,
                        f"{err.type}: {err.code}" if err.code else str(err.type),
                    )
                    span.set_attribute(Attributes.ERROR_TYPE, err.type or "unknown")

            # Mark failed/incomplete as error when no error details present
            if event.response.status in ("failed", "incomplete") and (
                not event.response.status_details or not event.response.status_details.error
            ):
                span.set_status(StatusCode.ERROR, f"Response {event.response.status}")

            if (output := event.response.output) and output[0].id:
                span.set_attribute(Attributes.ITEM_ID, output[0].id)

            attrs: dict[str, Any] = {}
            if event.response.output_modalities:
                attrs[Attributes.OUTPUT_TYPE] = event.response.output_modalities

            if (usage := event.response.usage) is not None:
                attrs.update(_extract_token_attributes(usage))
                self._extract_and_record_token_usage(usage, self._otel.session_id)

            span.set_attributes(attrs)

        self._otel.end_anchor_span(response_id)

    def _handle_function_call_arguments_done(self, event: ResponseFunctionCallArgumentsDoneEvent) -> None:
        ctx = self._otel.get_span_context(key=event.response_id)
        span = tracer.start_span(SpanName.FUNCTION_CALL, context=ctx, kind=SpanKind.INTERNAL)
        call_id = event.call_id or UNKNOWN_ID
        self._otel.start_anchor_span(call_id, span, context=ctx)

        function_name = getattr(event, "name", "unknown")
        if call_id is not UNKNOWN_ID:
            self._function_call_map[call_id] = function_name

        if self._otel.session_id:
            span.set_attribute(Attributes.SESSION_ID, self._otel.session_id)
        span.set_attribute(Attributes.EVENT_NAME, RealtimeEventType.FUNCTION_CALL)
        span.set_attribute(Attributes.RESPONSE_ID, event.response_id)
        span.set_attribute(Attributes.FUNCTION_CALL_ID, call_id)
        span.set_attribute(Attributes.FUNCTION_NAME, function_name)
        _function_call_counter.add(1, {"session_id": self._otel.session_id, "function_name": function_name})

        logger.info("Tool call: %s(%s)", function_name, event.arguments)

    def _handle_conversation_item_added(self, event: ConversationItemAdded) -> None:
        if isinstance(event.item, RealtimeConversationItemFunctionCallOutput):
            call_id = event.item.call_id
            output = event.item.output
            logger.info("Tool output: %s", output)

            if call_id and call_id in self._function_call_map:
                fn = self._function_call_map.pop(call_id)
                _function_success_counter.add(1, {"session_id": self._otel.session_id, "function_name": fn})

            self._otel.end_anchor_span(call_id)

    # ── Delta / transcript events ─────────────────────────────────────

    def _handle_response_transcription_delta(self, event: ResponseAudioTranscriptDeltaEvent) -> None:
        if not self.track_delta_events:
            return
        span = self._otel.get_anchor_span(event.response_id)
        if span:
            span.add_event(
                RealtimeEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA,
                attributes={Attributes.EVENT_NAME: RealtimeEventType.RESPONSE_AUDIO_DELTA},
            )

    def _handle_response_audio_delta(self, event: ResponseAudioDeltaEvent) -> None:
        if not self.track_delta_events:
            return
        span = self._otel.get_anchor_span(event.response_id)
        if span:
            span.add_event(
                RealtimeEventType.RESPONSE_AUDIO_DELTA,
                attributes={Attributes.EVENT_NAME: RealtimeEventType.RESPONSE_AUDIO_DELTA},
            )

    def _handle_input_audio_transcription_completed(
        self,
        event: ConversationItemInputAudioTranscriptionCompletedEvent,
    ) -> None:
        logger.info("User: %s", event.transcript)

    def _handle_response_audio_transcript_done(self, event: ResponseAudioTranscriptDoneEvent) -> None:
        logger.info("Assistant: %s", event.transcript)

    def _handle_conversation_item_truncated(self, event: ConversationItemTruncatedEvent) -> None:
        span = self._otel.get_anchor_span("session")
        if span:
            span.add_event(
                RealtimeEventType.CONVERSATION_ITEM_TRUNCATED,
                attributes={
                    Attributes.ITEM_ID: event.item_id,
                    Attributes.ITEM_AUDIO_END_MS: event.audio_end_ms,
                },
            )

    def _handle_error(self, event: RealtimeErrorEvent) -> None:
        error = event.error
        logger.error(
            "Realtime API error: [%s] %s (code=%s, param=%s)",
            error.type,
            error.message,
            error.code,
            error.param,
        )

        span = self._otel.get_anchor_span("session")
        if span:
            span.set_status(StatusCode.ERROR, error.message)
            span.set_attribute(Attributes.ERROR_TYPE, error.type or "unknown")
            span.add_event(
                "gen_ai.error",
                attributes={
                    Attributes.ERROR_TYPE: error.type or "unknown",
                    Attributes.ERROR_CODE: error.code or "",
                    Attributes.ERROR_MESSAGE: error.message,
                },
            )
        _error_counter.add(
            1,
            {"session_id": self._otel.session_id, "error_type": error.type or "unknown"},
        )

    def _handle_input_audio_transcription_failed(
        self,
        event: ConversationItemInputAudioTranscriptionFailedEvent,
    ) -> None:
        error = event.error
        logger.warning(
            "Transcription failed for item %s: %s",
            event.item_id,
            error.message if error else "unknown",
        )

        span = self._otel.get_anchor_span(event.item_id) or self._otel.get_anchor_span("session")
        if span and error:
            span.add_event(
                "gen_ai.transcription.failed",
                attributes={
                    Attributes.ERROR_TYPE: error.type or "unknown",
                    Attributes.ERROR_CODE: error.code or "",
                    Attributes.ERROR_MESSAGE: error.message or "",
                    Attributes.ITEM_ID: event.item_id,
                },
            )
        _error_counter.add(
            1,
            {
                "session_id": self._otel.session_id,
                "error_type": f"transcription.{error.type}" if error and error.type else "transcription.unknown",
            },
        )

    def _handle_rate_limits_updated(self, event: RateLimitsUpdatedEvent) -> None:
        span = self._otel.get_anchor_span("session")
        if span:
            for rl in event.rate_limits:
                span.add_event(
                    "gen_ai.rate_limits",
                    attributes={
                        Attributes.RATE_LIMIT_NAME: rl.name or "unknown",
                        Attributes.RATE_LIMIT_LIMIT: rl.limit or 0,
                        Attributes.RATE_LIMIT_REMAINING: rl.remaining or 0,
                        Attributes.RATE_LIMIT_RESET_SECONDS: rl.reset_seconds or 0.0,
                    },
                )

        for rl in event.rate_limits:
            if rl.remaining is not None:
                _rate_limit_remaining.add(
                    rl.remaining,
                    {
                        "session_id": self._otel.session_id,
                        "rate_limit_name": rl.name or "unknown",
                    },
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_and_record_token_usage(self, usage: RealtimeResponseUsage, session_id: str | None) -> None:
        audio_input_tokens: int | None = None
        text_input_tokens: int | None = None
        audio_output_tokens: int | None = None
        text_output_tokens: int | None = None
        audio_input_cached_tokens: int | None = None
        text_input_cached_tokens: int | None = None
        total_input_cached_tokens: int | None = None

        if usage.input_token_details:
            audio_input_tokens = usage.input_token_details.audio_tokens
            text_input_tokens = usage.input_token_details.text_tokens

            if usage.input_token_details.cached_tokens_details:
                cd = usage.input_token_details.cached_tokens_details
                audio_input_cached_tokens = cd.audio_tokens
                text_input_cached_tokens = cd.text_tokens
                if audio_input_cached_tokens is not None and text_input_cached_tokens is not None:
                    total_input_cached_tokens = audio_input_cached_tokens + text_input_cached_tokens
            elif usage.input_token_details.cached_tokens is not None:
                total_input_cached_tokens = usage.input_token_details.cached_tokens
                text_input_cached_tokens = usage.input_token_details.cached_tokens

        if usage.output_token_details:
            audio_output_tokens = usage.output_token_details.audio_tokens
            text_output_tokens = usage.output_token_details.text_tokens

        _record_token_usage(
            audio_input_tokens=audio_input_tokens,
            audio_input_cached_tokens=audio_input_cached_tokens,
            audio_output_tokens=audio_output_tokens,
            text_input_tokens=text_input_tokens,
            text_input_cached_tokens=text_input_cached_tokens,
            text_output_tokens=text_output_tokens,
            total_input_cached_tokens=total_input_cached_tokens,
            session_id=session_id,
        )


# ─── Helper utilities ─────────────────────────────────────────────────


def _record_token_usage(
    *,
    audio_input_tokens: int | None = None,
    audio_input_cached_tokens: int | None = None,
    audio_output_tokens: int | None = None,
    text_input_tokens: int | None = None,
    text_input_cached_tokens: int | None = None,
    text_output_tokens: int | None = None,
    total_input_cached_tokens: int | None = None,
    session_id: str | None = None,
) -> None:
    base = {"session_id": session_id}
    pairs: list[tuple[str, int | None]] = [
        ("audio_input", audio_input_tokens),
        ("audio_input_cached", audio_input_cached_tokens),
        ("audio_output", audio_output_tokens),
        ("text_input", text_input_tokens),
        ("text_input_cached", text_input_cached_tokens),
        ("text_output", text_output_tokens),
        ("total_input_cached", total_input_cached_tokens),
    ]
    for category, value in pairs:
        if value is not None:
            _tokens_counter.add(value, {**base, "token_type": category})


def _extract_token_attributes(usage: RealtimeResponseUsage) -> dict[str, int]:
    """Extract token usage attributes for span recording."""
    attrs: dict[str, Any] = {}

    if usage.total_tokens is not None:
        attrs[Attributes.TOKEN_TOTAL] = usage.total_tokens

    if input_tokens := usage.input_token_details:
        if input_tokens.audio_tokens is not None:
            attrs[Attributes.TOKEN_INPUT_AUDIO] = input_tokens.audio_tokens
        if input_tokens.text_tokens is not None:
            attrs[Attributes.TOKEN_INPUT_TEXT] = input_tokens.text_tokens

        if cached := input_tokens.cached_tokens_details:
            if cached.audio_tokens is not None:
                attrs[Attributes.TOKEN_INPUT_AUDIO_CACHED] = cached.audio_tokens
            if cached.text_tokens is not None:
                attrs[Attributes.TOKEN_INPUT_TEXT_CACHED] = cached.text_tokens

    if output_tokens := usage.output_token_details:
        if output_tokens.audio_tokens is not None:
            attrs[Attributes.TOKEN_OUTPUT_AUDIO] = output_tokens.audio_tokens
        if output_tokens.text_tokens is not None:
            attrs[Attributes.TOKEN_OUTPUT_TEXT] = output_tokens.text_tokens

    return attrs


def _extract_session_attributes(
    session: RealtimeSessionCreateRequest,
) -> dict[str, Any]:
    """Extract session configuration attributes for span recording."""
    attrs: dict[str, Any] = {}

    if session.model is not None:
        attrs[Attributes.REQUEST_MODEL] = session.model
    if session.instructions is not None:
        attrs[Attributes.INSTRUCTIONS] = session.instructions

    if exp_date := getattr(session, "expires_at", None):
        attrs[Attributes.SESSION_EXPIRES_AT] = exp_date
    if session_object := getattr(session, "object", None):
        attrs[Attributes.SESSION_OBJECT] = session_object

    if session.output_modalities is not None:
        attrs[Attributes.SESSION_TYPE] = session.output_modalities
    if session.max_output_tokens is not None:
        attrs[Attributes.REQUEST_MAX_TOKENS] = session.max_output_tokens
    if session.tool_choice is not None:
        attrs[Attributes.TOOL_CHOICE] = str(session.tool_choice)

    if audio := session.audio:
        if audio.input:
            if audio_format := audio.input.format:
                attrs[Attributes.AUDIO_INPUT_FORMAT] = audio_format.type
                if isinstance(audio_format, AudioPCM) and audio_format.rate is not None:
                    attrs[Attributes.AUDIO_INPUT_RATE] = audio_format.rate

            if transcription := audio.input.transcription:
                if transcription.model is not None:
                    attrs[Attributes.AUDIO_INPUT_TRANSCRIPTION_MODEL] = transcription.model
                if transcription.language is not None:
                    attrs[Attributes.AUDIO_INPUT_TRANSCRIPTION_LANGUAGE] = transcription.language
                if transcription.prompt is not None:
                    attrs[Attributes.AUDIO_INPUT_TRANSCRIPTION_PROMPT] = transcription.prompt

            if audio.input.noise_reduction is not None:
                attrs[Attributes.AUDIO_INPUT_NOISE_REDUCTION] = audio.input.noise_reduction.type

            if td := audio.input.turn_detection:
                attrs[Attributes.TURN_DETECTION_TYPE] = td.type
                if td.create_response is not None:
                    attrs[Attributes.TURN_DETECTION_CREATE_RESPONSE] = td.create_response
                if td.interrupt_response is not None:
                    attrs[Attributes.TURN_DETECTION_INTERRUPT_RESPONSE] = td.interrupt_response
                if isinstance(td, ServerVad):
                    if td.threshold is not None:
                        attrs[Attributes.TURN_DETECTION_THRESHOLD] = td.threshold
                    if td.prefix_padding_ms is not None:
                        attrs[Attributes.TURN_DETECTION_PREFIX_PADDING_MS] = td.prefix_padding_ms
                    if td.silence_duration_ms is not None:
                        attrs[Attributes.TURN_DETECTION_SILENCE_DURATION_MS] = td.silence_duration_ms

        if audio.output:
            if audio_format := audio.output.format:
                attrs[Attributes.AUDIO_OUTPUT_FORMAT] = audio_format.type
                if isinstance(audio_format, AudioPCM) and audio_format.rate is not None:
                    attrs[Attributes.AUDIO_OUTPUT_RATE] = audio_format.rate
            if audio.output.voice is not None:
                attrs[Attributes.AUDIO_OUTPUT_VOICE] = audio.output.voice
            if audio.output.speed is not None:
                attrs[Attributes.AUDIO_OUTPUT_SPEED] = audio.output.speed

    return attrs


def _map_status_to_finish_reasons(
    status: str | None,
    status_details: Any,
) -> list[str]:
    """Map Realtime API response status to OTel ``gen_ai.response.finish_reasons``."""
    if status == "completed":
        return ["stop"]
    if status == "failed":
        return ["error"]
    if status in ("cancelled", "incomplete"):
        reason = getattr(status_details, "reason", None)
        if reason == "max_output_tokens":
            return ["length"]
        return [reason or status]
    return []
