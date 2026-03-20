"""Repository for pipeline run audit records."""

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.db.models import PipelineRun

logger = logging.getLogger(__name__)


class PipelineRunRepository:
    def __init__(self, session: Session):
        self.session = session

    def start_run(self, run_type: str) -> PipelineRun:
        """Create a new pipeline run record in 'running' state."""
        run = PipelineRun(
            run_type=run_type,
            status="running",
        )
        self.session.add(run)
        self.session.flush()
        return run

    def complete_run(
        self,
        run_id: int,
        entries_collected: int = 0,
        entries_processed: int = 0,
        entries_failed: int = 0,
        alerts_sent: int = 0,
    ) -> PipelineRun | None:
        """Mark a run as completed with summary counts."""
        run = self.session.get(PipelineRun, run_id)
        if not run:
            return None
        run.status = "completed"
        run.entries_collected = entries_collected
        run.entries_processed = entries_processed
        run.entries_failed = entries_failed
        run.alerts_sent = alerts_sent
        run.finished_at = datetime.now(UTC)
        self.session.flush()
        return run

    def fail_run(self, run_id: int, error_message: str) -> PipelineRun | None:
        """Mark a run as failed with an error message."""
        run = self.session.get(PipelineRun, run_id)
        if not run:
            return None
        run.status = "failed"
        run.error_message = error_message
        run.finished_at = datetime.now(UTC)
        self.session.flush()
        return run

    def get_by_id(self, run_id: int) -> PipelineRun | None:
        return self.session.get(PipelineRun, run_id)

    def get_recent(self, limit: int = 20) -> list[PipelineRun]:
        """Get the most recent pipeline runs."""
        return (
            self.session.query(PipelineRun)
            .order_by(PipelineRun.started_at.desc())
            .limit(limit)
            .all()
        )
