from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    azure_openai_endpoint: str = Field(
        description="Azure OpenAI resource endpoint (e.g., https://myresource.openai.azure.com)",
    )
    azure_openai_deployment: str = Field(
        default="gpt-4o-realtime-preview",
        description="Azure OpenAI deployment name for Realtime API",
    )
    agent_instructions: str = Field(
        default="You are a helpful voice assistant. Keep responses concise.",
        description="System instructions for the agent",
    )
    voice: str = Field(default="ash", description="TTS voice name")

    @property
    def azure_realtime_url(self) -> str:
        base = self.azure_openai_endpoint.rstrip("/").replace("https://", "")
        return f"wss://{base}/openai/v1/realtime?model={self.azure_openai_deployment}"
