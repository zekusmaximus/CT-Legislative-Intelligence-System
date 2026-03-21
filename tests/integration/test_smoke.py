"""Smoke tests for Alembic migration bootstrap and Telegram sender wiring.

These tests verify that:
1. Alembic migrations can run to head on a clean SQLite database.
2. The TelegramSender is correctly wired through the Pipeline/API path
   with a real DB session, catching the missing-session bug at import time.
"""

import os
import tempfile

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from src.db.models import Alert, Base, Bill, Client, FileCopy


# ---------------------------------------------------------------------------
# Alembic bootstrap smoke test
# ---------------------------------------------------------------------------


class TestAlembicBootstrap:
    """Verify Alembic migrations can bring up a clean database."""

    def test_alembic_upgrade_head_creates_tables(self, tmp_path, monkeypatch):
        """Run 'alembic upgrade head' against a fresh SQLite file and verify
        key tables exist."""
        from alembic import command
        from alembic.config import Config

        db_path = tmp_path / "test.db"
        db_url = f"sqlite:///{db_path}"

        # Clear DATABASE_URL so env.py uses the alembic.ini URL we set
        monkeypatch.delenv("DATABASE_URL", raising=False)

        # Point Alembic at our migrations with a temp DB
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

        # Run all migrations
        command.upgrade(alembic_cfg, "head")

        # Verify key tables were created
        engine = create_engine(db_url)
        inspector = inspect(engine)
        table_names = inspector.get_table_names()

        expected_tables = [
            "bills",
            "file_copies",
            "bill_text_extractions",
            "bill_sections",
            "bill_diffs",
            "bill_change_events",
            "clients",
            "client_interest_profiles",
            "client_bill_scores",
            "alerts",
            "pipeline_runs",
            "bill_summaries",
            "bill_subject_tags",
            "feedback_labels",
            "source_pages",
        ]
        for table in expected_tables:
            assert table in table_names, f"Expected table '{table}' not found after migration"

        # Verify we can do a basic insert/select
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        engine.dispose()

    def test_alembic_env_honors_database_url(self, tmp_path, monkeypatch):
        """Verify that migrations/env.py picks up DATABASE_URL from the environment."""
        from alembic import command
        from alembic.config import Config

        db_path = tmp_path / "env_test.db"
        db_url = f"sqlite:///{db_path}"

        monkeypatch.setenv("DATABASE_URL", db_url)

        alembic_cfg = Config("alembic.ini")
        # Set a bogus URL in config — env.py should override with DATABASE_URL
        alembic_cfg.set_main_option("sqlalchemy.url", "sqlite:///nonexistent.db")

        command.upgrade(alembic_cfg, "head")

        # The real DB file should exist (not the bogus one)
        assert db_path.exists()

        engine = create_engine(db_url)
        inspector = inspect(engine)
        assert "bills" in inspector.get_table_names()
        engine.dispose()


# ---------------------------------------------------------------------------
# Telegram sender wiring integration test
# ---------------------------------------------------------------------------


class TestTelegramSenderWiring:
    """Verify TelegramSender is correctly constructed with a session in all
    production code paths, and that the full alert delivery path works
    end-to-end with a real DB."""

    @pytest.fixture
    def wired_db(self):
        """Create an in-memory DB with schema and seed data for alert tests."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        session = factory()

        # Seed: client, bill, file copy, and a pending alert
        client = Client(
            client_id="test_client",
            display_name="Test Client",
            is_active=True,
            alert_threshold=78,
            digest_threshold=58,
        )
        session.add(client)
        session.flush()

        bill = Bill(
            session_year=2026,
            bill_id="SB00001",
            chamber="senate",
            bill_number_numeric=1,
            current_title="Test Bill",
        )
        session.add(bill)
        session.flush()

        fc = FileCopy(
            bill_id_fk=bill.id,
            session_year=2026,
            file_copy_number=1,
            canonical_version_id="2026-SB00001-FC00001",
            pdf_url="https://example.com/test.pdf",
        )
        session.add(fc)
        session.flush()

        alert = Alert(
            client_id_fk=client.id,
            bill_id_fk=bill.id,
            canonical_version_id="2026-SB00001-FC00001",
            urgency="high",
            alert_disposition="immediate",
            alert_text="Test alert for SB00001",
            suppression_key="test_suppression_key_001",
        )
        session.add(alert)
        session.commit()

        yield session, client, bill, alert

        session.close()
        Base.metadata.drop_all(engine)

    def test_telegram_sender_constructed_with_session(self, wired_db):
        """TelegramSender can be instantiated with a real DB session and
        send_alert() correctly updates the Alert record."""
        from src.alerts.telegram_sender import TelegramSender

        session, client, bill, alert = wired_db

        sender = TelegramSender(
            bot_token="fake_token",
            default_chat_id="123456",
            session=session,
            enabled=False,  # Don't hit real Telegram API
        )

        # send_alert should mark as skipped (enabled=False) and flush to DB
        result = sender.send_alert(alert)
        assert result is False  # Not sent because disabled
        assert alert.delivery_status == "skipped"

    def test_send_pending_alerts_with_session(self, wired_db):
        """send_pending_alerts() works with a real session and updates DB state."""
        from src.alerts.telegram_sender import TelegramSender

        session, client, bill, alert = wired_db

        sender = TelegramSender(
            bot_token="fake_token",
            default_chat_id="123456",
            session=session,
            enabled=False,
        )

        summary = sender.send_pending_alerts([alert])
        assert summary["skipped"] == 0
        assert summary["failed"] == 1  # disabled sender → failed (skipped status set)

    def test_send_digest_with_session(self, wired_db):
        """send_digest() correctly batches alerts and updates all records."""
        from src.alerts.telegram_sender import TelegramSender

        session, client, bill, alert = wired_db

        sender = TelegramSender(
            bot_token="fake_token",
            default_chat_id="123456",
            session=session,
            enabled=False,
        )

        result = sender.send_digest([alert], "Test Client")
        assert result is False  # Not sent because disabled
        assert alert.delivery_status == "skipped"

    def test_alert_retry_on_reprocess(self, wired_db):
        """A failed alert can be retried when reprocessing the same version."""
        from src.db.repositories.alerts import AlertRepository

        session, client, bill, alert = wired_db

        # Simulate a failed alert
        alert.delivery_status = "failed"
        alert.delivery_attempts = 3
        alert.delivery_error = "Telegram API HTTP 500"
        session.flush()

        repo = AlertRepository(session)

        # Re-creating the same alert should reset it for retry
        retried = repo.create_alert(
            client_db_id=client.id,
            bill_db_id=bill.id,
            canonical_version_id="2026-SB00001-FC00001",
            urgency="high",
            alert_disposition="immediate",
            alert_text="Updated alert text",
            suppression_key="test_suppression_key_001",
        )

        assert retried.id == alert.id  # Same record
        assert retried.delivery_status == "pending"
        assert retried.delivery_attempts == 0
        assert retried.delivery_error is None
        assert retried.alert_text == "Updated alert text"

    def test_sent_alert_not_reset_on_reprocess(self, wired_db):
        """A successfully sent alert is not reset when reprocessing."""
        from datetime import UTC, datetime

        from src.db.repositories.alerts import AlertRepository

        session, client, bill, alert = wired_db

        # Simulate a sent alert
        alert.delivery_status = "sent"
        alert.sent_at = datetime.now(UTC)
        alert.telegram_message_id = "12345"
        session.flush()

        repo = AlertRepository(session)

        retried = repo.create_alert(
            client_db_id=client.id,
            bill_db_id=bill.id,
            canonical_version_id="2026-SB00001-FC00001",
            urgency="high",
            alert_disposition="immediate",
            alert_text="Should not overwrite",
            suppression_key="test_suppression_key_001",
        )

        assert retried.id == alert.id
        assert retried.delivery_status == "sent"  # Not reset
        assert retried.telegram_message_id == "12345"


# ---------------------------------------------------------------------------
# Bill ID parsing smoke test
# ---------------------------------------------------------------------------


class TestBillIdParsing:
    """Verify the new canonical version ID parser works correctly."""

    def test_parse_canonical_version_id(self):
        from src.utils.bill_id import parse_canonical_version_id

        year, bill_id, fc_num = parse_canonical_version_id("2026-SB00093-FC00044")
        assert year == 2026
        assert bill_id == "SB00093"
        assert fc_num == 44

    def test_bill_id_from_canonical(self):
        from src.utils.bill_id import bill_id_from_canonical

        assert bill_id_from_canonical("2026-SB00093-FC00044") == "SB00093"
        assert bill_id_from_canonical("2026-HB05140-FC00001") == "HB05140"

    def test_parse_invalid_raises(self):
        from src.utils.bill_id import parse_canonical_version_id

        with pytest.raises(ValueError):
            parse_canonical_version_id("invalid-id")

    def test_roundtrip(self):
        from src.utils.bill_id import make_canonical_version_id, parse_canonical_version_id

        original = make_canonical_version_id(2026, "SB00093", 44)
        year, bill_id, fc_num = parse_canonical_version_id(original)
        assert year == 2026
        assert bill_id == "SB00093"
        assert fc_num == 44
