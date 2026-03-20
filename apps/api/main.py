"""FastAPI application — operational API surface for Phase 5."""

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
    version="0.5.0",
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
