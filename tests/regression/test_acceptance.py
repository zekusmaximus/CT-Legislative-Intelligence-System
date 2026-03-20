"""Acceptance tests for MVP pilot readiness.

Covers:
- Duplicate suppression correctness
- Taxonomy compliance (no invalid tags/flags can leak)
- Persisted output integrity (round-trip from pipeline to DB)
"""

import tempfile
from pathlib import Path

import pymupdf
import pytest
import yaml

from src.db.models import (
    Alert,
    Bill,
    BillChangeEvent,
    BillDiff,
    BillSection,
    BillSubjectTag,
    BillSummary,
    BillTextExtraction,
    Client,
    FileCopy,
)
from src.db.repositories.alerts import AlertRepository
from src.db.repositories.extractions import ExtractionRepository
from src.db.repositories.sections import SectionRepository
from src.db.repositories.summaries import SummaryRepository
from src.db.repositories.diffs import DiffRepository
from src.db.repositories.subject_tags import SubjectTagRepository
from src.diff.change_classifier import classify_changes
from src.diff.section_differ import diff_documents
from src.metadata.taxonomy import (
    InvalidTaxonomyValueError,
    load_change_flags,
    load_subject_tags,
    validate_change_flags,
    validate_subject_tags,
)
from src.pipeline.orchestrator import Pipeline
from src.schemas.extraction import ExtractedDocument, PageText, SectionSpan
from src.scoring.alert_decisioner import decide_alert, make_suppression_key
from src.scoring.client_scorer import ClientProfile, score_bill_for_client
from src.scoring.subject_tagger import tag_bill_version
from src.schemas.scoring import ClientScoreResult, SubjectTagResult
from src.utils.storage import LocalStorage


# -----------------------------------------------------------------------
# Taxonomy compliance
# -----------------------------------------------------------------------


class TestTaxonomyCompliance:
    """No invalid subject tags or change flags can escape validation."""

    def test_invalid_subject_tag_raises(self):
        with pytest.raises(InvalidTaxonomyValueError):
            validate_subject_tags(["health_care", "nonexistent_subject_xyz"])

    def test_invalid_change_flag_raises(self):
        with pytest.raises(InvalidTaxonomyValueError):
            validate_change_flags(["section_added", "invalid_flag_xyz"])

    def test_all_subject_keywords_are_canonical(self):
        """SUBJECT_KEYWORDS map keys must exactly match taxonomy config."""
        from src.scoring.subject_tagger import SUBJECT_KEYWORDS
        approved = load_subject_tags()
        assert set(SUBJECT_KEYWORDS.keys()) == approved

    def test_tagger_only_emits_approved_tags(self):
        doc = ExtractedDocument(
            canonical_version_id="2026-SB00001-FC00001",
            pages=[PageText(
                page_number=1,
                raw_text="insurance insurer premium coverage policyholder claims",
                cleaned_text="insurance insurer premium coverage policyholder claims",
                extraction_method="text",
                extraction_confidence=0.95,
            )],
            full_raw_text="insurance insurer premium coverage policyholder claims",
            full_cleaned_text="insurance insurer premium coverage policyholder claims",
            sections=[],
            overall_extraction_confidence=0.95,
        )
        result = tag_bill_version(doc)
        approved = load_subject_tags()
        for tag in result.subject_tags:
            assert tag in approved, f"Tag '{tag}' not in approved taxonomy"

    def test_classifier_only_emits_approved_flags(self):
        """classify_changes must never return an unapproved change flag."""
        from src.schemas.diff import BillDiffResult, SectionDelta
        result = BillDiffResult(
            bill_id="2026-SB00001",
            current_version_id="2026-SB00001-FC00002",
            prior_version_id="2026-SB00001-FC00001",
            compared_against="prior_file_copy",
            sections_added=1,
            sections_removed=0,
            sections_modified=0,
            section_deltas=[
                SectionDelta(
                    section_id="sec_1",
                    old_heading=None,
                    new_heading="Section 1",
                    delta_type="added",
                    new_text="There is appropriated the sum of five million dollars from the General Fund. "
                             "Any person who violates this shall be subject to a penalty of ten thousand dollars. "
                             "This act shall take effect July 1, 2026.",
                    similarity_score=0.0,
                ),
            ],
            change_events=[],
        )
        events = classify_changes(result)
        approved = load_change_flags()
        for event in events:
            assert event.change_flag in approved, f"Flag '{event.change_flag}' not in approved taxonomy"


# -----------------------------------------------------------------------
# Duplicate suppression
# -----------------------------------------------------------------------


class TestDuplicateSuppression:
    """Suppression key prevents duplicate alerts for the same client+version."""

    def test_suppression_key_deterministic(self):
        k1 = make_suppression_key("client_a", "2026-SB00001-FC00001")
        k2 = make_suppression_key("client_a", "2026-SB00001-FC00001")
        assert k1 == k2

    def test_different_versions_get_different_keys(self):
        k1 = make_suppression_key("client_a", "2026-SB00001-FC00001")
        k2 = make_suppression_key("client_a", "2026-SB00001-FC00002")
        assert k1 != k2

    def test_different_clients_get_different_keys(self):
        k1 = make_suppression_key("client_a", "2026-SB00001-FC00001")
        k2 = make_suppression_key("client_b", "2026-SB00001-FC00001")
        assert k1 != k2

    def test_full_duplicate_flow(self, db_session):
        """Process the same version twice → second alert is suppressed."""
        bill = Bill(session_year=2026, bill_id="SB00400", chamber="senate", bill_number_numeric=400, current_title="Test")
        client = Client(client_id="dup_flow", display_name="Dup Flow")
        db_session.add_all([bill, client])
        db_session.flush()

        alert_repo = AlertRepository(db_session)

        score = ClientScoreResult(
            client_id="dup_flow",
            bill_id="2026-SB00400",
            version_id="2026-SB00400-FC00001",
            rules_score=75.0,
            final_score=75.0,
            urgency="high",
            should_alert=True,
            alert_disposition="immediate",
            match_reasons=[],
        )

        # First decision
        d1 = decide_alert(score, client.id, bill.id, alert_repo)
        assert d1.final_disposition == "immediate"
        assert d1.should_create_alert is True

        # Create the alert record
        alert_repo.create_alert(
            client_db_id=client.id,
            bill_db_id=bill.id,
            canonical_version_id="2026-SB00400-FC00001",
            urgency="high",
            alert_disposition="immediate",
            alert_text="Test",
            suppression_key=d1.suppression_key,
        )
        db_session.flush()

        # Second decision (same version)
        d2 = decide_alert(score, client.id, bill.id, alert_repo)
        assert d2.final_disposition == "suppressed_duplicate"
        assert d2.should_create_alert is False


# -----------------------------------------------------------------------
# Persisted output integrity
# -----------------------------------------------------------------------


class TestPersistedOutputIntegrity:
    """Pipeline outputs persist correctly and can be queried back."""

    def _make_test_doc(self) -> ExtractedDocument:
        return ExtractedDocument(
            canonical_version_id="2026-SB00500-FC00001",
            pages=[PageText(
                page_number=1,
                raw_text="Section 1. AN ACT CONCERNING health care regulation.\n"
                         "All hospitals shall implement quality reporting requirements.",
                cleaned_text="Section 1. AN ACT CONCERNING health care regulation.\n"
                             "All hospitals shall implement quality reporting requirements.",
                extraction_method="text",
                extraction_confidence=0.95,
            )],
            full_raw_text="Section 1. AN ACT CONCERNING health care regulation.\n"
                          "All hospitals shall implement quality reporting requirements.",
            full_cleaned_text="Section 1. AN ACT CONCERNING health care regulation.\n"
                              "All hospitals shall implement quality reporting requirements.",
            sections=[SectionSpan(
                section_id="sec_1",
                heading="Section 1. AN ACT CONCERNING health care regulation.",
                start_page=1,
                end_page=1,
                start_char=0,
                end_char=100,
                text="Section 1. AN ACT CONCERNING health care regulation.\n"
                     "All hospitals shall implement quality reporting requirements.",
            )],
            overall_extraction_confidence=0.95,
            extraction_warnings=[],
        )

    def test_extraction_persists_and_queries(self, db_session):
        doc = self._make_test_doc()
        repo = ExtractionRepository(db_session)
        repo.save_extraction(doc)
        db_session.flush()

        row = db_session.query(BillTextExtraction).filter_by(
            canonical_version_id="2026-SB00500-FC00001"
        ).first()
        assert row is not None
        assert row.overall_extraction_confidence == pytest.approx(0.95)
        assert "health care" in row.full_cleaned_text

    def test_sections_persist_and_query(self, db_session):
        doc = self._make_test_doc()
        repo = SectionRepository(db_session)
        repo.save_sections(doc)
        db_session.flush()

        rows = db_session.query(BillSection).filter_by(
            canonical_version_id="2026-SB00500-FC00001"
        ).all()
        assert len(rows) == 1
        assert rows[0].section_id == "sec_1"

    def test_diff_persists_and_queries(self, db_session):
        doc = self._make_test_doc()
        diff_result = diff_documents(doc, None)
        diff_result.change_events = classify_changes(diff_result)

        # Need a bill row
        bill = Bill(session_year=2026, bill_id="SB00500", chamber="senate", bill_number_numeric=500, current_title="Test")
        db_session.add(bill)
        db_session.flush()

        repo = DiffRepository(db_session)
        repo.save_diff(diff_result, bill.id)
        db_session.flush()

        row = db_session.query(BillDiff).filter_by(
            current_version_id="2026-SB00500-FC00001"
        ).first()
        assert row is not None
        assert row.sections_added >= 1

        events = db_session.query(BillChangeEvent).filter_by(
            bill_diff_id=row.id
        ).all()
        assert len(events) >= 1  # at least section_added

    def test_subject_tags_persist(self, db_session):
        doc = self._make_test_doc()
        tags = tag_bill_version(doc)
        repo = SubjectTagRepository(db_session)
        repo.save_tags(tags)
        db_session.flush()

        rows = db_session.query(BillSubjectTag).filter_by(
            canonical_version_id="2026-SB00500-FC00001"
        ).all()
        tag_names = {r.subject_tag for r in rows}
        # The doc mentions health care and hospitals → should tag health_care
        assert "health_care" in tag_names

    def test_summary_persists(self, db_session):
        doc = self._make_test_doc()
        diff_result = diff_documents(doc, None)
        from src.scoring.summary_generator import generate_summary
        summary = generate_summary(doc, diff_result, bill_title="Health Care Act")

        repo = SummaryRepository(db_session)
        repo.save_summary(summary)
        db_session.flush()

        row = db_session.query(BillSummary).filter_by(
            canonical_version_id="2026-SB00500-FC00001"
        ).first()
        assert row is not None
        assert "Health Care" in row.one_sentence_summary

    def test_alert_persists_with_delivery_fields(self, db_session):
        bill = Bill(session_year=2026, bill_id="SB00501", chamber="senate", bill_number_numeric=501, current_title="Test")
        client = Client(client_id="persist_test", display_name="Persist Test")
        db_session.add_all([bill, client])
        db_session.flush()

        repo = AlertRepository(db_session)
        alert = repo.create_alert(
            client_db_id=client.id,
            bill_db_id=bill.id,
            canonical_version_id="2026-SB00501-FC00001",
            urgency="high",
            alert_disposition="immediate",
            alert_text="Test alert text",
            suppression_key="test_key_12345",
        )
        db_session.flush()

        row = db_session.query(Alert).get(alert.id)
        assert row is not None
        assert row.urgency == "high"
        assert row.alert_disposition == "immediate"
        assert row.delivery_status == "pending"
        assert row.delivery_attempts == 0
