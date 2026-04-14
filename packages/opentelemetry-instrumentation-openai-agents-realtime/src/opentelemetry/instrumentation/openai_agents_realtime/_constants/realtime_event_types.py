from enum import StrEnum


class RealtimeEventType(StrEnum):
    """Event type strings for the OpenAI Realtime GA API.

    Used on both the server (Python match) and referenced by the browser
    (JavaScript switch).  Keep in sync with static/index.html.
    """

    # Audio transport
    AUDIO_DELTA = "response.output_audio.delta"
    AUDIO_DONE = "response.output_audio.done"
    SPEECH_STARTED = "input_audio_buffer.speech_started"
    SPEECH_STOPPED = "input_audio_buffer.speech_stopped"

    # Agent transcript
    TRANSCRIPT_DELTA = "response.output_audio_transcript.delta"
    TRANSCRIPT_DONE = "response.output_audio_transcript.done"

    # User input transcription
    INPUT_TRANSCRIPTION_COMPLETED = "conversation.item.input_audio_transcription.completed"
    INPUT_TRANSCRIPTION_FAILED = "conversation.item.input_audio_transcription.failed"

    # Session lifecycle
    SESSION_CREATED = "session.created"
    SESSION_UPDATED = "session.updated"
    CONVERSATION_CREATED = "conversation.created"
    RESPONSE_CREATED = "response.created"
    RESPONSE_DONE = "response.done"
    ERROR = "error"
    RATE_LIMITS_UPDATED = "rate_limits.updated"

    # Function calls
    FUNCTION_CALL = "response.function_call_arguments.done"

    # MCP tool calls
    MCP_CALL_ARGUMENTS_DONE = "response.mcp_call_arguments.done"
    MCP_CALL_IN_PROGRESS = "response.mcp_call.in_progress"
    MCP_CALL_COMPLETED = "response.mcp_call.completed"
    MCP_CALL_FAILED = "response.mcp_call.failed"
    MCP_LIST_TOOLS_IN_PROGRESS = "mcp_list_tools.in_progress"
    MCP_LIST_TOOLS_COMPLETED = "mcp_list_tools.completed"
    MCP_LIST_TOOLS_FAILED = "mcp_list_tools.failed"

    # Conversation items
    CONVERSATION_ITEM_ADDED = "conversation.item.added"
    CONVERSATION_ITEM_TRUNCATED = "conversation.item.truncated"

    # Audio buffer events
    INPUT_AUDIO_BUFFER_COMMITTED = "input_audio_buffer.committed"
    INPUT_AUDIO_BUFFER_TIMEOUT_TRIGGERED = "input_audio_buffer.timeout_triggered"

    # Text output streaming
    TEXT_DELTA = "response.output_text.delta"
    TEXT_DONE = "response.output_text.done"

    # Virtual type (span attribute value only)
    USER_INPUT = "user_input"
