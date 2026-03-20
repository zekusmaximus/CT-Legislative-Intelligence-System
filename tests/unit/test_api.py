"""Unit tests for the FastAPI operational API."""

import os
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("APP_ENV", "development")

from datetime import datetime, UTC

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from apps.api.main import app, get_db, get_current_settings
from config.settings import Settings
from src.db.models import (
    Alert,
    Base,
    Bill,
    BillDiff,
    BillSection,
    BillSummary,
    BillTextExtraction,
    Client,
    ClientBillScore,
    FileCopy,
    PipelineRun,
)


@pytest.fixture
def db_url(tmp_path):
    db_path = tmp_path / "test.db"
    return f"sqlite:///{db_path}"


@pytest.fixture
def db_engine(db_url):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session(db_engine):
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = factory()
    yield session
    session.close()


@pytest.fixture
def test_settings(db_url):
    return Settings(
        database_url=db_url,
        app_env="development",
    )


@pytest.fixture
def client(db_session, test_settings):
    """Create a FastAPI test client with dependency overrides."""

    def _override_db():
        yield db_session

    def _override_settings():
        return test_settings

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_settings] = _override_settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_bill_and_fc(db_session: Session) -> tuple:
    """Helper: create a Bill + FileCopy pair for testing."""
    bill = Bill(
        session_year=2026,
        bill_id="SB00001",
        chamber="senate",
        bill_number_numeric=1,
        current_title="Test Bill",
    )
    db_session.add(bill)
    db_session.flush()

    fc = FileCopy(
        bill_id_fk=bill.id,
        session_year=2026,
        file_copy_number=1,
        canonical_version_id="2026-SB00001-FC00001",
        pdf_url="https://example.com/test.pdf",
    )
    db_session.add(fc)
    db_session.flush()
    return bill, fc


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["database"] == "ok"
        assert "timestamp" in data


class TestVersionEndpoint:
    def test_version_not_found(self, client):
        resp = client.get("/versions/2026-NOEXIST-FC00001")
        assert resp.status_code == 404

    def test_version_found_minimal(self, client, db_session):
        bill, fc = _seed_bill_and_fc(db_session)
        db_session.commit()

        resp = client.get(f"/versions/{fc.canonical_version_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["canonical_version_id"] == "2026-SB00001-FC00001"
        assert data["bill_id"] == "SB00001"
        assert data["session_year"] == 2026
        assert data["file_copy_number"] == 1
        assert data["extraction_confidence"] is None
        assert data["sections_count"] == 0
        assert data["has_diff"] is False
        assert data["has_summary"] is False

    def test_version_with_extraction_and_summary(self, client, db_session):
        bill, fc = _seed_bill_and_fc(db_session)

        extraction = BillTextExtraction(
            canonical_version_id=fc.canonical_version_id,
            full_raw_text="raw text",
            full_cleaned_text="cleaned text",
            overall_extraction_confidence=0.92,
        )
        db_session.add(extraction)

        section = BillSection(
            canonical_version_id=fc.canonical_version_id,
            section_id="sec_1",
            heading="Section 1",
            start_page=1,
            end_page=1,
            start_char=0,
            end_char=100,
            text="Section text",
        )
        db_session.add(section)

        diff = BillDiff(
            bill_id_fk=bill.id,
            current_version_id=fc.canonical_version_id,
            compared_against="none",
            sections_added=1,
            sections_removed=0,
            sections_modified=0,
        )
        db_session.add(diff)

        summary = BillSummary(
            canonical_version_id=fc.canonical_version_id,
            bill_id="SB00001",
            one_sentence_summary="A test bill summary.",
            deep_summary="A deeper summary.",
            confidence=0.85,
        )
        db_session.add(summary)
        db_session.commit()

        resp = client.get(f"/versions/{fc.canonical_version_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["extraction_confidence"] == pytest.approx(0.92)
        assert data["sections_count"] == 1
        assert data["has_diff"] is True
        assert data["has_summary"] is True
        assert data["summary_one_sentence"] == "A test bill summary."


class TestAlertsEndpoint:
    def test_alerts_empty(self, client):
        resp = client.get("/alerts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_alerts_with_data(self, client, db_session):
        bill, fc = _seed_bill_and_fc(db_session)

        client_row = Client(
            client_id="test_client",
            display_name="Test Client",
            is_active=True,
        )
        db_session.add(client_row)
        db_session.flush()

        alert = Alert(
            client_id_fk=client_row.id,
            bill_id_fk=bill.id,
            canonical_version_id=fc.canonical_version_id,
            urgency="high",
            alert_disposition="immediate",
            alert_text="Test alert text",
            suppression_key="test_key_1",
            delivery_status="sent",
            delivery_attempts=1,
        )
        db_session.add(alert)
        db_session.commit()

        resp = client.get("/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["client_id"] == "test_client"
        assert data[0]["urgency"] == "high"
        assert data[0]["delivery_status"] == "sent"

    def test_alerts_filter_by_urgency(self, client, db_session):
        bill, fc = _seed_bill_and_fc(db_session)

        client_row = Client(
            client_id="filter_client",
            display_name="Filter Client",
        )
        db_session.add(client_row)
        db_session.flush()

        for urgency in ["high", "low", "high"]:
            db_session.add(Alert(
                client_id_fk=client_row.id,
                bill_id_fk=bill.id,
                canonical_version_id=fc.canonical_version_id,
                urgency=urgency,
                alert_disposition="immediate",
                alert_text=f"Alert {urgency}",
                suppression_key=f"key_{urgency}_{id(urgency)}",
            ))
        db_session.commit()

        resp = client.get("/alerts?urgency=high")
        assert resp.status_code == 200
        data = resp.json()
        assert all(a["urgency"] == "high" for a in data)

    def test_alerts_filter_by_delivery_status(self, client, db_session):
        bill, fc = _seed_bill_and_fc(db_session)
        client_row = Client(client_id="ds_client", display_name="DS")
        db_session.add(client_row)
        db_session.flush()

        db_session.add(Alert(
            client_id_fk=client_row.id,
            bill_id_fk=bill.id,
            canonical_version_id=fc.canonical_version_id,
            urgency="medium",
            alert_disposition="immediate",
            alert_text="pending alert",
            suppression_key="pend_1",
            delivery_status="pending",
        ))
        db_session.add(Alert(
            client_id_fk=client_row.id,
            bill_id_fk=bill.id,
            canonical_version_id=fc.canonical_version_id,
            urgency="medium",
            alert_disposition="immediate",
            alert_text="sent alert",
            suppression_key="sent_1",
            delivery_status="sent",
        ))
        db_session.commit()

        resp = client.get("/alerts?delivery_status=pending")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["delivery_status"] == "pending"


class TestRunsEndpoint:
    def test_runs_empty(self, client):
        resp = client.get("/runs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_runs_with_data(self, client, db_session):
        run = PipelineRun(
            run_type="daily",
            status="completed",
            entries_collected=10,
            entries_processed=8,
            entries_failed=2,
            alerts_sent=3,
        )
        db_session.add(run)
        db_session.commit()

        resp = client.get("/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["run_type"] == "daily"
        assert data[0]["status"] == "completed"
        assert data[0]["entries_collected"] == 10
        assert data[0]["entries_processed"] == 8
        assert data[0]["entries_failed"] == 2
        assert data[0]["alerts_sent"] == 3


class TestProcessVersionEndpoint:
    def test_process_version_not_found(self, client):
        resp = client.post("/jobs/process/2026-NOEXIST-FC00001")
        assert resp.status_code == 404
