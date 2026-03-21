"""Regression tests for alert routing scenarios.

Covers: no-alert (below threshold), immediate-alert (high score),
digest-only (mid-range score), and suppression edge cases.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pymupdf
import pytest
import yaml

from src.db.models import Alert, Bill, Client, ClientInterestProfile, FileCopy
from src.db.repositories.alerts import AlertRepository
from src.pipeline.orchestrator import Pipeline
from src.scoring.alert_decisioner import AlertDecision, decide_alert, make_suppression_key
from src.scoring.client_scorer import ClientProfile, score_bill_for_client
from src.schemas.scoring import ClientScoreResult, SubjectTagResult
from src.utils.storage import LocalStorage


def _tag_result(
    bill_id: str = "2026-SB00100",
    version_id: str = "2026-SB00100-FC00001",
    subjects: list[str] | None = None,
    change_flags: list[str] | None = None,
) -> SubjectTagResult:
    return SubjectTagResult(
        bill_id=bill_id,
        version_id=version_id,
        subject_tags=subjects or [],
        change_flags=change_flags or [],
        tag_confidence=0.8,
        rationale=[],
    )


class TestNoAlertScenario:
    """Bill scores below client threshold → suppressed_below_threshold."""

    def test_irrelevant_bill_scores_below_threshold(self):
        client = ClientProfile(
            client_id="test_health_client",
            keywords=["hospital", "medical", "nursing"],
            subject_interests=["health_care"],
            alert_threshold=30.0,
        )
        tags = _tag_result(subjects=["transportation"], change_flags=[])
        score = score_bill_for_client(
            client=client,
            tag_result=tags,
            bill_text="This bill concerns highway construction and road maintenance.",
            committee=None,
        )
        assert score.final_score < 30.0
        assert score.should_alert is False
        assert score.alert_disposition == "suppressed_below_threshold"

    def test_no_alert_decision_still_creates_record(self, db_session):
        """Below-threshold alerts should still create an alert record for auditing."""
        client = ClientProfile(
            client_id="test_no_alert",
            keywords=["unrelated_keyword"],
            alert_threshold=50.0,
        )
        tags = _tag_result()
        score = score_bill_for_client(
            client=client,
            tag_result=tags,
            bill_text="Nothing relevant here at all.",
            committee=None,
        )

        alert_repo = AlertRepository(db_session)
        decision = decide_alert(
            score=score,
            client_db_id=1,
            bill_db_id=1,
            alert_repo=alert_repo,
        )
        assert decision.should_create_alert is True
        assert decision.final_disposition == "suppressed_below_threshold"


class TestImmediateAlertScenario:
    """High-scoring bill → immediate alert."""

    def test_high_score_triggers_immediate(self):
        client = ClientProfile(
            client_id="test_transit_client",
            keywords=["transportation", "transit", "highway", "municipal"],
            subject_interests=["transportation", "municipalities"],
            committees_of_interest=["transportation"],
            alert_threshold=30.0,
        )
        tags = _tag_result(
            subjects=["transportation", "municipalities"],
            change_flags=["appropriation_added"],
        )
        score = score_bill_for_client(
            client=client,
            tag_result=tags,
            bill_text=(
                "AN ACT CONCERNING transportation and transit "
                "improvements in municipal areas. The highway "
                "department shall coordinate with local transit authorities."
            ),
            committee="Transportation",
        )
        # Should score high: keywords (40) + subjects (30) + committee (15) = 85
        assert score.final_score >= 60.0
        assert score.alert_disposition == "immediate"
        assert score.urgency in ("high", "critical")

    def test_watched_bill_gets_immediate(self):
        client = ClientProfile(
            client_id="test_watcher",
            keywords=[],
            watched_bills=["2026-SB00100"],
            alert_threshold=15.0,
        )
        tags = _tag_result(bill_id="2026-SB00100")
        score = score_bill_for_client(
            client=client,
            tag_result=tags,
            bill_text="Generic bill text without particular keywords.",
            committee=None,
        )
        assert score.final_score >= 20.0  # 20 from watched bill
        assert score.should_alert is True


class TestDigestOnlyScenario:
    """Mid-range score → digest disposition."""

    def test_moderate_score_routes_to_digest(self):
        # Two-tier thresholds: digest_threshold=25, alert_threshold=60
        # Score of ~35 lands in the digest band (25 <= 35 < 60).
        client = ClientProfile(
            client_id="test_moderate",
            keywords=["insurance", "coverage"],
            subject_interests=["insurance"],
            alert_threshold=60.0,
            digest_threshold=25.0,
        )
        tags = _tag_result(subjects=["insurance"])
        score = score_bill_for_client(
            client=client,
            tag_result=tags,
            bill_text="This act modifies insurance coverage requirements for policyholders.",
            committee=None,
        )
        # Should score: keywords (insurance + coverage = 20) + subject (15) = 35
        assert 25.0 <= score.final_score < 60.0
        assert score.alert_disposition == "digest"
        assert score.should_alert is True


class TestAlertSuppressionScenarios:
    """Suppression rules: duplicate, cooldown."""

    def test_duplicate_suppression_blocks_second_alert(self, db_session):
        """Same client+version pair → suppressed_duplicate."""
        # Set up DB records
        bill = Bill(session_year=2026, bill_id="SB00200", chamber="senate", bill_number_numeric=200, current_title="Test")
        client = Client(client_id="dup_test", display_name="Dup Test")
        db_session.add_all([bill, client])
        db_session.flush()

        alert_repo = AlertRepository(db_session)
        suppression_key = make_suppression_key("dup_test", "2026-SB00200-FC00001")

        # First alert — mark as sent so it's a true duplicate
        alert = alert_repo.create_alert(
            client_db_id=client.id,
            bill_db_id=bill.id,
            canonical_version_id="2026-SB00200-FC00001",
            urgency="high",
            alert_disposition="immediate",
            alert_text="Test alert",
            suppression_key=suppression_key,
        )
        alert.delivery_status = "sent"
        db_session.flush()

        # Second attempt — should be suppressed (already sent)
        score = ClientScoreResult(
            client_id="dup_test",
            bill_id="2026-SB00200",
            version_id="2026-SB00200-FC00001",
            rules_score=70.0,
            final_score=70.0,
            urgency="high",
            should_alert=True,
            alert_disposition="immediate",
            match_reasons=[],
        )
        decision = decide_alert(score, client.id, bill.id, alert_repo)
        assert decision.final_disposition == "suppressed_duplicate"
        assert decision.should_create_alert is False

    def test_cooldown_suppression_within_window(self, db_session):
        """Recent alert for same client+bill → suppressed_cooldown."""
        bill = Bill(session_year=2026, bill_id="SB00201", chamber="senate", bill_number_numeric=201, current_title="Test")
        client = Client(client_id="cool_test", display_name="Cool Test")
        db_session.add_all([bill, client])
        db_session.flush()

        alert_repo = AlertRepository(db_session)

        # Create a recent alert for FC00001
        alert_repo.create_alert(
            client_db_id=client.id,
            bill_db_id=bill.id,
            canonical_version_id="2026-SB00201-FC00001",
            urgency="medium",
            alert_disposition="digest",
            alert_text="Prior alert",
            suppression_key=make_suppression_key("cool_test", "2026-SB00201-FC00001"),
        )
        db_session.flush()

        # New version FC00002 within cooldown window
        score = ClientScoreResult(
            client_id="cool_test",
            bill_id="2026-SB00201",
            version_id="2026-SB00201-FC00002",
            rules_score=50.0,
            final_score=50.0,
            urgency="medium",
            should_alert=True,
            alert_disposition="digest",
            match_reasons=[],
        )
        decision = decide_alert(score, client.id, bill.id, alert_repo)
        assert decision.final_disposition == "suppressed_cooldown"
        assert decision.should_create_alert is True  # still create record for audit


class TestEndToEndAlertRouting:
    """Full pipeline integration: alert reaches correct disposition."""

    def _write_client_yaml(self, tmpdir: str, client_id: str, config: dict) -> Path:
        client_dir = Path(tmpdir) / "clients"
        client_dir.mkdir(exist_ok=True)
        path = client_dir / f"{client_id}.yaml"
        with open(path, "w") as f:
            yaml.dump(config, f)
        return client_dir

    def test_pipeline_creates_immediate_alert(self, db_session):
        """High-matching bill produces an immediate alert record."""
        pdf_text = (
            "Section 1. AN ACT CONCERNING insurance regulation.\n"
            "All insurers shall comply with new coverage requirements. "
            "Each policyholder must receive updated premium notices. "
            "Insurance companies are required to submit annual claims reports."
        )
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text(pymupdf.Point(72, 72), pdf_text, fontsize=11)
        pdf_bytes = doc.tobytes()
        doc.close()

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            pdf_path = storage.store_pdf(2026, "SB00300", 1, pdf_bytes)

            # Write client config that matches insurance bills
            client_dir = self._write_client_yaml(tmpdir, "insurance_client", {
                "client_id": "insurance_client",
                "client_name": "Insurance Client",
                "is_active": True,
                "alert_threshold": 25,
                "digest_threshold": 15,
                "positive_keywords": ["insurance", "insurer", "policyholder", "premium", "coverage", "claims"],
                "subject_priorities": {"insurance": "high", "consumer_protection": "medium"},
            })

            pipeline = Pipeline(
                db_session=db_session,
                storage=storage,
                session_year=2026,
                client_config_dir=client_dir,
            )

            # Create bill + file copy
            from src.db.models import Bill, FileCopy
            bill = Bill(session_year=2026, bill_id="SB00300", chamber="senate", bill_number_numeric=300, current_title="Insurance Regulation Act")
            db_session.add(bill)
            db_session.flush()

            fc = FileCopy(
                bill_id_fk=bill.id,
                session_year=2026,
                file_copy_number=1,
                canonical_version_id="2026-SB00300-FC00001",
                pdf_url="https://example.com/sb300.pdf",
                local_pdf_path=pdf_path,
            )
            db_session.add(fc)
            db_session.flush()

            # Extract and score
            doc_result = pipeline.extract_document(pdf_path, "2026-SB00300-FC00001")
            assert doc_result is not None

            diff = pipeline.diff_version(doc_result, bill.id, 1)
            score_result = pipeline.score_and_summarize(doc_result, diff, bill_title="Insurance Regulation Act")

            client_results = pipeline.score_clients(
                doc=doc_result,
                tag_result=score_result["tags"],
                summary=score_result["summary"],
                bill_db_id=bill.id,
                pdf_url="https://example.com/sb300.pdf",
            )

            assert len(client_results) >= 1
            cr = client_results[0]
            assert cr["score"].final_score >= 25.0
            assert cr["score"].should_alert is True
