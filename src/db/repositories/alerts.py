"""Repository for alert persistence and suppression checks."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from src.db.models import Alert

logger = logging.getLogger(__name__)


class AlertRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_alert(
        self,
        client_db_id: int,
        bill_db_id: int,
        canonical_version_id: str,
        urgency: str,
        alert_disposition: str,
        alert_text: str,
        suppression_key: str,
    ) -> Alert:
        """Create an alert record. Idempotent by suppression_key."""
        existing = (
            self.session.query(Alert)
            .filter_by(suppression_key=suppression_key)
            .first()
        )
        if existing:
            return existing

        alert = Alert(
            client_id_fk=client_db_id,
            bill_id_fk=bill_db_id,
            canonical_version_id=canonical_version_id,
            urgency=urgency,
            alert_disposition=alert_disposition,
            alert_text=alert_text,
            suppression_key=suppression_key,
        )
        self.session.add(alert)
        self.session.flush()
        return alert

    def has_suppression_key(self, suppression_key: str) -> bool:
        """Check if an alert with this suppression key already exists."""
        return (
            self.session.query(Alert)
            .filter_by(suppression_key=suppression_key)
            .first()
        ) is not None

    def get_recent_for_client_bill(
        self,
        client_db_id: int,
        bill_db_id: int,
        cooldown_hours: int = 24,
    ) -> Alert | None:
        """Get the most recent alert for a client-bill pair within the cooldown window."""
        cutoff = datetime.now(UTC) - timedelta(hours=cooldown_hours)
        return (
            self.session.query(Alert)
            .filter(
                Alert.client_id_fk == client_db_id,
                Alert.bill_id_fk == bill_db_id,
                Alert.created_at >= cutoff,
                Alert.alert_disposition.in_(["immediate", "digest"]),
            )
            .order_by(Alert.created_at.desc())
            .first()
        )

    def mark_sent(self, alert_id: int, telegram_message_id: str) -> None:
        """Update an alert as sent."""
        alert = self.session.get(Alert, alert_id)
        if alert:
            alert.sent_at = datetime.now(UTC)
            alert.telegram_message_id = telegram_message_id
            self.session.flush()

    def get_unsent_digests(self, client_db_id: int) -> list[Alert]:
        """Get unsent digest alerts for a client."""
        return (
            self.session.query(Alert)
            .filter(
                Alert.client_id_fk == client_db_id,
                Alert.alert_disposition == "digest",
                Alert.sent_at.is_(None),
            )
            .order_by(Alert.created_at)
            .all()
        )
