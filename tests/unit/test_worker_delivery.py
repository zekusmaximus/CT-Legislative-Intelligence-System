"""Tests for one-shot worker delivery wiring.

Verifies that `python -m apps.worker.jobs daily|reconcile` correctly
constructs a TelegramSender when Telegram is configured, and omits it
when not configured.
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("APP_ENV", "development")

from unittest.mock import MagicMock, patch

from apps.worker.jobs import _make_telegram_sender


class TestMakeTelegramSender:
    """Verify _make_telegram_sender helper."""

    def test_returns_sender_when_telegram_configured(self):
        settings = MagicMock(
            telegram_available=True,
            telegram_alerts_enabled=True,
            telegram_bot_token="fake_token",
            telegram_chat_id="123",
        )
        session = MagicMock()

        sender = _make_telegram_sender(settings, session)

        assert sender is not None
        assert sender.bot_token == "fake_token"
        assert sender.default_chat_id == "123"
        assert sender.session is session

    def test_returns_none_when_telegram_not_available(self):
        settings = MagicMock(
            telegram_available=False,
            telegram_alerts_enabled=True,
        )
        session = MagicMock()

        assert _make_telegram_sender(settings, session) is None

    def test_returns_none_when_alerts_disabled(self):
        settings = MagicMock(
            telegram_available=True,
            telegram_alerts_enabled=False,
        )
        session = MagicMock()

        assert _make_telegram_sender(settings, session) is None


class TestWorkerPipelineWiring:
    """Verify that run_daily_pipeline and run_reconciliation wire the sender."""

    @patch("apps.worker.jobs._make_telegram_sender")
    @patch("apps.worker.jobs.Pipeline")
    @patch("apps.worker.jobs.LocalStorage")
    @patch("apps.worker.jobs.get_session_factory")
    @patch("apps.worker.jobs.get_settings")
    def test_daily_passes_sender_to_pipeline(
        self, mock_settings, mock_sf, mock_storage, mock_pipeline_cls, mock_make_sender
    ):
        from apps.worker.jobs import run_daily_pipeline

        mock_settings.return_value = MagicMock(
            database_url="sqlite:///:memory:",
            storage_local_dir="/tmp/test",
            session_year=2026,
            telegram_available=True,
            telegram_alerts_enabled=True,
            telegram_bot_token="tok",
            telegram_chat_id="123",
        )
        mock_session = MagicMock()
        mock_sf.return_value = MagicMock(
            __call__=MagicMock(return_value=MagicMock(
                __enter__=MagicMock(return_value=mock_session),
                __exit__=MagicMock(return_value=False),
            ))
        )
        mock_pipeline = MagicMock()
        mock_pipeline.run_daily.return_value = []
        mock_pipeline_cls.return_value = mock_pipeline
        mock_make_sender.return_value = MagicMock()

        run_daily_pipeline()

        # Pipeline should have been constructed with telegram_sender kwarg
        call_kwargs = mock_pipeline_cls.call_args
        assert "telegram_sender" in call_kwargs.kwargs
        assert call_kwargs.kwargs["telegram_sender"] is mock_make_sender.return_value

    @patch("apps.worker.jobs._make_telegram_sender")
    @patch("apps.worker.jobs.Pipeline")
    @patch("apps.worker.jobs.LocalStorage")
    @patch("apps.worker.jobs.get_session_factory")
    @patch("apps.worker.jobs.get_settings")
    def test_reconcile_passes_sender_to_pipeline(
        self, mock_settings, mock_sf, mock_storage, mock_pipeline_cls, mock_make_sender
    ):
        from apps.worker.jobs import run_reconciliation

        mock_settings.return_value = MagicMock(
            database_url="sqlite:///:memory:",
            storage_local_dir="/tmp/test",
            session_year=2026,
            telegram_available=True,
            telegram_alerts_enabled=True,
            telegram_bot_token="tok",
            telegram_chat_id="123",
        )
        mock_session = MagicMock()
        mock_sf.return_value = MagicMock(
            __call__=MagicMock(return_value=MagicMock(
                __enter__=MagicMock(return_value=mock_session),
                __exit__=MagicMock(return_value=False),
            ))
        )
        mock_pipeline = MagicMock()
        mock_pipeline.run_reconciliation.return_value = []
        mock_pipeline_cls.return_value = mock_pipeline
        mock_make_sender.return_value = MagicMock()

        run_reconciliation()

        call_kwargs = mock_pipeline_cls.call_args
        assert "telegram_sender" in call_kwargs.kwargs
        assert call_kwargs.kwargs["telegram_sender"] is mock_make_sender.return_value
