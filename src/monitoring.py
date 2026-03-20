"""Monitoring helpers and error budget tracking.

Provides lightweight operational health checks that can be queried
via the API or examined by operators during session.

Error budget model:
  - Target: ≤5% pipeline run failure rate per rolling 24h window
  - Target: ≤2% alert delivery failure rate per rolling 24h window
  - Target: ≥80% average extraction confidence across versions
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.db.models import Alert, BillTextExtraction, PipelineRun

logger = logging.getLogger(__name__)

# Error budget thresholds
PIPELINE_FAILURE_BUDGET = 0.05  # 5% failure rate allowed
DELIVERY_FAILURE_BUDGET = 0.02  # 2% delivery failure rate
MIN_EXTRACTION_CONFIDENCE = 0.80  # target average confidence


@dataclass
class ErrorBudgetStatus:
    """Current error budget consumption."""

    window_hours: int
    pipeline_runs_total: int
    pipeline_runs_failed: int
    pipeline_failure_rate: float
    pipeline_budget_remaining: float

    delivery_attempts_total: int
    delivery_failures: int
    delivery_failure_rate: float
    delivery_budget_remaining: float

    avg_extraction_confidence: float | None
    extraction_below_target: bool

    @property
    def healthy(self) -> bool:
        return (
            self.pipeline_budget_remaining > 0
            and self.delivery_budget_remaining > 0
            and not self.extraction_below_target
        )


@dataclass
class SystemHealthReport:
    """Comprehensive system health snapshot."""

    status: str  # "healthy", "degraded", "unhealthy"
    last_successful_run: datetime | None
    hours_since_last_run: float | None
    pending_alerts: int
    failed_alerts: int
    error_budget: ErrorBudgetStatus


def compute_error_budget(
    db: Session,
    window_hours: int = 24,
) -> ErrorBudgetStatus:
    """Compute error budget consumption over a rolling window."""
    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)

    # Pipeline runs
    runs_total = (
        db.query(func.count(PipelineRun.id))
        .filter(PipelineRun.started_at >= cutoff)
        .scalar()
    ) or 0

    runs_failed = (
        db.query(func.count(PipelineRun.id))
        .filter(PipelineRun.started_at >= cutoff, PipelineRun.status == "failed")
        .scalar()
    ) or 0

    pipeline_rate = runs_failed / runs_total if runs_total > 0 else 0.0
    pipeline_remaining = PIPELINE_FAILURE_BUDGET - pipeline_rate

    # Delivery
    delivery_total = (
        db.query(func.count(Alert.id))
        .filter(Alert.created_at >= cutoff, Alert.delivery_status.isnot(None))
        .scalar()
    ) or 0

    delivery_failed = (
        db.query(func.count(Alert.id))
        .filter(Alert.created_at >= cutoff, Alert.delivery_status == "failed")
        .scalar()
    ) or 0

    delivery_rate = delivery_failed / delivery_total if delivery_total > 0 else 0.0
    delivery_remaining = DELIVERY_FAILURE_BUDGET - delivery_rate

    # Extraction confidence
    avg_conf = (
        db.query(func.avg(BillTextExtraction.overall_extraction_confidence))
        .scalar()
    )
    conf_below = avg_conf is not None and avg_conf < MIN_EXTRACTION_CONFIDENCE

    return ErrorBudgetStatus(
        window_hours=window_hours,
        pipeline_runs_total=runs_total,
        pipeline_runs_failed=runs_failed,
        pipeline_failure_rate=pipeline_rate,
        pipeline_budget_remaining=pipeline_remaining,
        delivery_attempts_total=delivery_total,
        delivery_failures=delivery_failed,
        delivery_failure_rate=delivery_rate,
        delivery_budget_remaining=delivery_remaining,
        avg_extraction_confidence=float(avg_conf) if avg_conf is not None else None,
        extraction_below_target=conf_below,
    )


def get_system_health(db: Session) -> SystemHealthReport:
    """Build a comprehensive health report."""
    budget = compute_error_budget(db)

    # Last successful run
    last_run = (
        db.query(PipelineRun)
        .filter(PipelineRun.status == "completed")
        .order_by(PipelineRun.finished_at.desc())
        .first()
    )

    hours_since = None
    if last_run and last_run.finished_at:
        delta = datetime.now(UTC) - last_run.finished_at
        hours_since = delta.total_seconds() / 3600.0

    # Pending and failed alerts
    pending = (
        db.query(func.count(Alert.id))
        .filter(Alert.delivery_status == "pending")
        .scalar()
    ) or 0

    failed = (
        db.query(func.count(Alert.id))
        .filter(Alert.delivery_status == "failed")
        .scalar()
    ) or 0

    # Overall status
    if not budget.healthy:
        status = "unhealthy"
    elif hours_since is not None and hours_since > 2.0:
        status = "degraded"
    elif failed > 0:
        status = "degraded"
    else:
        status = "healthy"

    return SystemHealthReport(
        status=status,
        last_successful_run=last_run.finished_at if last_run else None,
        hours_since_last_run=hours_since,
        pending_alerts=pending,
        failed_alerts=failed,
        error_budget=budget,
    )
