"""Tests for Phase 6 API endpoints: monitoring, review, feedback."""

import os
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("APP_ENV", "development")

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
    BillSubjectTag,
    BillSummary,
    BillTextExtraction,
    Client,
    ClientBillScore,
    FileCopy,
    PipelineRun,
)


@pytest.fixture
def db_url(tmp_path):
    db_path = tmp_path / "test_phase6.db"
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
    def _override_db():
        yield db_session

    def _override_settings():
        return test_settings

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_settings] = _override_settings
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_db(db_session):
    """Seed the database with test data for review/monitoring endpoints."""
    bill = Bill(session_year=2026, bill_id="SB00900", chamber="senate", bill_number_numeric=900, current_title="Test Bill")
    db_session.add(bill)
    db_session.flush()

    fc = FileCopy(
        bill_id_fk=bill.id,
        session_year=2026,
        file_copy_number=1,
        canonical_version_id="2026-SB00900-FC00001",
        pdf_url="https://example.com/sb900.pdf",
    )
    db_session.add(fc)
    db_session.flush()

    db_session.add(BillTextExtraction(
        canonical_version_id="2026-SB00900-FC00001",
        full_raw_text="Section 1. Test content.",
        full_cleaned_text="Section 1. Test content.",
        overall_extraction_confidence=0.92,
    ))

    db_session.add(BillSection(
        canonical_version_id="2026-SB00900-FC00001",
        section_id="sec_1",
        heading="Section 1",
        start_page=1,
        end_page=1,
        start_char=0,
        end_char=25,
        text="Section 1. Test content.",
    ))

    db_session.add(BillSubjectTag(
        canonical_version_id="2026-SB00900-FC00001",
        subject_tag="health_care",
        tag_confidence=0.8,
    ))

    db_session.add(BillSummary(
        canonical_version_id="2026-SB00900-FC00001",
        bill_id="SB00900",
        one_sentence_summary="Test bill about health care.",
        deep_summary="Detailed summary here.",
        key_sections_json='["Section 1"]',
        practical_takeaways_json='["Review section 1"]',
        confidence=0.85,
    ))

    client_row = Client(client_id="test_client", display_name="Test Client")
    db_session.add(client_row)
    db_session.flush()

    db_session.add(ClientBillScore(
        client_id_fk=client_row.id,
        bill_id_fk=bill.id,
        canonical_version_id="2026-SB00900-FC00001",
        rules_score=65.0,
        final_score=65.0,
        urgency="high",
        should_alert=True,
        alert_disposition="immediate",
        reasons_json='[]',
    ))

    db_session.add(Alert(
        client_id_fk=client_row.id,
        bill_id_fk=bill.id,
        canonical_version_id="2026-SB00900-FC00001",
        urgency="high",
        alert_disposition="immediate",
        alert_text="Test alert",
        suppression_key="test_key_900_001",
        delivery_status="sent",
        delivery_attempts=1,
    ))

    db_session.flush()
    return {"bill": bill, "fc": fc, "client": client_row}


class TestMonitoringEndpoint:
    def test_monitoring_health_returns_ok(self, client):
        resp = client.get("/monitoring/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "error_budget" in data
        assert "healthy" in data["error_budget"]

    def test_monitoring_health_with_runs(self, client, db_session):
        db_session.add(PipelineRun(run_type="daily", status="completed"))
        db_session.flush()

        resp = client.get("/monitoring/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error_budget"]["pipeline_runs_total"] >= 1


class TestReviewEndpoint:
    def test_review_version_returns_full_data(self, client, seeded_db):
        resp = client.get("/review/version/2026-SB00900-FC00001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["canonical_version_id"] == "2026-SB00900-FC00001"
        assert data["bill_id"] == "SB00900"
        assert data["extraction_confidence"] == pytest.approx(0.92)
        assert len(data["sections"]) == 1
        assert "health_care" in data["subject_tags"]
        assert data["summary"] is not None
        assert data["summary"]["one_sentence"] == "Test bill about health care."
        assert len(data["client_scores"]) == 1
        assert len(data["alerts"]) == 1

    def test_review_version_404(self, client):
        resp = client.get("/review/version/nonexistent")
        assert resp.status_code == 404


class TestFeedbackEndpoint:
    def test_submit_feedback(self, client, seeded_db):
        resp = client.post("/feedback", json={
            "client_id": "test_client",
            "bill_id": "SB00900",
            "canonical_version_id": "2026-SB00900-FC00001",
            "label": "relevant",
            "notes": "This is important for our operations.",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "saved"
        assert data["id"] > 0

    def test_submit_feedback_invalid_label(self, client, seeded_db):
        resp = client.post("/feedback", json={
            "client_id": "test_client",
            "bill_id": "SB00900",
            "canonical_version_id": "2026-SB00900-FC00001",
            "label": "maybe",
        })
        assert resp.status_code == 400

    def test_submit_feedback_unknown_client(self, client, seeded_db):
        resp = client.post("/feedback", json={
            "client_id": "nonexistent",
            "bill_id": "SB00900",
            "canonical_version_id": "2026-SB00900-FC00001",
            "label": "relevant",
        })
        assert resp.status_code == 404
