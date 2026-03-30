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
    RESPONSE_CREATED = "response.created"
    RESPONSE_DONE = "response.done"
    ERROR = "error"
    RATE_LIMITS_UPDATED = "rate_limits.updated"

    # Function calls
    FUNCTION_CALL = "response.function_call_arguments.done"

    # Conversation items
    CONVERSATION_ITEM_ADDED = "conversation.item.added"
    CONVERSATION_ITEM_TRUNCATED = "conversation.item.truncated"

    # Virtual type (span attribute value only)
    USER_INPUT = "user_input"
