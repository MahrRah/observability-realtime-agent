from enum import StrEnum


class SpanName(StrEnum):
    SESSION_CREATED = "session.created"
    USER_INPUT = "user.input"
    ASSISTANT_RESPONSE = "assistant.response"
    FUNCTION_CALL = "function.call"
