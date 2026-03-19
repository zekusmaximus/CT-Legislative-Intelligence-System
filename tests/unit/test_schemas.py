"""Tests for Pydantic schema validation."""

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from src.schemas.bills import BillRecord, FileCopyRecord
from src.schemas.diff import BillDiffResult, ChangeEvent, SectionDelta
from src.schemas.extraction import ExtractedDocument, PageText, SectionSpan
from src.schemas.intake import FileCopyListingRow, SourcePageRecord
from src.schemas.scoring import ClientMatchReason, ClientScoreResult, SubjectTagResult
from src.schemas.summary import InternalSummary, TelegramAlertPayload


class TestSourcePageRecord:
    def test_valid(self):
        rec = SourcePageRecord(
            source_type="daily_filecopies",
            source_url="https://cga.ct.gov/asp/cgabillstatus/filecopies.asp",
            fetched_at=datetime(2026, 3, 15, 10, 0),
            content_sha256="a" * 64,
            http_status=200,
            session_year=2026,
        )
        assert rec.source_type == "daily_filecopies"

    def test_invalid_source_type(self):
        with pytest.raises(ValidationError):
            SourcePageRecord(
                source_type="unknown",
                source_url="https://cga.ct.gov/test",
                fetched_at=datetime(2026, 3, 15),
                content_sha256="a" * 64,
                http_status=200,
                session_year=2026,
            )


class TestFileCopyListingRow:
    def test_valid(self):
        row = FileCopyListingRow(
            session_year=2026,
            bill_id="SB00093",
            bill_number_display="S.B. No. 93",
            bill_title="AN ACT CONCERNING TRANSPORTATION",
            file_copy_number=44,
            file_copy_pdf_url="https://cga.ct.gov/2026/FC/pdf/2026SB-00093-R000044-FC.PDF",
            listing_date=date(2026, 3, 15),
            listing_source_url="https://cga.ct.gov/asp/cgabillstatus/filecopies.asp",
        )
        assert row.bill_id == "SB00093"

    def test_invalid_bill_id_format(self):
        with pytest.raises(ValidationError, match="bill_id"):
            FileCopyListingRow(
                session_year=2026,
                bill_id="XB00093",
                bill_number_display="X.B. 93",
                bill_title="Test",
                file_copy_number=1,
                file_copy_pdf_url="https://example.com/test.pdf",
                listing_date=date(2026, 3, 15),
                listing_source_url="https://example.com",
            )

    def test_invalid_file_copy_number(self):
        with pytest.raises(ValidationError):
            FileCopyListingRow(
                session_year=2026,
                bill_id="SB00093",
                bill_number_display="S.B. 93",
                bill_title="Test",
                file_copy_number=0,
                file_copy_pdf_url="https://example.com/test.pdf",
                listing_date=date(2026, 3, 15),
                listing_source_url="https://example.com",
            )


class TestBillRecord:
    def test_valid(self):
        bill = BillRecord(
            session_year=2026,
            bill_id="HB05140",
            chamber="house",
            bill_number_numeric=5140,
            current_title="AN ACT CONCERNING EDUCATION",
            last_seen_at=datetime(2026, 3, 15, 10, 0),
        )
        assert bill.chamber == "house"

    def test_invalid_chamber(self):
        with pytest.raises(ValidationError):
            BillRecord(
                session_year=2026,
                bill_id="HB05140",
                chamber="other",
                bill_number_numeric=5140,
                current_title="Test",
                last_seen_at=datetime(2026, 3, 15),
            )


class TestFileCopyRecord:
    def test_valid(self):
        fc = FileCopyRecord(
            session_year=2026,
            bill_id="SB00093",
            file_copy_number=44,
            canonical_version_id="2026-SB00093-FC00044",
            pdf_url="https://example.com/test.pdf",
            pdf_sha256="b" * 64,
            discovered_at=datetime(2026, 3, 15),
        )
        assert fc.canonical_version_id == "2026-SB00093-FC00044"

    def test_invalid_canonical_id(self):
        with pytest.raises(ValidationError, match="canonical_version_id"):
            FileCopyRecord(
                session_year=2026,
                bill_id="SB00093",
                file_copy_number=44,
                canonical_version_id="bad-format",
                pdf_url="https://example.com/test.pdf",
                pdf_sha256="b" * 64,
                discovered_at=datetime(2026, 3, 15),
            )


class TestExtractionSchemas:
    def test_page_text(self):
        page = PageText(
            page_number=1,
            raw_text="raw",
            cleaned_text="cleaned",
            extraction_method="text",
            extraction_confidence=0.95,
        )
        assert page.extraction_method == "text"

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            PageText(
                page_number=1,
                raw_text="raw",
                cleaned_text="cleaned",
                extraction_method="text",
                extraction_confidence=1.5,
            )

    def test_section_span(self):
        section = SectionSpan(
            section_id="sec_1",
            heading="Section 1",
            start_page=1,
            end_page=2,
            start_char=0,
            end_char=500,
            text="Section text here.",
        )
        assert section.section_id == "sec_1"

    def test_extracted_document(self):
        doc = ExtractedDocument(
            canonical_version_id="2026-SB00093-FC00044",
            pages=[],
            full_raw_text="raw text",
            full_cleaned_text="cleaned text",
            sections=[],
            overall_extraction_confidence=0.9,
        )
        assert doc.overall_extraction_confidence == 0.9


class TestDiffSchemas:
    def test_section_delta(self):
        delta = SectionDelta(
            section_id="sec_1",
            delta_type="modified",
            new_heading="Section 1",
            similarity_score=0.85,
        )
        assert delta.delta_type == "modified"

    def test_change_event(self):
        event = ChangeEvent(
            change_flag="effective_date_changed",
            old_text_summary="October 1, 2026",
            new_text_summary="July 1, 2026",
            practical_effect="Earlier implementation deadline.",
            confidence=0.9,
        )
        assert event.change_flag == "effective_date_changed"

    def test_bill_diff_result(self):
        diff = BillDiffResult(
            bill_id="SB00093",
            current_version_id="2026-SB00093-FC00044",
            compared_against="none",
            sections_added=0,
            sections_removed=0,
            sections_modified=0,
            section_deltas=[],
            change_events=[],
        )
        assert diff.compared_against == "none"


class TestScoringSchemas:
    def test_subject_tag_result(self):
        result = SubjectTagResult(
            bill_id="SB00093",
            version_id="2026-SB00093-FC00044",
            subject_tags=["transportation", "municipalities"],
            change_flags=["mandate_added"],
            tag_confidence=0.86,
            rationale=["Creates duties for municipal transit operations."],
        )
        assert len(result.subject_tags) == 2

    def test_client_score_result(self):
        result = ClientScoreResult(
            client_id="client_via",
            bill_id="SB00093",
            version_id="2026-SB00093-FC00044",
            rules_score=72.0,
            final_score=68.5,
            urgency="high",
            should_alert=True,
            alert_disposition="immediate",
            match_reasons=[
                ClientMatchReason(
                    reason_code="keyword_match",
                    reason_text="Title contains 'transit district'",
                    weight=20.0,
                )
            ],
        )
        assert result.urgency == "high"

    def test_invalid_urgency(self):
        with pytest.raises(ValidationError):
            ClientScoreResult(
                client_id="test",
                bill_id="SB00001",
                version_id="2026-SB00001-FC00001",
                rules_score=50,
                final_score=50,
                urgency="extreme",
                should_alert=True,
                alert_disposition="immediate",
                match_reasons=[],
            )


class TestSummarySchemas:
    def test_internal_summary(self):
        summary = InternalSummary(
            bill_id="SB00093",
            version_id="2026-SB00093-FC00044",
            one_sentence_summary="This bill modifies transportation oversight.",
            deep_summary="Detailed analysis here.",
            key_sections_to_review=["Sec. 2", "Sec. 4"],
            practical_takeaways=["Expands agency authority."],
            confidence=0.84,
        )
        assert len(summary.key_sections_to_review) == 2

    def test_telegram_alert_payload(self):
        payload = TelegramAlertPayload(
            client_id="client_via",
            bill_id="SB00093",
            version_id="2026-SB00093-FC00044",
            urgency="high",
            alert_text="SB 93 | File 44 | HIGH",
            file_copy_url="https://example.com/fc.pdf",
            suppression_key="client_via:SB00093:2026-SB00093-FC00044",
        )
        assert payload.urgency == "high"
