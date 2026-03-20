"""FastAPI application — operational API surface for Phase 5+6."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config.settings import Settings, get_settings
from src.db.models import (
    Alert,
    Bill,
    BillDiff,
    BillSection,
    BillSummary,
    BillTextExtraction,
    ClientBillScore,
    FileCopy,
    PipelineRun,
)
from src.db.session import create_all_tables, get_session_factory

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CT CGA File Copy Intelligence Agent",
    version="0.6.0",
    description="Legislative monitoring and alerting system for CT General Assembly file copies.",
)

# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------

_session_factory = None


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        settings = get_settings()
        _session_factory = get_session_factory(settings.database_url)
    return _session_factory


def get_db() -> Session:
    """Yield a database session, closing it after the request."""
    factory = _get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_current_settings() -> Settings:
    return get_settings()


DB = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_current_settings)]


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    database: str
    timestamp: str


class JobResponse(BaseModel):
    run_id: int
    status: str
    message: str


class VersionResponse(BaseModel):
    canonical_version_id: str
    bill_id: str
    session_year: int
    file_copy_number: int
    pdf_url: str
    page_count: int | None
    extraction_confidence: float | None
    sections_count: int
    has_diff: bool
    has_summary: bool
    summary_one_sentence: str | None
    scores_count: int


class AlertResponse(BaseModel):
    id: int
    client_id: str
    bill_id: str
    canonical_version_id: str
    urgency: str
    alert_disposition: str
    delivery_status: str
    delivery_attempts: int
    created_at: str
    sent_at: str | None


class PipelineRunResponse(BaseModel):
    id: int
    run_type: str
    status: str
    entries_collected: int
    entries_processed: int
    entries_failed: int
    alerts_sent: int
    error_message: str | None
    started_at: str
    finished_at: str | None


# ---------------------------------------------------------------------------
# GET /health — enhanced with DB connectivity check
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
def health_check(db: DB):
    db_status = "ok"
    try:
        db.execute(
            __import__("sqlalchemy").text("SELECT 1")
        )
    except Exception:
        db_status = "unreachable"

    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        database=db_status,
        timestamp=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# POST /jobs/collect/daily — trigger daily collection
# ---------------------------------------------------------------------------


@app.post("/jobs/collect/daily", response_model=JobResponse)
def trigger_daily_collection(db: DB, settings: SettingsDep):
    from src.alerts.telegram_sender import TelegramSender
    from src.pipeline.orchestrator import Pipeline
    from src.utils.storage import LocalStorage

    storage = LocalStorage(settings.storage_local_dir)

    telegram_sender = None
    if settings.telegram_available and settings.telegram_alerts_enabled:
        telegram_sender = TelegramSender(
            bot_token=settings.telegram_bot_token,
            default_chat_id=settings.telegram_chat_id,
        )

    pipeline = Pipeline(
        db_session=db,
        storage=storage,
        session_year=settings.session_year,
        telegram_sender=telegram_sender,
    )

    try:
        results = pipeline.run_daily()
        return JobResponse(
            run_id=_get_latest_run_id(db),
            status="completed",
            message=f"Processed {len(results)} entries",
        )
    except Exception as e:
        logger.exception("Daily collection failed")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# POST /jobs/process/{canonical_version_id} — process a single version
# ---------------------------------------------------------------------------


@app.post("/jobs/process/{canonical_version_id}", response_model=JobResponse)
def trigger_process_version(canonical_version_id: str, db: DB, settings: SettingsDep):
    from src.alerts.telegram_sender import TelegramSender
    from src.pipeline.orchestrator import Pipeline
    from src.utils.storage import LocalStorage

    # Validate the version exists
    fc = db.query(FileCopy).filter_by(canonical_version_id=canonical_version_id).first()
    if not fc:
        raise HTTPException(status_code=404, detail=f"Version {canonical_version_id} not found")

    storage = LocalStorage(settings.storage_local_dir)

    telegram_sender = None
    if settings.telegram_available and settings.telegram_alerts_enabled:
        telegram_sender = TelegramSender(
            bot_token=settings.telegram_bot_token,
            default_chat_id=settings.telegram_chat_id,
        )

    pipeline = Pipeline(
        db_session=db,
        storage=storage,
        session_year=settings.session_year,
        telegram_sender=telegram_sender,
    )

    try:
        result = pipeline.process_single_version(canonical_version_id)
        return JobResponse(
            run_id=_get_latest_run_id(db),
            status="completed" if result else "no_output",
            message="Processed successfully" if result else "Processing produced no output",
        )
    except Exception as e:
        logger.exception("Processing version %s failed", canonical_version_id)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# GET /versions/{canonical_version_id} — inspect a processed version
# ---------------------------------------------------------------------------


@app.get("/versions/{canonical_version_id}", response_model=VersionResponse)
def get_version(canonical_version_id: str, db: DB):
    fc = db.query(FileCopy).filter_by(canonical_version_id=canonical_version_id).first()
    if not fc:
        raise HTTPException(status_code=404, detail="Version not found")

    bill = db.get(Bill, fc.bill_id_fk)

    extraction = (
        db.query(BillTextExtraction)
        .filter_by(canonical_version_id=canonical_version_id)
        .first()
    )

    sections_count = (
        db.query(BillSection)
        .filter_by(canonical_version_id=canonical_version_id)
        .count()
    )

    has_diff = (
        db.query(BillDiff)
        .filter_by(current_version_id=canonical_version_id)
        .first()
        is not None
    )

    summary = (
        db.query(BillSummary)
        .filter_by(canonical_version_id=canonical_version_id)
        .first()
    )

    scores_count = (
        db.query(ClientBillScore)
        .filter_by(canonical_version_id=canonical_version_id)
        .count()
    )

    return VersionResponse(
        canonical_version_id=fc.canonical_version_id,
        bill_id=bill.bill_id if bill else "UNKNOWN",
        session_year=fc.session_year,
        file_copy_number=fc.file_copy_number,
        pdf_url=fc.pdf_url,
        page_count=fc.page_count,
        extraction_confidence=extraction.overall_extraction_confidence if extraction else None,
        sections_count=sections_count,
        has_diff=has_diff,
        has_summary=summary is not None,
        summary_one_sentence=summary.one_sentence_summary if summary else None,
        scores_count=scores_count,
    )


# ---------------------------------------------------------------------------
# GET /alerts — list alerts with optional filters
# ---------------------------------------------------------------------------


@app.get("/alerts", response_model=list[AlertResponse])
def list_alerts(
    db: DB,
    delivery_status: str | None = Query(None, description="Filter by delivery status"),
    urgency: str | None = Query(None, description="Filter by urgency level"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    from src.db.models import Client

    query = db.query(Alert, Client.client_id, Bill.bill_id).join(
        Client, Alert.client_id_fk == Client.id
    ).join(
        Bill, Alert.bill_id_fk == Bill.id
    )

    if delivery_status:
        query = query.filter(Alert.delivery_status == delivery_status)
    if urgency:
        query = query.filter(Alert.urgency == urgency)

    rows = (
        query.order_by(Alert.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        AlertResponse(
            id=alert.id,
            client_id=client_id,
            bill_id=bill_id,
            canonical_version_id=alert.canonical_version_id,
            urgency=alert.urgency,
            alert_disposition=alert.alert_disposition,
            delivery_status=alert.delivery_status or "pending",
            delivery_attempts=alert.delivery_attempts or 0,
            created_at=alert.created_at.isoformat() if alert.created_at else "",
            sent_at=alert.sent_at.isoformat() if alert.sent_at else None,
        )
        for alert, client_id, bill_id in rows
    ]


# ---------------------------------------------------------------------------
# GET /runs — list recent pipeline runs
# ---------------------------------------------------------------------------


@app.get("/runs", response_model=list[PipelineRunResponse])
def list_runs(
    db: DB,
    limit: int = Query(20, ge=1, le=100, description="Max results"),
):
    runs = (
        db.query(PipelineRun)
        .order_by(PipelineRun.started_at.desc())
        .limit(limit)
        .all()
    )

    return [
        PipelineRunResponse(
            id=r.id,
            run_type=r.run_type,
            status=r.status,
            entries_collected=r.entries_collected or 0,
            entries_processed=r.entries_processed or 0,
            entries_failed=r.entries_failed or 0,
            alerts_sent=r.alerts_sent or 0,
            error_message=r.error_message,
            started_at=r.started_at.isoformat() if r.started_at else "",
            finished_at=r.finished_at.isoformat() if r.finished_at else None,
        )
        for r in runs
    ]


# ---------------------------------------------------------------------------
# GET /monitoring/health — system health report
# ---------------------------------------------------------------------------


class ErrorBudgetResponse(BaseModel):
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
    healthy: bool


class SystemHealthResponse(BaseModel):
    status: str
    last_successful_run: str | None
    hours_since_last_run: float | None
    pending_alerts: int
    failed_alerts: int
    error_budget: ErrorBudgetResponse


@app.get("/monitoring/health", response_model=SystemHealthResponse)
def system_health(db: DB):
    from src.monitoring import get_system_health

    report = get_system_health(db)
    return SystemHealthResponse(
        status=report.status,
        last_successful_run=report.last_successful_run.isoformat() if report.last_successful_run else None,
        hours_since_last_run=round(report.hours_since_last_run, 2) if report.hours_since_last_run is not None else None,
        pending_alerts=report.pending_alerts,
        failed_alerts=report.failed_alerts,
        error_budget=ErrorBudgetResponse(
            window_hours=report.error_budget.window_hours,
            pipeline_runs_total=report.error_budget.pipeline_runs_total,
            pipeline_runs_failed=report.error_budget.pipeline_runs_failed,
            pipeline_failure_rate=round(report.error_budget.pipeline_failure_rate, 4),
            pipeline_budget_remaining=round(report.error_budget.pipeline_budget_remaining, 4),
            delivery_attempts_total=report.error_budget.delivery_attempts_total,
            delivery_failures=report.error_budget.delivery_failures,
            delivery_failure_rate=round(report.error_budget.delivery_failure_rate, 4),
            delivery_budget_remaining=round(report.error_budget.delivery_budget_remaining, 4),
            avg_extraction_confidence=round(report.error_budget.avg_extraction_confidence, 4) if report.error_budget.avg_extraction_confidence is not None else None,
            extraction_below_target=report.error_budget.extraction_below_target,
            healthy=report.error_budget.healthy,
        ),
    )


# ---------------------------------------------------------------------------
# GET /review/version/{canonical_version_id} — detailed review view
# ---------------------------------------------------------------------------


class ReviewVersionResponse(BaseModel):
    canonical_version_id: str
    bill_id: str
    bill_title: str
    session_year: int
    file_copy_number: int
    extraction_confidence: float | None
    sections: list[dict]
    diff_summary: dict | None
    change_events: list[dict]
    subject_tags: list[str]
    summary: dict | None
    client_scores: list[dict]
    alerts: list[dict]


@app.get("/review/version/{canonical_version_id}", response_model=ReviewVersionResponse)
def review_version(canonical_version_id: str, db: DB):
    """Detailed review of a processed version — all artifacts in one call."""
    from src.db.models import BillChangeEvent, BillSubjectTag, Client, ClientBillScore

    fc = db.query(FileCopy).filter_by(canonical_version_id=canonical_version_id).first()
    if not fc:
        raise HTTPException(status_code=404, detail="Version not found")

    bill = db.get(Bill, fc.bill_id_fk)

    # Extraction
    extraction = (
        db.query(BillTextExtraction)
        .filter_by(canonical_version_id=canonical_version_id)
        .first()
    )

    # Sections
    sections = (
        db.query(BillSection)
        .filter_by(canonical_version_id=canonical_version_id)
        .order_by(BillSection.start_char)
        .all()
    )
    sections_data = [
        {"section_id": s.section_id, "heading": s.heading, "start_page": s.start_page, "end_page": s.end_page}
        for s in sections
    ]

    # Diff
    diff = (
        db.query(BillDiff)
        .filter_by(current_version_id=canonical_version_id)
        .first()
    )
    diff_data = None
    change_events_data = []
    if diff:
        diff_data = {
            "sections_added": diff.sections_added,
            "sections_removed": diff.sections_removed,
            "sections_modified": diff.sections_modified,
            "compared_against": diff.compared_against,
            "prior_version_id": diff.prior_version_id,
        }
        events = (
            db.query(BillChangeEvent)
            .filter_by(bill_diff_id=diff.id)
            .all()
        )
        change_events_data = [
            {
                "change_flag": e.change_flag,
                "section_id": e.section_id,
                "practical_effect": e.practical_effect,
                "confidence": e.confidence,
            }
            for e in events
        ]

    # Subject tags
    tags = (
        db.query(BillSubjectTag)
        .filter_by(canonical_version_id=canonical_version_id)
        .all()
    )
    tag_names = [t.subject_tag for t in tags]

    # Summary
    summary = (
        db.query(BillSummary)
        .filter_by(canonical_version_id=canonical_version_id)
        .first()
    )
    summary_data = None
    if summary:
        key_sections = summary.key_sections_json
        if isinstance(key_sections, str):
            key_sections = json.loads(key_sections)
        takeaways = summary.practical_takeaways_json
        if isinstance(takeaways, str):
            takeaways = json.loads(takeaways)
        summary_data = {
            "one_sentence": summary.one_sentence_summary,
            "deep_summary": summary.deep_summary,
            "key_sections": key_sections,
            "practical_takeaways": takeaways,
            "confidence": summary.confidence,
        }

    # Scores
    scores = (
        db.query(ClientBillScore, Client.client_id)
        .join(Client, ClientBillScore.client_id_fk == Client.id)
        .filter(ClientBillScore.canonical_version_id == canonical_version_id)
        .all()
    )
    scores_data = [
        {
            "client_id": cid,
            "final_score": s.final_score,
            "urgency": s.urgency,
            "should_alert": s.should_alert,
            "alert_disposition": s.alert_disposition,
        }
        for s, cid in scores
    ]

    # Alerts
    alerts = (
        db.query(Alert)
        .filter_by(canonical_version_id=canonical_version_id)
        .all()
    )
    alerts_data = [
        {
            "id": a.id,
            "urgency": a.urgency,
            "disposition": a.alert_disposition,
            "delivery_status": a.delivery_status or "pending",
            "delivery_attempts": a.delivery_attempts or 0,
        }
        for a in alerts
    ]

    return ReviewVersionResponse(
        canonical_version_id=canonical_version_id,
        bill_id=bill.bill_id if bill else "UNKNOWN",
        bill_title=bill.current_title if bill else "",
        session_year=fc.session_year,
        file_copy_number=fc.file_copy_number,
        extraction_confidence=extraction.overall_extraction_confidence if extraction else None,
        sections=sections_data,
        diff_summary=diff_data,
        change_events=change_events_data,
        subject_tags=tag_names,
        summary=summary_data,
        client_scores=scores_data,
        alerts=alerts_data,
    )


# ---------------------------------------------------------------------------
# POST /feedback — capture operator feedback on alert decisions
# ---------------------------------------------------------------------------


class FeedbackRequest(BaseModel):
    client_id: str
    bill_id: str
    canonical_version_id: str
    label: str  # "relevant" or "not_relevant"
    notes: str = ""


class FeedbackResponse(BaseModel):
    id: int
    status: str


@app.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(body: FeedbackRequest, db: DB):
    """Capture operator feedback for future scoring calibration."""
    from src.db.models import Client, FeedbackLabel

    client = db.query(Client).filter_by(client_id=body.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client {body.client_id} not found")

    bill = db.query(Bill).filter_by(bill_id=body.bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail=f"Bill {body.bill_id} not found")

    if body.label not in ("relevant", "not_relevant"):
        raise HTTPException(status_code=400, detail="Label must be 'relevant' or 'not_relevant'")

    feedback = FeedbackLabel(
        client_id_fk=client.id,
        bill_id_fk=bill.id,
        canonical_version_id=body.canonical_version_id,
        label=body.label,
        notes=body.notes,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    return FeedbackResponse(id=feedback.id, status="saved")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_latest_run_id(db: Session) -> int:
    """Get the most recent pipeline run ID."""
    run = (
        db.query(PipelineRun)
        .order_by(PipelineRun.started_at.desc())
        .first()
    )
    return run.id if run else 0
