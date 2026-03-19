"""Tests for config settings loader."""

import pytest

from config.settings import Settings


class TestSettings:
    def test_loads_from_env(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("SESSION_YEAR", "2026")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.database_url == "sqlite:///test.db"
        assert settings.session_year == 2026

    def test_missing_database_url_raises(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        # Also ensure no .env file is loaded
        monkeypatch.setattr(
            "config.settings.Settings.model_config",
            {
                "env_file": None,
                "case_sensitive": False,
            },
        )
        with pytest.raises(Exception):
            Settings()  # type: ignore[call-arg]

    def test_is_production(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("APP_ENV", "production")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.is_production is True

    def test_not_production(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("APP_ENV", "development")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.is_production is False

    def test_llm_available(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.llm_available is True

    def test_llm_not_available(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("OPENAI_API_KEY", "")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.llm_available is False

    def test_telegram_available(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100123")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.telegram_available is True

    def test_defaults(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.cga_request_timeout_seconds == 30
        assert settings.cga_poll_interval_minutes == 20
        assert settings.default_timezone == "America/New_York"
