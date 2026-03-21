"""Tests for alert decisioning and suppression logic."""

from unittest.mock import MagicMock

from src.schemas.scoring import ClientScoreResult
from src.scoring.alert_decisioner import (
    AlertDecision,
    decide_alert,
    make_suppression_key,
)


def _make_score(
    score: float = 80.0,
    should_alert: bool = True,
    disposition: str = "immediate",
    client_id: str = "client1",
    bill_id: str = "SB00093",
    version_id: str = "2026-SB00093-FC00044",
) -> ClientScoreResult:
    return ClientScoreResult(
        client_id=client_id,
        bill_id=bill_id,
        version_id=version_id,
        rules_score=score,
        final_score=score,
        urgency="high" if score >= 60 else "low",
        should_alert=should_alert,
        alert_disposition=disposition,
        match_reasons=[],
    )


def _mock_alert_repo(
    has_key: bool = False,
    has_recent: bool = False,
    existing_status: str = "sent",
):
    repo = MagicMock()
    repo.has_suppression_key.return_value = has_key
    if has_key:
        existing_alert = MagicMock()
        existing_alert.delivery_status = existing_status
        repo.get_by_suppression_key.return_value = existing_alert
    else:
        repo.get_by_suppression_key.return_value = None
    repo.get_recent_for_client_bill.return_value = MagicMock() if has_recent else None
    return repo


class TestMakeSuppressionKey:
    def test_deterministic(self):
        k1 = make_suppression_key("c1", "v1")
        k2 = make_suppression_key("c1", "v1")
        assert k1 == k2

    def test_different_inputs_different_keys(self):
        k1 = make_suppression_key("c1", "v1")
        k2 = make_suppression_key("c1", "v2")
        assert k1 != k2

    def test_length(self):
        key = make_suppression_key("c1", "v1")
        assert len(key) == 16


class TestDecideAlert:
    def test_below_threshold_suppressed(self):
        score = _make_score(score=20, should_alert=False, disposition="suppressed_below_threshold")
        repo = _mock_alert_repo()

        decision = decide_alert(score, client_db_id=1, bill_db_id=1, alert_repo=repo)

        assert decision.final_disposition == "suppressed_below_threshold"
        assert decision.should_create_alert is True  # record is still created
        assert decision.suppression_reason is not None

    def test_duplicate_suppressed(self):
        score = _make_score(score=80, should_alert=True, disposition="immediate")
        repo = _mock_alert_repo(has_key=True)

        decision = decide_alert(score, client_db_id=1, bill_db_id=1, alert_repo=repo)

        assert decision.final_disposition == "suppressed_duplicate"
        assert decision.should_create_alert is False

    def test_cooldown_suppressed(self):
        score = _make_score(score=80, should_alert=True, disposition="immediate")
        repo = _mock_alert_repo(has_key=False, has_recent=True)

        decision = decide_alert(score, client_db_id=1, bill_db_id=1, alert_repo=repo)

        assert decision.final_disposition == "suppressed_cooldown"
        assert decision.should_create_alert is True

    def test_immediate_passthrough(self):
        score = _make_score(score=80, should_alert=True, disposition="immediate")
        repo = _mock_alert_repo(has_key=False, has_recent=False)

        decision = decide_alert(score, client_db_id=1, bill_db_id=1, alert_repo=repo)

        assert decision.final_disposition == "immediate"
        assert decision.should_create_alert is True
        assert decision.suppression_reason is None

    def test_digest_passthrough(self):
        score = _make_score(score=45, should_alert=True, disposition="digest")
        repo = _mock_alert_repo(has_key=False, has_recent=False)

        decision = decide_alert(score, client_db_id=1, bill_db_id=1, alert_repo=repo)

        assert decision.final_disposition == "digest"
        assert decision.should_create_alert is True

    def test_suppression_order_threshold_before_duplicate(self):
        """Below-threshold should be checked before duplicate."""
        score = _make_score(score=20, should_alert=False, disposition="suppressed_below_threshold")
        # Even if duplicate key exists, threshold suppression takes priority
        repo = _mock_alert_repo(has_key=True)

        decision = decide_alert(score, client_db_id=1, bill_db_id=1, alert_repo=repo)

        assert decision.final_disposition == "suppressed_below_threshold"

    def test_failed_alert_not_suppressed_as_duplicate(self):
        """A failed/pending alert should not be suppressed as duplicate — allow retry."""
        score = _make_score(score=80, should_alert=True, disposition="immediate")
        repo = _mock_alert_repo(has_key=True, existing_status="failed")

        decision = decide_alert(score, client_db_id=1, bill_db_id=1, alert_repo=repo)

        # Should NOT be suppressed_duplicate; should pass through to cooldown/immediate
        assert decision.final_disposition != "suppressed_duplicate"
        assert decision.should_create_alert is True

    def test_pending_alert_not_suppressed_as_duplicate(self):
        """A pending alert should not be suppressed as duplicate — allow retry."""
        score = _make_score(score=80, should_alert=True, disposition="immediate")
        repo = _mock_alert_repo(has_key=True, existing_status="pending")

        decision = decide_alert(score, client_db_id=1, bill_db_id=1, alert_repo=repo)

        assert decision.final_disposition != "suppressed_duplicate"
        assert decision.should_create_alert is True

    def test_custom_cooldown(self):
        score = _make_score(score=80, should_alert=True, disposition="immediate")
        repo = _mock_alert_repo(has_key=False, has_recent=True)

        decision = decide_alert(
            score, client_db_id=1, bill_db_id=1, alert_repo=repo, cooldown_hours=48
        )

        assert decision.final_disposition == "suppressed_cooldown"
        repo.get_recent_for_client_bill.assert_called_with(1, 1, 48)
