import logging
import random

from agents import function_tool
from agents.realtime import RealtimeAgent

logger = logging.getLogger(__name__)


@function_tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""

    logger.info("Fetching weather for city: %s", city)

    temp_c = random.randint(-10, 40)
    return f"{temp_c}°C in {city}"


def create_agent(instructions: str) -> RealtimeAgent:
    """Create a RealtimeAgent with the given instructions and tools."""

    return RealtimeAgent(
        name="Assistant",
        instructions=instructions,
        tools=[get_weather],
    )
