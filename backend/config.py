"""Single source of truth for backend configuration and OpenAI model selection."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings are intentionally server-only and read from the environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", validation_alias="OPENAI_MODEL")
    openai_timeout_seconds: int = Field(default=45, validation_alias="OPENAI_TIMEOUT_SECONDS", ge=5, le=120)
    openai_max_retries: int = Field(default=2, validation_alias="OPENAI_MAX_RETRIES", ge=0, le=4)
    cache_ttl_seconds: int = Field(default=900, validation_alias="DEALLENS_CACHE_TTL_SECONDS", ge=30)
    max_pitch_deck_mb: int = Field(default=10, validation_alias="DEALLENS_MAX_PITCH_DECK_MB", ge=1, le=25)
    database_url: SecretStr | None = Field(default=None, validation_alias="DATABASE_URL")
    database_connect_timeout_seconds: int = Field(default=10, validation_alias="DATABASE_CONNECT_TIMEOUT_SECONDS", ge=3, le=30)
    app_env: str = Field(default="development", validation_alias="APP_ENV")
    frontend_origin: str = Field(default="http://localhost:3000", validation_alias="FRONTEND_ORIGIN")
    github_token: SecretStr | None = Field(default=None, validation_alias="GITHUB_TOKEN")
    worker_poll_seconds: float = Field(default=2.0, validation_alias="WORKER_POLL_SECONDS", ge=0.5, le=30)
    job_stale_minutes: int = Field(default=15, validation_alias="JOB_STALE_MINUTES", ge=1, le=120)
    job_max_attempts: int = Field(default=2, validation_alias="JOB_MAX_ATTEMPTS", ge=1, le=5)

    def require_openai(self) -> str:
        """Return the key or raise a safe, actionable configuration error."""
        if self.openai_api_key is None or not self.openai_api_key.get_secret_value().strip():
            raise OpenAIConfigurationError(
                "OPENAI_API_KEY is not configured. Add it to the backend environment or .env file; it is never read by the frontend."
            )
        return self.openai_api_key.get_secret_value()

    def require_database(self) -> str:
        if self.database_url is None or not self.database_url.get_secret_value().strip():
            raise DatabaseConfigurationError("DATABASE_URL is not configured on the backend.")
        return self.database_url.get_secret_value()


class OpenAIConfigurationError(RuntimeError):
    pass


class DatabaseConfigurationError(RuntimeError):
    pass


@lru_cache
def get_settings() -> Settings:
    return Settings()
