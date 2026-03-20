"""Alert decision engine with suppression rules.

Evaluates a ClientScoreResult against suppression rules (threshold,
duplicate, cooldown) and returns a final alert decision.
"""

import hashlib
import logging
from dataclasses import dataclass

from src.db.repositories.alerts import AlertRepository
from src.schemas.scoring import ClientScoreResult

logger = logging.getLogger(__name__)

# Default cooldown: don't re-alert for the same client+bill within 24 hours
DEFAULT_COOLDOWN_HOURS = 24


@dataclass
class AlertDecision:
    """Result of the alert decisioning process."""

    should_create_alert: bool
    final_disposition: str  # "immediate", "digest", or "suppressed_*"
    suppression_key: str
    suppression_reason: str | None = None


def make_suppression_key(client_id: str, version_id: str) -> str:
    """Create a deterministic suppression key for deduplication."""
    raw = f"{client_id}:{version_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def decide_alert(
    score: ClientScoreResult,
    client_db_id: int,
    bill_db_id: int,
    alert_repo: AlertRepository,
    cooldown_hours: int = DEFAULT_COOLDOWN_HOURS,
) -> AlertDecision:
    """Apply suppression rules and return an alert decision.

    Suppression rules are evaluated in order:
    1. Below-threshold suppression (score < client threshold)
    2. Duplicate suppression (same client+version already alerted)
    3. Cooldown suppression (recent alert for same client+bill)
    4. Pass through as immediate or digest
    """
    suppression_key = make_suppression_key(score.client_id, score.version_id)

    # Rule 1: Below-threshold suppression (already computed by scorer)
    if not score.should_alert:
        return AlertDecision(
            should_create_alert=True,  # still record the decision
            final_disposition="suppressed_below_threshold",
            suppression_key=suppression_key,
            suppression_reason=f"Score {score.final_score:.0f} below threshold",
        )

    # Rule 2: Duplicate suppression (same client+version)
    if alert_repo.has_suppression_key(suppression_key):
        return AlertDecision(
            should_create_alert=False,
            final_disposition="suppressed_duplicate",
            suppression_key=suppression_key,
            suppression_reason="Alert already exists for this client+version",
        )

    # Rule 3: Cooldown suppression (recent alert for same client+bill)
    recent = alert_repo.get_recent_for_client_bill(
        client_db_id, bill_db_id, cooldown_hours
    )
    if recent:
        return AlertDecision(
            should_create_alert=True,
            final_disposition="suppressed_cooldown",
            suppression_key=suppression_key,
            suppression_reason=f"Recent alert exists (within {cooldown_hours}h cooldown)",
        )

    # Rule 4: Pass through with original disposition
    return AlertDecision(
        should_create_alert=True,
        final_disposition=score.alert_disposition,
        suppression_key=suppression_key,
    )
