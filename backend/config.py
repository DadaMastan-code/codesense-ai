from __future__ import annotations

from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    # LLM
    groq_api_key: str = ""
    openai_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    openai_model: str = "gpt-4o"
    max_tokens: int = 4096
    temperature: float = 0.1
    request_timeout: int = 30

    # App
    rate_limit_per_minute: int = 10
    log_level: str = "INFO"
    environment: str = "development"

    # GitHub integration
    github_webhook_secret: str = ""
    github_token: str = ""

    # LangSmith tracing (optional)
    langsmith_api_key: str = ""
    langsmith_project: str = "codesense-ai"
    langsmith_tracing_enabled: bool = False

    # Evolution tracker
    evolution_db_path: str = "data/evolution.db"

    model_config = {"env_file": ".env", "case_sensitive": False}

    @property
    def primary_llm_provider(self) -> str:
        return "groq" if self.groq_api_key else "openai"

    @property
    def has_any_llm_key(self) -> bool:
        return bool(self.groq_api_key or self.openai_api_key)

    @property
    def tracing_enabled(self) -> bool:
        return bool(self.langsmith_api_key and self.langsmith_tracing_enabled)


@lru_cache
def get_settings() -> Settings:
    return Settings()
