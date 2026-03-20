"""Telegram Bot API sender with retry-safe delivery.

Sends alert messages via the Telegram Bot API and tracks delivery state
on the Alert record. Retry-safe: each attempt increments delivery_attempts
and records errors; duplicate sends are prevented by checking delivery_status.
"""

import logging
import urllib.error
import urllib.parse
import urllib.request
import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.db.models import Alert

logger = logging.getLogger(__name__)

# Delivery status values
STATUS_PENDING = "pending"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

# Maximum retry attempts before marking as failed
MAX_DELIVERY_ATTEMPTS = 3

# Telegram Bot API timeout in seconds
SEND_TIMEOUT_SECONDS = 15


class TelegramSender:
    """Sends alert messages via the Telegram Bot API.

    Retry-safe: checks delivery_status before sending, increments attempts,
    and records errors. Does not re-send already-sent alerts.
    """

    def __init__(
        self,
        bot_token: str,
        default_chat_id: str,
        session: Session,
        enabled: bool = True,
    ):
        self.bot_token = bot_token
        self.default_chat_id = default_chat_id
        self.session = session
        self.enabled = enabled
        self._api_base = f"https://api.telegram.org/bot{bot_token}"

    def send_alert(
        self,
        alert: Alert,
        chat_id: str | None = None,
    ) -> bool:
        """Send a single alert via Telegram.

        Returns True if the message was sent successfully, False otherwise.
        Updates the Alert record with delivery state regardless of outcome.
        """
        target_chat = chat_id or self.default_chat_id

        # Guard: already sent
        if alert.delivery_status == STATUS_SENT:
            logger.info("Alert %d already sent, skipping", alert.id)
            return True

        # Guard: max attempts exceeded
        if alert.delivery_attempts >= MAX_DELIVERY_ATTEMPTS:
            alert.delivery_status = STATUS_FAILED
            self.session.flush()
            logger.warning(
                "Alert %d exceeded max delivery attempts (%d), marking failed",
                alert.id, MAX_DELIVERY_ATTEMPTS,
            )
            return False

        # Guard: not enabled (dev/test environments)
        if not self.enabled:
            logger.info("Telegram disabled, skipping alert %d", alert.id)
            alert.delivery_status = STATUS_SKIPPED
            self.session.flush()
            return False

        # Attempt delivery
        alert.delivery_attempts += 1
        alert.last_delivery_attempt_at = datetime.now(UTC)

        try:
            message_id = self._call_send_message(target_chat, alert.alert_text)
            alert.telegram_message_id = message_id
            alert.sent_at = datetime.now(UTC)
            alert.delivery_status = STATUS_SENT
            alert.delivery_error = None
            self.session.flush()
            logger.info(
                "Alert %d sent successfully (message_id=%s)", alert.id, message_id
            )
            return True

        except Exception as exc:
            error_msg = str(exc)[:500]
            alert.delivery_error = error_msg
            if alert.delivery_attempts >= MAX_DELIVERY_ATTEMPTS:
                alert.delivery_status = STATUS_FAILED
            self.session.flush()
            logger.error(
                "Alert %d delivery failed (attempt %d/%d): %s",
                alert.id, alert.delivery_attempts, MAX_DELIVERY_ATTEMPTS, error_msg,
            )
            return False

    def send_pending_alerts(self, alerts: list[Alert]) -> dict:
        """Send all pending alerts. Returns summary of results."""
        sent = 0
        failed = 0
        skipped = 0

        for alert in alerts:
            if alert.delivery_status == STATUS_SENT:
                skipped += 1
                continue

            if alert.alert_disposition not in ("immediate", "digest"):
                skipped += 1
                continue

            success = self.send_alert(alert)
            if success:
                sent += 1
            else:
                failed += 1

        return {"sent": sent, "failed": failed, "skipped": skipped}

    def send_digest(
        self,
        alerts: list[Alert],
        client_display_name: str,
        chat_id: str | None = None,
    ) -> bool:
        """Send a digest message combining multiple alerts.

        Returns True if the digest was sent, False otherwise.
        """
        target_chat = chat_id or self.default_chat_id

        if not alerts:
            return False

        if not self.enabled:
            for alert in alerts:
                alert.delivery_status = STATUS_SKIPPED
            self.session.flush()
            return False

        # Build digest text
        lines = [
            f"Legislative Digest for {client_display_name}",
            f"{len(alerts)} alert(s)",
            "",
        ]
        for i, alert in enumerate(alerts, 1):
            # Extract bill info from the alert text (first few lines)
            preview = alert.alert_text.split("\n")[:3]
            lines.append(f"{i}. " + " | ".join(preview))
            lines.append("")

        digest_text = "\n".join(lines)

        try:
            message_id = self._call_send_message(target_chat, digest_text)

            now = datetime.now(UTC)
            for alert in alerts:
                alert.telegram_message_id = message_id
                alert.sent_at = now
                alert.delivery_status = STATUS_SENT
                alert.delivery_attempts += 1
                alert.last_delivery_attempt_at = now
                alert.delivery_error = None

            self.session.flush()
            logger.info(
                "Digest sent for %s: %d alerts (message_id=%s)",
                client_display_name, len(alerts), message_id,
            )
            return True

        except Exception as exc:
            error_msg = str(exc)[:500]
            now = datetime.now(UTC)
            for alert in alerts:
                alert.delivery_attempts += 1
                alert.last_delivery_attempt_at = now
                alert.delivery_error = error_msg
                if alert.delivery_attempts >= MAX_DELIVERY_ATTEMPTS:
                    alert.delivery_status = STATUS_FAILED

            self.session.flush()
            logger.error("Digest delivery failed for %s: %s", client_display_name, error_msg)
            return False

    def _call_send_message(self, chat_id: str, text: str) -> str:
        """Call the Telegram Bot API sendMessage endpoint.

        Returns the message_id as a string.
        Raises on HTTP or API errors.
        """
        url = f"{self._api_base}/sendMessage"
        payload = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=SEND_TIMEOUT_SECONDS) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise RuntimeError(
                f"Telegram API HTTP {e.code}: {error_body}"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Telegram API connection error: {e.reason}") from e

        if not body.get("ok"):
            raise RuntimeError(
                f"Telegram API error: {body.get('description', 'unknown')}"
            )

        return str(body["result"]["message_id"])
