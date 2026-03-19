"""Typed application settings loaded from environment variables."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Database (required — fail fast if missing)
    database_url: str = Field(
        ...,
        description="Database connection URL. PostgreSQL for prod, SQLite for dev.",
    )

    # Storage
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_dir: Path = Path("./var/storage")
    storage_s3_bucket: str = ""
    storage_s3_region: str = ""
    storage_s3_endpoint: str = ""
    storage_s3_access_key_id: str = ""
    storage_s3_secret_access_key: str = ""

    # LLM
    openai_api_key: str = ""
    openai_model_summary: str = "gpt-4o"
    openai_model_reasoning: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_alerts_enabled: bool = False

    # CGA scraping
    cga_request_timeout_seconds: int = 30
    cga_poll_interval_minutes: int = 20

    # OCR
    ocr_enabled: bool = True
    tesseract_cmd: str = "tesseract"

    # Session
    default_timezone: str = "America/New_York"
    session_year: int = 2026

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def llm_available(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def telegram_available(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
