from enum import StrEnum


class SpanName(StrEnum):
    SESSION_CREATED = "session.created"
    USER_INPUT = "user.input"
    AGENT_RESPONSE = "agent.response"
    FUNCTION_CALL = "tool.call"
