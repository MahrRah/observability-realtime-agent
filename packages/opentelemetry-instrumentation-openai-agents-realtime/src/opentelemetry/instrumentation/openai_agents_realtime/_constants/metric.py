from enum import StrEnum


class MetricName(StrEnum):
    TOKEN_USAGE = "gen_ai.client.token.usage"
    OPERATION_DURATION = "gen_ai.client.operation.duration"
    TIME_TO_FIRST_TOKEN = "gen_ai.server.time_to_first_token"
    FUNCTION_CALL = "gen_ai.realtime.function.call"
    FUNCTION_SUCCESS = "gen_ai.realtime.function.success"
    ERROR = "gen_ai.realtime.error"
