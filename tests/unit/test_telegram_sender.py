"""Unit tests for TelegramSender."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.alerts.telegram_sender import (
    MAX_DELIVERY_ATTEMPTS,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENT,
    STATUS_SKIPPED,
    TelegramSender,
)
from src.db.models import Alert, Base, Bill, Client, FileCopy


@pytest.fixture
def sender_session():
    """Create an in-memory SQLite database and yield a session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _make_alert(session: Session, **overrides) -> Alert:
    """Create a minimal alert record for testing."""
    # Create prerequisite records
    bill = session.query(Bill).first()
    if not bill:
        bill = Bill(
            session_year=2026, bill_id="SB00001", chamber="S",
            bill_number_numeric=1, current_title="Test Bill",
        )
        session.add(bill)
        session.flush()

    fc = session.query(FileCopy).first()
    if not fc:
        fc = FileCopy(
            bill_id_fk=bill.id, session_year=2026, file_copy_number=1,
            canonical_version_id="2026-SB00001-FC00001",
            pdf_url="http://example.com/t.pdf",
        )
        session.add(fc)
        session.flush()

    client = session.query(Client).first()
    if not client:
        client = Client(client_id="test_client", display_name="Test Client")
        session.add(client)
        session.flush()

    defaults = dict(
        client_id_fk=client.id,
        bill_id_fk=bill.id,
        canonical_version_id="2026-SB00001-FC00001",
        urgency="high",
        alert_disposition="immediate",
        alert_text="Test alert text",
        suppression_key="test_key_001",
        delivery_status=STATUS_PENDING,
        delivery_attempts=0,
    )
    defaults.update(overrides)
    alert = Alert(**defaults)
    session.add(alert)
    session.flush()
    return alert


class TestTelegramSenderDisabled:
    def test_disabled_sender_skips(self, sender_session):
        """When disabled, alerts are marked as skipped."""
        sender = TelegramSender(
            bot_token="fake", default_chat_id="123",
            session=sender_session, enabled=False,
        )
        alert = _make_alert(sender_session)
        result = sender.send_alert(alert)

        assert result is False
        assert alert.delivery_status == STATUS_SKIPPED

    def test_disabled_sender_does_not_call_api(self, sender_session):
        """Disabled sender never calls the Telegram API."""
        sender = TelegramSender(
            bot_token="fake", default_chat_id="123",
            session=sender_session, enabled=False,
        )
        alert = _make_alert(sender_session)

        with patch.object(sender, "_call_send_message") as mock_send:
            sender.send_alert(alert)
            mock_send.assert_not_called()


class TestTelegramSenderEnabled:
    def test_successful_send(self, sender_session):
        """Successful send updates all delivery fields."""
        sender = TelegramSender(
            bot_token="fake", default_chat_id="123",
            session=sender_session, enabled=True,
        )
        alert = _make_alert(sender_session)

        with patch.object(sender, "_call_send_message", return_value="42"):
            result = sender.send_alert(alert)

        assert result is True
        assert alert.delivery_status == STATUS_SENT
        assert alert.telegram_message_id == "42"
        assert alert.sent_at is not None
        assert alert.delivery_attempts == 1
        assert alert.delivery_error is None

    def test_already_sent_skips(self, sender_session):
        """Already-sent alerts are not re-sent."""
        sender = TelegramSender(
            bot_token="fake", default_chat_id="123",
            session=sender_session, enabled=True,
        )
        alert = _make_alert(sender_session, delivery_status=STATUS_SENT)

        with patch.object(sender, "_call_send_message") as mock_send:
            result = sender.send_alert(alert)
            mock_send.assert_not_called()

        assert result is True

    def test_api_failure_records_error(self, sender_session):
        """API failure records the error and increments attempts."""
        sender = TelegramSender(
            bot_token="fake", default_chat_id="123",
            session=sender_session, enabled=True,
        )
        alert = _make_alert(sender_session)

        with patch.object(sender, "_call_send_message", side_effect=RuntimeError("API down")):
            result = sender.send_alert(alert)

        assert result is False
        assert alert.delivery_attempts == 1
        assert "API down" in alert.delivery_error

    def test_max_attempts_marks_failed(self, sender_session):
        """After max attempts, alert is marked as failed."""
        sender = TelegramSender(
            bot_token="fake", default_chat_id="123",
            session=sender_session, enabled=True,
        )
        alert = _make_alert(sender_session, delivery_attempts=MAX_DELIVERY_ATTEMPTS - 1)

        with patch.object(sender, "_call_send_message", side_effect=RuntimeError("fail")):
            sender.send_alert(alert)

        assert alert.delivery_status == STATUS_FAILED
        assert alert.delivery_attempts == MAX_DELIVERY_ATTEMPTS

    def test_exceeded_max_attempts_skips(self, sender_session):
        """Alerts that already exceeded max attempts are immediately marked failed."""
        sender = TelegramSender(
            bot_token="fake", default_chat_id="123",
            session=sender_session, enabled=True,
        )
        alert = _make_alert(sender_session, delivery_attempts=MAX_DELIVERY_ATTEMPTS)

        with patch.object(sender, "_call_send_message") as mock_send:
            result = sender.send_alert(alert)
            mock_send.assert_not_called()

        assert result is False
        assert alert.delivery_status == STATUS_FAILED


class TestSendPendingAlerts:
    def test_sends_only_actionable(self, sender_session):
        """send_pending_alerts only sends immediate/digest alerts."""
        sender = TelegramSender(
            bot_token="fake", default_chat_id="123",
            session=sender_session, enabled=True,
        )
        a1 = _make_alert(sender_session, suppression_key="k1", alert_disposition="immediate")
        a2 = _make_alert(sender_session, suppression_key="k2", alert_disposition="suppressed_below_threshold")

        with patch.object(sender, "_call_send_message", return_value="99"):
            result = sender.send_pending_alerts([a1, a2])

        assert result["sent"] == 1
        assert result["skipped"] == 1

    def test_batch_results(self, sender_session):
        """Batch send returns correct counts."""
        sender = TelegramSender(
            bot_token="fake", default_chat_id="123",
            session=sender_session, enabled=True,
        )
        a1 = _make_alert(sender_session, suppression_key="k3", alert_disposition="immediate")
        a2 = _make_alert(sender_session, suppression_key="k4", alert_disposition="digest")

        call_count = 0
        def mock_send(chat_id, text):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "100"
            raise RuntimeError("fail")

        with patch.object(sender, "_call_send_message", side_effect=mock_send):
            result = sender.send_pending_alerts([a1, a2])

        assert result["sent"] == 1
        assert result["failed"] == 1


class TestDigestSend:
    def test_digest_sends_combined_message(self, sender_session):
        """Digest combines multiple alerts into one message."""
        sender = TelegramSender(
            bot_token="fake", default_chat_id="123",
            session=sender_session, enabled=True,
        )
        a1 = _make_alert(sender_session, suppression_key="d1", alert_disposition="digest")
        a2 = _make_alert(sender_session, suppression_key="d2", alert_disposition="digest")

        with patch.object(sender, "_call_send_message", return_value="200") as mock:
            result = sender.send_digest([a1, a2], "Test Client")

        assert result is True
        # Both alerts should be marked sent
        assert a1.delivery_status == STATUS_SENT
        assert a2.delivery_status == STATUS_SENT
        assert a1.telegram_message_id == "200"
        # Only one API call for the combined message
        assert mock.call_count == 1

    def test_disabled_digest_skips(self, sender_session):
        """Disabled sender marks digest alerts as skipped."""
        sender = TelegramSender(
            bot_token="fake", default_chat_id="123",
            session=sender_session, enabled=False,
        )
        a1 = _make_alert(sender_session, suppression_key="d3", alert_disposition="digest")

        result = sender.send_digest([a1], "Test Client")

        assert result is False
        assert a1.delivery_status == STATUS_SKIPPED
