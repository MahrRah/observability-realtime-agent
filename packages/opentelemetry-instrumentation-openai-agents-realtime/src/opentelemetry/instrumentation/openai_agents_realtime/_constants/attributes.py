from __future__ import annotations

try:
    from opentelemetry.semconv._incubating.attributes import (
        gen_ai_attributes as GenAIAttributes,
    )
    from opentelemetry.semconv._incubating.attributes import (
        server_attributes as ServerAttributes,
    )
except ImportError:
    GenAIAttributes = None  # type: ignore[assignment, misc]
    ServerAttributes = None  # type: ignore[assignment, misc]


class Attributes:
    """Span/event attribute key constants.

    Values are sourced from the ``opentelemetry-semantic-conventions`` package
    when available, with hardcoded fallbacks for forward-compatibility.
    """

    SESSION_ID = "gen_ai.session.id"
    SESSION_OUTCOME = "gen_ai.session.outcome"
    OPERATION_NAME = "gen_ai.operation.name"
    PROVIDER_NAME = "gen_ai.provider.name"
    CONVERSATION_ID = "gen_ai.conversation.id"
    EVENT_NAME = "gen_ai.event.name"
    EVENT_ID = "gen_ai.event.id"
    ITEM_ID = "gen_ai.item.id"
    ITEM_AUDIO_END_MS = "gen_ai.item.audio_end_ms"
    RESPONSE_ID = "gen_ai.response.id"
    OUTPUT_TYPE = "gen_ai.output.type"
    TOOL_CALL_ID = "gen_ai.tool.call.id"
    TOOL_NAME = "gen_ai.tool.name"
    TOOL_TYPE = "gen_ai.tool.type"
    TOOL_CALL_ARGUMENTS = "gen_ai.tool.call.arguments"
    TOOL_CALL_RESULT = "gen_ai.tool.call.result"
    REQUEST_MODEL = "gen_ai.request.model"
    INSTRUCTIONS = "gen_ai.instructions"
    SESSION_EXPIRES_AT = "gen_ai.session.expires_at"
    SESSION_OBJECT = "gen_ai.session.object"
    SESSION_TYPE = "gen_ai.session.type"
    REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
    TOOL_CHOICE = "gen_ai.tool_choice"
    AUDIO_INPUT_FORMAT = "gen_ai.audio.input.format"
    AUDIO_INPUT_RATE = "gen_ai.audio.input.rate"
    AUDIO_INPUT_TRANSCRIPTION_MODEL = "gen_ai.audio.input.transcription.model"
    AUDIO_INPUT_TRANSCRIPTION_LANGUAGE = "gen_ai.audio.input.transcription.language"
    AUDIO_INPUT_TRANSCRIPTION_PROMPT = "gen_ai.audio.input.transcription.prompt"
    AUDIO_INPUT_NOISE_REDUCTION = "gen_ai.audio.input.noise_reduction"
    TURN_DETECTION_TYPE = "gen_ai.turn_detection.type"
    TURN_DETECTION_CREATE_RESPONSE = "gen_ai.turn_detection.create_response"
    TURN_DETECTION_INTERRUPT_RESPONSE = "gen_ai.turn_detection.interrupt_response"
    TURN_DETECTION_THRESHOLD = "gen_ai.turn_detection.threshold"
    TURN_DETECTION_PREFIX_PADDING_MS = "gen_ai.turn_detection.prefix_padding_ms"
    TURN_DETECTION_SILENCE_DURATION_MS = "gen_ai.turn_detection.silence_duration_ms"
    AUDIO_OUTPUT_FORMAT = "gen_ai.audio.output.format"
    AUDIO_OUTPUT_RATE = "gen_ai.audio.output.rate"
    AUDIO_OUTPUT_VOICE = "gen_ai.audio.output.voice"
    AUDIO_OUTPUT_SPEED = "gen_ai.audio.output.speed"
    TOKEN_TOTAL = "gen_ai.usage.total_tokens"
    TOKEN_INPUT_AUDIO = "gen_ai.usage.input_audio_tokens"
    TOKEN_INPUT_TEXT = "gen_ai.usage.input_text_tokens"
    TOKEN_INPUT_AUDIO_CACHED = "gen_ai.usage.input_audio_cached_tokens"
    TOKEN_INPUT_TEXT_CACHED = "gen_ai.usage.input_text_cached_tokens"
    TOKEN_OUTPUT_AUDIO = "gen_ai.usage.output_audio_tokens"
    TOKEN_OUTPUT_TEXT = "gen_ai.usage.output_text_tokens"
    USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
    USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
    AGENT_NAME = "gen_ai.agent.name"
    CONTENT_INDEX = "gen_ai.content_index" # for multimodal responses, which may have interleaved text and audio, this indicates the index of the content part (text/audio) that an event corresponds to

    # Response status
    RESPONSE_STATUS = "gen_ai.response.status"
    RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
    RESPONSE_MODEL = "gen_ai.response.model"
    RESPONSE_OUTPUT = "gen_ai.response.output"

    # Error
    ERROR_TYPE = "error.type"
    ERROR_CODE = "error.code"
    ERROR_MESSAGE = "error.message"

    # Metric attributes
    TOKEN_TYPE = "gen_ai.token.type"

    # Server attributes
    SERVER_ADDRESS = "server.address"
    SERVER_PORT = "server.port"

    # Rate limits
    RATE_LIMIT_NAME = "rate_limit.name"
    RATE_LIMIT_LIMIT = "rate_limit.limit"
    RATE_LIMIT_REMAINING = "rate_limit.remaining"
    RATE_LIMIT_RESET_SECONDS = "rate_limit.reset_seconds"



def _enum_values(enum_cls) -> dict[str, str]:
    """Return mapping of enum member name to value."""
    return {member.name: member.value for member in enum_cls}


_PROVIDER_VALUES = _enum_values(GenAIAttributes.GenAiProviderNameValues)


class GenAIProvider:
    OPENAI = _PROVIDER_VALUES["OPENAI"]
    GCP_GEN_AI = _PROVIDER_VALUES["GCP_GEN_AI"]
    GCP_VERTEX_AI = _PROVIDER_VALUES["GCP_VERTEX_AI"]
    GCP_GEMINI = _PROVIDER_VALUES["GCP_GEMINI"]
    ANTHROPIC = _PROVIDER_VALUES["ANTHROPIC"]
    COHERE = _PROVIDER_VALUES["COHERE"]
    AZURE_AI_INFERENCE = _PROVIDER_VALUES["AZURE_AI_INFERENCE"]
    AZURE_AI_OPENAI = _PROVIDER_VALUES["AZURE_AI_OPENAI"]
    IBM_WATSONX_AI = _PROVIDER_VALUES["IBM_WATSONX_AI"]
    AWS_BEDROCK = _PROVIDER_VALUES["AWS_BEDROCK"]
    PERPLEXITY = _PROVIDER_VALUES["PERPLEXITY"]
    X_AI = _PROVIDER_VALUES["X_AI"]
    DEEPSEEK = _PROVIDER_VALUES["DEEPSEEK"]
    GROQ = _PROVIDER_VALUES["GROQ"]
    MISTRAL_AI = _PROVIDER_VALUES["MISTRAL_AI"]

    ALL = set(_PROVIDER_VALUES.values())


_OPERATION_VALUES = _enum_values(GenAIAttributes.GenAiOperationNameValues)

class GenAIOperationName:
    CHAT = _OPERATION_VALUES["CHAT"]
    GENERATE_CONTENT = _OPERATION_VALUES["GENERATE_CONTENT"]
    TEXT_COMPLETION = _OPERATION_VALUES["TEXT_COMPLETION"]
    EMBEDDINGS = _OPERATION_VALUES["EMBEDDINGS"]
    CREATE_AGENT = _OPERATION_VALUES["CREATE_AGENT"]
    INVOKE_AGENT = _OPERATION_VALUES["INVOKE_AGENT"]
    EXECUTE_TOOL = _OPERATION_VALUES["EXECUTE_TOOL"]
    # Operations below are not yet covered by the spec but remain for backwards compatibility
    TRANSCRIPTION = "transcription"
    SPEECH = "speech_generation"
    GUARDRAIL = "guardrail_check"
    HANDOFF = "agent_handoff"
    RESPONSE = "response"  # internal aggregator in current processor

    CLASS_FALLBACK = {
        "generationspan": CHAT,
        "responsespan": RESPONSE,
        "functionspan": EXECUTE_TOOL,
        "agentspan": INVOKE_AGENT,
    }


