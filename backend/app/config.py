"""Central application configuration.

Follows implementation plan sections 6 (sliding window) and 17 (token mgmt).
All values are overridable via environment variables / .env file.
"""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Multi-LLM Research Chat"
    DATABASE_URL: str = "sqlite:///./research_chat.db"

    # Sliding window: number of recent COMPLETE turns sent to the LLM.
    MAX_CONTEXT_TURNS: int = 8

    # Token budgets (plan section 17). Estimator in services/token_counter.py.
    MAX_CONTEXT_TOKENS: int = 12000
    MAX_OUTPUT_TOKENS: int = 1024
    DEFAULT_TEMPERATURE: float = 0.7

    # Summarization triggers once total turns exceed this.
    SUMMARIZE_AFTER_TURNS: int = 16
    # How many oldest turns a summary may cover at once.
    SUMMARY_CHUNK_SIZE: int = 10

    # LLM behaviour
    LLM_TIMEOUT_SECONDS: float = 60.0
    LLM_MAX_RETRIES: int = 2

    # API keys (optional in V1; MockProvider works without keys)
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    CODECRAFT_API_KEY: str = ""
    CODECRAFT_BASE_URL: str = "https://codecraftapi.com/v1"

    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,https://multi-llm-chat-sandy.vercel.app"

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        """Railway injects postgres:// which SQLAlchemy 2.x no longer accepts."""
        if not v:
            return "sqlite:///./research_chat.db"
        if v.startswith("postgres://"):
            return "postgresql://" + v[len("postgres://"):]
        return v


settings = Settings()
