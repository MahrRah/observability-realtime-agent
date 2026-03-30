from enum import StrEnum


class MetricName(StrEnum):
    TOKENS = "gen_ai.realtime.tokens"
    FUNCTION_CALL = "gen_ai.realtime.function.call"
    FUNCTION_SUCCESS = "gen_ai.realtime.function.success"
    ERROR = "gen_ai.realtime.error"
