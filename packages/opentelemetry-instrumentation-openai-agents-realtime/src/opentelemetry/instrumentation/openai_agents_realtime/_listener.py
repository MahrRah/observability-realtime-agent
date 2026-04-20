from __future__ import annotations

import contextlib
import logging
import time
from typing import Any

from agents.realtime.model import RealtimeModelListener
from agents.realtime.model_events import RealtimeModelEvent
from agents.realtime.openai_realtime import get_server_event_type_adapter
from openai.types.realtime import (
    ConversationCreatedEvent,
    ConversationItemAdded,
    ConversationItemInputAudioTranscriptionCompletedEvent,
    ConversationItemInputAudioTranscriptionFailedEvent,
    ConversationItemTruncatedEvent,
    InputAudioBufferCommittedEvent,
    InputAudioBufferSpeechStartedEvent,
    InputAudioBufferSpeechStoppedEvent,
    InputAudioBufferTimeoutTriggered,
    McpListToolsCompleted,
    McpListToolsFailed,
    McpListToolsInProgress,
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
    ResponseMcpCallArgumentsDone,
    ResponseMcpCallCompleted,
    ResponseMcpCallFailed,
    ResponseMcpCallInProgress,
    ResponseTextDeltaEvent,
    ResponseTextDoneEvent,
    SessionCreatedEvent,
    SessionUpdatedEvent,
)
from openai.types.realtime.realtime_audio_formats import AudioPCM
from openai.types.realtime.realtime_audio_input_turn_detection import ServerVad
from opentelemetry.trace import SpanKind, StatusCode, get_current_span

from opentelemetry import metrics, trace
from opentelemetry.instrumentation.openai_agents_realtime._constants.attributes import Attributes, GenAIOperationName, GenAIProvider
from opentelemetry.instrumentation.openai_agents_realtime._constants.metric import MetricName
from opentelemetry.instrumentation.openai_agents_realtime._constants.realtime_event_types import RealtimeEventType
from opentelemetry.instrumentation.openai_agents_realtime._constants.span import SpanName
from opentelemetry.instrumentation.openai_agents_realtime._telemetry_context import TelemetryContext

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

#TODO Is this a good idea
_UNKNOWN = "unknown"


# ─── Metrics ───────────────────────────────────────────


_token_usage_histogram = meter.create_histogram(
    MetricName.TOKEN_USAGE,
    description="Number of input and output tokens used",
    unit="{token}",
)

_operation_duration_histogram = meter.create_histogram(
    MetricName.OPERATION_DURATION,
    description="GenAI operation duration",
    unit="s",
)
_time_to_first_token = meter.create_histogram(
    MetricName.TIME_TO_FIRST_TOKEN,
    description="Time to generate first token for successful responses",
    unit="s",
)
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
        *,
        track_delta_events: bool = False,
        track_call_content: bool = False, #TODO dont really like the name/should be configurable via env vars
        server_address: str | None = None,
        server_port: int | None = None,
        provider_name: str | None = None,
        agent_name: str | None = None,
    ) -> None:
        
        self.track_delta_events = track_delta_events
        self.track_call_content = track_call_content
        self._server_address = server_address
        self._server_port = server_port
        self.agent_name : str | None = agent_name
        self.provider_name = provider_name or "openai"
        self._otel = TelemetryContext(root_span=get_current_span()) # TODO should the passing of the span be here?

        self._function_call_map: dict[str, str] = {}
        
        self._model: str | None = None
        self._response_start_times: dict[str, float] = {}
        self._first_token_recorded: set[str] = set()

    def cleanup(self) -> None:
        """End all open spans and record a session-outcome metric."""

        self._otel.cleanup()
        logger.debug("OTEL context cleaned up for session %s", self.session_id)



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
            case RealtimeEventType.TEXT_DELTA:
                self._handle_response_text_delta(parsed)
            case RealtimeEventType.TEXT_DONE:
                self._handle_response_text_done(parsed)
            case RealtimeEventType.INPUT_TRANSCRIPTION_COMPLETED:
                self._handle_input_audio_transcription_completed(parsed)
            case RealtimeEventType.INPUT_TRANSCRIPTION_FAILED:
                self._handle_input_audio_transcription_failed(parsed)
            case RealtimeEventType.CONVERSATION_ITEM_TRUNCATED:
                self._handle_conversation_item_truncated(parsed)
            case RealtimeEventType.INPUT_AUDIO_BUFFER_COMMITTED:
                self._handle_input_audio_buffer_committed(parsed)
            case RealtimeEventType.INPUT_AUDIO_BUFFER_TIMEOUT_TRIGGERED:
                self._handle_input_audio_buffer_timeout_triggered(parsed)
            case RealtimeEventType.MCP_CALL_ARGUMENTS_DONE:
                self._handle_mcp_call_arguments_done(parsed)
            case RealtimeEventType.MCP_CALL_IN_PROGRESS:
                self._handle_mcp_call_in_progress(parsed)
            case RealtimeEventType.MCP_CALL_COMPLETED:
                self._handle_mcp_call_completed(parsed)
            case RealtimeEventType.MCP_CALL_FAILED:
                self._handle_mcp_call_failed(parsed)
            case RealtimeEventType.MCP_LIST_TOOLS_IN_PROGRESS:
                self._handle_mcp_list_tools(parsed)
            case RealtimeEventType.MCP_LIST_TOOLS_COMPLETED:
                self._handle_mcp_list_tools(parsed)
            case RealtimeEventType.MCP_LIST_TOOLS_FAILED:
                self._handle_mcp_list_tools(parsed)
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
        session_id = getattr(event.session, "id", None)
        logger.info("Session created: %s", session_id)
        ctx = self._otel.get_span_context()
        span = tracer.start_span(SpanName.SESSION_CREATED, context=ctx, kind=SpanKind.INTERNAL)
        self._otel.start_anchor_span("session", span, context=ctx)
        
        if session_id:
            self._otel.session_id = session_id
            span.set_attribute(Attributes.SESSION_ID, session_id)
            if self._otel.root_span is not None:
                with contextlib.suppress(Exception):
                    self._otel.root_span.set_attribute(Attributes.SESSION_ID, session_id)

        span.set_attribute(Attributes.OPERATION_NAME, GenAIOperationName.INVOKE_AGENT)
        span.set_attribute(Attributes.PROVIDER_NAME, self.provider_name)
        if self._server_address:
            span.set_attribute(Attributes.SERVER_ADDRESS, self._server_address)
        if self._server_port is not None:
            span.set_attribute(Attributes.SERVER_PORT, self._server_port)
        span.set_attribute(Attributes.EVENT_NAME, event.type)
        span.set_attribute(Attributes.EVENT_ID, event.event_id)
        if span and isinstance(event.session, RealtimeSessionCreateRequest):
            span.set_attributes(_extract_session_attributes(event.session))
        
        if self.agent_name:
            
            span.set_attribute(Attributes.AGENT_NAME, self.agent_name)

    def _handle_session_updated(self, event: SessionUpdatedEvent) -> None:
        self._otel.end_anchor_span("session")
        
        ctx = self._otel.get_span_context()
        span = tracer.start_span(SpanName.SESSION_CREATED, context=ctx, kind=SpanKind.INTERNAL)
        self._otel.start_anchor_span("session", span, context=ctx)
        
        if span and isinstance(event.session, RealtimeSessionCreateRequest):
            span.set_attributes(_extract_session_attributes(event.session))
            if event.session.model is not None:
                self._model = event.session.model

    def _handle_speech_started(self, event: InputAudioBufferSpeechStartedEvent) -> None:
        ctx = self._otel.get_span_context(key="session")
        span = tracer.start_span(SpanName.USER_INPUT, context=ctx, kind=SpanKind.INTERNAL)
        
        item_id = event.item_id
        self._otel.start_anchor_span(item_id, span, context=ctx)

        span.set_attribute(Attributes.OPERATION_NAME, SpanName.USER_INPUT)
        span.set_attribute(Attributes.PROVIDER_NAME, self.provider_name)
        if self._model:
            span.set_attribute(Attributes.REQUEST_MODEL, self._model)
        span.set_attribute(Attributes.SESSION_ID, self._otel.session_id)
        span.set_attribute(Attributes.EVENT_NAME, event.type)
        span.set_attribute(Attributes.EVENT_ID, event.event_id)
        span.set_attribute(Attributes.ITEM_ID, event.item_id)

    def _handle_speech_stopped(self, event: InputAudioBufferSpeechStoppedEvent) -> None:
        self._otel.end_anchor_span(event.item_id)

    def _handle_response_created(self, event: ResponseCreatedEvent) -> None:
        ctx = self._otel.get_span_context(key="session")
        span = tracer.start_span(SpanName.AGENT_RESPONSE, context=ctx, kind=SpanKind.INTERNAL)
        response = event.response
        response_id = response.id or _UNKNOWN
        self._otel.start_anchor_span(response_id, span, context=ctx)

        span.set_attribute(Attributes.OPERATION_NAME, SpanName.AGENT_RESPONSE)
        span.set_attribute(Attributes.PROVIDER_NAME, self.provider_name)
        if response.conversation_id:
            span.set_attribute(Attributes.CONVERSATION_ID, response.conversation_id)
        if response.output_modalities:
            span.set_attribute(Attributes.OUTPUT_TYPE, response.output_modalities)
        span.set_attribute(Attributes.RESPONSE_ID, response_id)
        span.set_attribute(Attributes.EVENT_NAME, event.type)
        span.set_attribute(Attributes.EVENT_ID, event.event_id)

        # TODO should this be here or in speech_stopped?
        self._response_start_times[response_id] = time.monotonic()

    def _handle_response_done(self, event: ResponseDoneEvent) -> None:

        response = event.response
        response_id = response.id or _UNKNOWN
        span = self._otel.get_anchor_span(response_id)

        if span:
            if response.status:
                span.set_attribute(Attributes.RESPONSE_STATUS, response.status)
            # Status details for non-completed responses
            if status_details := response.status_details:
                if status_details.reason:
                    span.set_attribute(
                        Attributes.RESPONSE_STATUS_REASON,
                        status_details.reason,
                    )
                if status_details.error:
                    err = status_details.error
                    logger.error("Response error: %s", err)
                    span.set_status(
                        StatusCode.ERROR,
                        f"{err.type}: {err.code}" if err.code else str(err.type),
                    )
                    span.set_attribute(Attributes.ERROR_TYPE, err.type or _UNKNOWN)


            if response.status in ("failed", "incomplete") and (
                not response.status_details or not response.status_details.error
            ):
                span.set_status(StatusCode.ERROR, f"Response {response.status}")

            if response.conversation_id:
                span.set_attribute(Attributes.CONVERSATION_ID, response.conversation_id)
            if response.output_modalities:
                span.set_attribute(Attributes.OUTPUT_TYPE, response.output_modalities)

            if usage := response.usage:
                usage_attributes = _extract_token_attributes(usage)
                span.set_attributes(usage_attributes)
                self._extract_and_record_token_usage(usage)

            if output := response.output:
                item_ids = []
                for item in output:
                    if item.id:
                        item_ids.append(item.id)
                    if self.track_call_content:
                        span.set_attribute(Attributes.RESPONSE_OUTPUT, str([c.model_dump() for c in item.content]))
                span.set_attribute(Attributes.ITEM_ID, item_ids)

        # Record operation duration metric
        start_time = self._response_start_times.pop(response_id, None)
        self._first_token_recorded.discard(response_id)
        if start_time is not None:
            duration = time.monotonic() - start_time
            duration_attrs: dict[str, str] = {
                Attributes.OPERATION_NAME: "realtime_session",
                Attributes.PROVIDER_NAME: self.provider_name,
            }
            if self._model:
                duration_attrs[Attributes.REQUEST_MODEL] = self._model
            if response.status and response.status  in ("failed", "incomplete"):
                duration_attrs[Attributes.ERROR_TYPE] = response.status 
            _operation_duration_histogram.record(duration, duration_attrs)

        self._otel.end_anchor_span(response_id)

    def _handle_function_call_arguments_done(self, event: ResponseFunctionCallArgumentsDoneEvent) -> None:
        ctx = self._otel.get_span_context(key=event.response_id)
        function_name = event.name
        call_id = event.call_id
        
        span = tracer.start_span(f"{SpanName.FUNCTION_CALL} {function_name}", context=ctx, kind=SpanKind.INTERNAL)
        self._otel.start_anchor_span(call_id, span, context=ctx)
        self._function_call_map[call_id] = function_name

        span.set_attribute(Attributes.OPERATION_NAME, GenAIOperationName.EXECUTE_TOOL)
        span.set_attribute(Attributes.PROVIDER_NAME, self.provider_name)
        span.set_attribute(Attributes.RESPONSE_ID, event.response_id)
        span.set_attribute(Attributes.TOOL_CALL_ID, call_id)
        span.set_attribute(Attributes.TOOL_NAME, function_name)
        span.set_attribute(Attributes.TOOL_TYPE, "function")


        if self.track_call_content:
            span.set_attribute(Attributes.TOOL_CALL_ARGUMENTS, event.arguments)
        _function_call_counter.add(1, {"session_id": self._otel.session_id, "tool_name": function_name})

        logger.info("Tool call: %s(%s)", function_name, event.arguments)

    def _handle_conversation_item_added(self, event: ConversationItemAdded) -> None:
        if isinstance(event.item, RealtimeConversationItemFunctionCallOutput):
            call_id = event.item.call_id
            output = event.item.output
            
            if call_id and call_id in self._function_call_map:
                fn = self._function_call_map.pop(call_id)
                _function_success_counter.add(1, {"session_id": self._otel.session_id, "tool_name": fn})

            if self.track_call_content and output:
                logger.info("Tool output: %s", output)
                span = self._otel.get_anchor_span(call_id)
                if span:
                    span.set_attribute(Attributes.TOOL_CALL_RESULT, output)

            self._otel.end_anchor_span(call_id)

    # ── Delta / transcript events ─────────────────────────────────────

    def _handle_response_transcription_delta(self, event: ResponseAudioTranscriptDeltaEvent) -> None:
        self._maybe_record_ttft(event.response_id)
        if not self.track_delta_events:
            return
        span = self._otel.get_anchor_span(event.response_id)
        if span:
            span.add_event(
                RealtimeEventType.TRANSCRIPT_DELTA,
                attributes={Attributes.EVENT_NAME: event.type},
            )

    def _handle_response_audio_delta(self, event: ResponseAudioDeltaEvent) -> None:
        self._maybe_record_ttft(event.response_id)
        if not self.track_delta_events:
            return
        span = self._otel.get_anchor_span(event.response_id)
        if span:
            span.add_event(
                RealtimeEventType.AUDIO_DELTA,
                attributes={Attributes.EVENT_NAME: event.type},
            )

    def _handle_response_text_delta(self, event: ResponseTextDeltaEvent) -> None:
        self._maybe_record_ttft(event.response_id)
        if not self.track_delta_events:
            return
        span = self._otel.get_anchor_span(event.response_id)
        if span:
            span.add_event(
                RealtimeEventType.TEXT_DELTA,
                attributes={Attributes.EVENT_NAME: event.type},
            )

    def _handle_response_text_done(self, event: ResponseTextDoneEvent) -> None:
        if self.track_call_content:
            logger.info("Assistant (text): %s", event.text) 

    def _handle_input_audio_transcription_completed(
        self,
        event: ConversationItemInputAudioTranscriptionCompletedEvent,
    ) -> None:
        if self.track_call_content:
            logger.info("User (transcription): %s", event.transcript)

    def _handle_response_audio_transcript_done(self, event: ResponseAudioTranscriptDoneEvent) -> None:
        if self.track_call_content:
            logger.info("Assistant (transcription): %s", event.transcript)

    def _handle_conversation_item_truncated(self, event: ConversationItemTruncatedEvent) -> None:
        span = self._otel.get_anchor_span("session")
        if span:
            span.add_event(
                RealtimeEventType.CONVERSATION_ITEM_TRUNCATED,
                attributes={
                    Attributes.ITEM_ID: event.item_id,
                    Attributes.EVENT_ID: event.event_id,
                    Attributes.ITEM_AUDIO_END_MS: event.audio_end_ms,
                    Attributes.CONTENT_INDEX: event.content_index, 
                },
            )

    # ── Audio buffer events ───────────────────────────────────────────

    def _handle_input_audio_buffer_committed(self, event: InputAudioBufferCommittedEvent) -> None:
        span = self._otel.get_anchor_span("session")
        if span:
            span.add_event(
                RealtimeEventType.INPUT_AUDIO_BUFFER_COMMITTED,
                attributes={Attributes.ITEM_ID: event.item_id},
            )

    def _handle_input_audio_buffer_timeout_triggered(self, event: InputAudioBufferTimeoutTriggered) -> None:
        span = self._otel.get_anchor_span("session")
        if span:
            span.add_event(
                RealtimeEventType.INPUT_AUDIO_BUFFER_TIMEOUT_TRIGGERED,
                attributes={Attributes.ITEM_ID: event.item_id},
            )

    # ── MCP tool call events ──────────────────────────────────────────

    def _handle_mcp_call_arguments_done(self, event: ResponseMcpCallArgumentsDone) -> None:
        ctx = self._otel.get_span_context(key=event.response_id)
        span = tracer.start_span(f"{SpanName.FUNCTION_CALL} mcp_tool", context=ctx, kind=SpanKind.INTERNAL)
        self._otel.start_anchor_span(event.item_id, span, context=ctx)

        span.set_attribute(Attributes.OPERATION_NAME, GenAIOperationName.EXECUTE_TOOL)
        span.set_attribute(Attributes.PROVIDER_NAME, self.provider_name)
        span.set_attribute(Attributes.RESPONSE_ID, event.response_id)
        span.set_attribute(Attributes.TOOL_TYPE, "mcp")
        if self._otel.session_id:
            span.set_attribute(Attributes.SESSION_ID, self._otel.session_id)
        span.set_attribute(Attributes.EVENT_NAME, RealtimeEventType.MCP_CALL_ARGUMENTS_DONE)
        span.set_attribute(Attributes.ITEM_ID, event.item_id)
        
        if self.track_call_content:
            span.set_attribute(Attributes.TOOL_CALL_ARGUMENTS, event.arguments)

    def _handle_mcp_call_in_progress(self, event: ResponseMcpCallInProgress) -> None:
        span = self._otel.get_anchor_span(event.item_id)
        if span:
            span.add_event(RealtimeEventType.MCP_CALL_IN_PROGRESS)

    def _handle_mcp_call_completed(self, event: ResponseMcpCallCompleted) -> None:
        self._otel.end_anchor_span(event.item_id)

    def _handle_mcp_call_failed(self, event: ResponseMcpCallFailed) -> None:
        span = self._otel.get_anchor_span(event.item_id)
        if span:
            span.set_status(StatusCode.ERROR, "MCP call failed")
            span.set_attribute(Attributes.ERROR_TYPE, "mcp_call_failed")
        self._otel.end_anchor_span(event.item_id)
        _error_counter.add(
            1,
            {"session_id": self._otel.session_id, "error_type": "mcp_call_failed"},
        )

    def _handle_mcp_list_tools(
        self,
        event: McpListToolsInProgress | McpListToolsCompleted | McpListToolsFailed,
    ) -> None:
        span = self._otel.get_anchor_span("session")
        if span:
            span.add_event(
                event.type,
                attributes={Attributes.ITEM_ID: event.item_id},
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
            span.set_attribute(Attributes.ERROR_TYPE, error.type or _UNKNOWN)
            span.add_event(
                "gen_ai.error",
                attributes={
                    Attributes.EVENT_ID: error.event_id, #TODO this is original event ID what caused the error
                    Attributes.ERROR_TYPE: error.type or _UNKNOWN,
                    Attributes.ERROR_CODE: error.code or "",
                    Attributes.ERROR_MESSAGE: error.message,
                },
            )
        _error_counter.add(
            1,
            {"session_id": self._otel.session_id, "error_type": error.type or _UNKNOWN},
        )

    def _handle_input_audio_transcription_failed(
        self,
        event: ConversationItemInputAudioTranscriptionFailedEvent,
    ) -> None:
        error = event.error
        logger.warning(
            "Transcription failed for item %s: %s",
            event.item_id,
            error.message if error else _UNKNOWN,
        )

        span = self._otel.get_anchor_span(event.item_id) or self._otel.get_anchor_span("session")
        if span and error:
            span.add_event(
                "gen_ai.transcription.failed",
                attributes={
                    Attributes.ERROR_TYPE: error.type or _UNKNOWN,
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
                        Attributes.RATE_LIMIT_NAME: rl.name or _UNKNOWN,
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
                        "rate_limit_name": rl.name or _UNKNOWN,
                    },
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_and_record_token_usage(self, usage: RealtimeResponseUsage) -> None:
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens

        # Fall back to computing aggregates from details when top-level fields are absent
        if input_tokens is None and usage.input_token_details:
            audio = usage.input_token_details.audio_tokens or 0
            text = usage.input_token_details.text_tokens or 0
            input_tokens = audio + text

        if output_tokens is None and usage.output_token_details:
            audio = usage.output_token_details.audio_tokens or 0
            text = usage.output_token_details.text_tokens or 0
            output_tokens = audio + text

        base_attrs: dict[str, str] = {
            #TODO should those be set to unknown or just omitted when not available?
            Attributes.SERVER_ADDRESS: self._server_address or _UNKNOWN,
            Attributes.SERVER_PORT: self._server_port or _UNKNOWN,
            Attributes.OPERATION_NAME: GenAIOperationName.GENERATE_CONTENT,
            Attributes.PROVIDER_NAME: self.provider_name,
            
        }
        if self._model:
            base_attrs[Attributes.REQUEST_MODEL] = self._model
            base_attrs[Attributes.RESPONSE_MODEL] = self._model

        if input_tokens is not None:
            _token_usage_histogram.record(
                input_tokens,
                {**base_attrs, Attributes.TOKEN_TYPE: "input"},
            )
        if output_tokens is not None:
            _token_usage_histogram.record(
                output_tokens,
                {**base_attrs, Attributes.TOKEN_TYPE: "output"},
            )

    def _maybe_record_ttft(self, response_id: str) -> None:
        """Record time-to-first-token once per response on the first content delta."""
        if response_id in self._first_token_recorded:
            return
        start_time = self._response_start_times.get(response_id)
        if start_time is None:
            return
        self._first_token_recorded.add(response_id)
        ttft = time.monotonic() - start_time
        ttft_attrs: dict[str, str] = {
            Attributes.OPERATION_NAME: "realtime_session",
            Attributes.PROVIDER_NAME: self.provider_name,
        }
        if self._model:
            ttft_attrs[Attributes.REQUEST_MODEL] = self._model
            ttft_attrs[Attributes.RESPONSE_MODEL] = self._model
        _time_to_first_token.record(ttft, ttft_attrs)


# ─── Helper utilities ─────────────────────────────────────────────────


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

    # Aggregate input/output tokens
    if usage.input_tokens is not None:
        attrs[Attributes.USAGE_INPUT_TOKENS] = usage.input_tokens
    elif Attributes.TOKEN_INPUT_AUDIO in attrs or Attributes.TOKEN_INPUT_TEXT in attrs:
        attrs[Attributes.USAGE_INPUT_TOKENS] = attrs.get(Attributes.TOKEN_INPUT_AUDIO, 0) + attrs.get(
            Attributes.TOKEN_INPUT_TEXT, 0
        )

    if usage.output_tokens is not None:
        attrs[Attributes.USAGE_OUTPUT_TOKENS] = usage.output_tokens
    elif Attributes.TOKEN_OUTPUT_AUDIO in attrs or Attributes.TOKEN_OUTPUT_TEXT in attrs:
        attrs[Attributes.USAGE_OUTPUT_TOKENS] = attrs.get(Attributes.TOKEN_OUTPUT_AUDIO, 0) + attrs.get(
            Attributes.TOKEN_OUTPUT_TEXT, 0
        )

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



