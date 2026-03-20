"""Tests for monitoring helpers and error budget tracking."""

import pytest
from datetime import UTC, datetime

from src.db.models import Alert, Bill, BillTextExtraction, Client, PipelineRun
from src.monitoring import (
    DELIVERY_FAILURE_BUDGET,
    MIN_EXTRACTION_CONFIDENCE,
    PIPELINE_FAILURE_BUDGET,
    compute_error_budget,
    get_system_health,
)


class TestErrorBudget:
    def test_no_data_returns_healthy(self, db_session):
        budget = compute_error_budget(db_session)
        assert budget.pipeline_runs_total == 0
        assert budget.pipeline_failure_rate == 0.0
        assert budget.pipeline_budget_remaining == PIPELINE_FAILURE_BUDGET
        assert budget.delivery_budget_remaining == DELIVERY_FAILURE_BUDGET
        assert budget.healthy is True

    def test_all_runs_succeeded(self, db_session):
        for _ in range(10):
            db_session.add(PipelineRun(run_type="daily", status="completed"))
        db_session.flush()

        budget = compute_error_budget(db_session)
        assert budget.pipeline_runs_total == 10
        assert budget.pipeline_runs_failed == 0
        assert budget.pipeline_failure_rate == 0.0
        assert budget.healthy is True

    def test_failure_rate_exceeds_budget(self, db_session):
        # 2 out of 10 failed = 20% > 5% budget
        for _ in range(8):
            db_session.add(PipelineRun(run_type="daily", status="completed"))
        for _ in range(2):
            db_session.add(PipelineRun(run_type="daily", status="failed"))
        db_session.flush()

        budget = compute_error_budget(db_session)
        assert budget.pipeline_runs_total == 10
        assert budget.pipeline_runs_failed == 2
        assert budget.pipeline_failure_rate == pytest.approx(0.2)
        assert budget.pipeline_budget_remaining < 0
        assert budget.healthy is False

    def test_delivery_failures_tracked(self, db_session):
        bill = Bill(session_year=2026, bill_id="SB99", chamber="senate", bill_number_numeric=99, current_title="Test")
        client = Client(client_id="test", display_name="Test")
        db_session.add_all([bill, client])
        db_session.flush()

        # 1 sent, 1 failed
        db_session.add(Alert(
            client_id_fk=client.id, bill_id_fk=bill.id,
            canonical_version_id="2026-SB99-FC00001",
            urgency="high", alert_disposition="immediate",
            alert_text="ok", delivery_status="sent",
            suppression_key="mon_test_key_1",
        ))
        db_session.add(Alert(
            client_id_fk=client.id, bill_id_fk=bill.id,
            canonical_version_id="2026-SB99-FC00002",
            urgency="high", alert_disposition="immediate",
            alert_text="fail", delivery_status="failed",
            suppression_key="mon_test_key_2",
        ))
        db_session.flush()

        budget = compute_error_budget(db_session)
        assert budget.delivery_attempts_total == 2
        assert budget.delivery_failures == 1
        assert budget.delivery_failure_rate == pytest.approx(0.5)
        assert budget.healthy is False

    def test_low_extraction_confidence(self, db_session):
        db_session.add(BillTextExtraction(
            canonical_version_id="2026-SB99-FC00001",
            full_raw_text="x",
            full_cleaned_text="x",
            overall_extraction_confidence=0.3,
        ))
        db_session.flush()

        budget = compute_error_budget(db_session)
        assert budget.avg_extraction_confidence == pytest.approx(0.3)
        assert budget.extraction_below_target is True
        assert budget.healthy is False


class TestSystemHealth:
    def test_healthy_when_clean(self, db_session):
        report = get_system_health(db_session)
        # No runs = healthy (no data is not an error)
        assert report.status == "healthy"
        assert report.last_successful_run is None

    def test_unhealthy_when_failed_alerts_exist(self, db_session):
        """Failed alerts blow delivery error budget → unhealthy."""
        bill = Bill(session_year=2026, bill_id="SB99", chamber="senate", bill_number_numeric=99, current_title="Test")
        client = Client(client_id="test", display_name="Test")
        db_session.add_all([bill, client])
        db_session.flush()

        db_session.add(Alert(
            client_id_fk=client.id, bill_id_fk=bill.id,
            canonical_version_id="2026-SB99-FC00001",
            urgency="high", alert_disposition="immediate",
            alert_text="fail", delivery_status="failed",
            suppression_key="health_test_key_1",
        ))
        db_session.flush()

        report = get_system_health(db_session)
        assert report.status == "unhealthy"
        assert report.failed_alerts == 1
