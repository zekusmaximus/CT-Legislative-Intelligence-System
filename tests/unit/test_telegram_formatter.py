"""Tests for the Telegram alert formatter."""

from src.alerts.telegram_formatter import (
    build_alert_payload,
    format_alert_text,
    format_telegram_markdown,
)
from src.schemas.scoring import ClientMatchReason, ClientScoreResult
from src.schemas.summary import InternalSummary


def _make_score() -> ClientScoreResult:
    return ClientScoreResult(
        client_id="client1",
        bill_id="SB00093",
        version_id="2026-SB00093-FC00044",
        rules_score=75.0,
        final_score=75.0,
        urgency="high",
        should_alert=True,
        alert_disposition="immediate",
        match_reasons=[
            ClientMatchReason(
                reason_code="keyword_match",
                reason_text="Keyword 'transportation' found",
                weight=10.0,
            ),
            ClientMatchReason(
                reason_code="subject_match",
                reason_text="Subject 'transportation' matches",
                weight=15.0,
            ),
        ],
    )


def _make_summary() -> InternalSummary:
    return InternalSummary(
        bill_id="SB00093",
        version_id="2026-SB00093-FC00044",
        one_sentence_summary=(
            "AN ACT CONCERNING TRANSPORTATION — updated with 1 section(s) added."
        ),
        deep_summary="Detailed summary text.",
        key_sections_to_review=["Section 1", "Section 4"],
        practical_takeaways=[
            "1 new section added — review for new requirements.",
            "effective_date_change: Contains effective date",
        ],
        confidence=0.85,
    )


PDF_URL = "https://www.cga.ct.gov/2026/FC/pdf/2026SB-00093-R000044-FC.PDF"


BILL_STATUS_URL = "https://www.cga.ct.gov/asp/cgabillstatus/cgabillstatus.asp?selBillType=Bill&which_year=2026&bill_num=SB00093"


class TestTelegramFormatter:
    def test_alert_text_contains_bill_id(self):
        text = format_alert_text(_make_score(), _make_summary())
        assert "SB00093" in text

    def test_alert_text_contains_urgency(self):
        text = format_alert_text(_make_score(), _make_summary())
        assert "ORANGE" in text  # high = ORANGE

    def test_alert_text_contains_score(self):
        text = format_alert_text(_make_score(), _make_summary())
        assert "75" in text

    def test_alert_text_contains_summary(self):
        text = format_alert_text(_make_score(), _make_summary())
        assert "TRANSPORTATION" in text

    def test_alert_text_contains_takeaways(self):
        text = format_alert_text(_make_score(), _make_summary())
        assert "Key points:" in text

    def test_alert_text_contains_reasons(self):
        text = format_alert_text(_make_score(), _make_summary())
        assert "Why this matters:" in text

    def test_alert_text_contains_version(self):
        text = format_alert_text(_make_score(), _make_summary())
        assert "2026-SB00093-FC00044" in text

    def test_alert_text_contains_client_disposition(self):
        text = format_alert_text(_make_score(), _make_summary())
        assert "client1" in text
        assert "immediate" in text

    def test_alert_text_contains_pdf_link(self):
        text = format_alert_text(
            _make_score(), _make_summary(),
            file_copy_pdf_url=PDF_URL,
        )
        assert f"PDF: {PDF_URL}" in text

    def test_alert_text_contains_bill_status_link(self):
        text = format_alert_text(
            _make_score(), _make_summary(),
            bill_status_url=BILL_STATUS_URL,
        )
        assert f"Bill page: {BILL_STATUS_URL}" in text

    def test_build_payload(self):
        payload = build_alert_payload(_make_score(), _make_summary(), PDF_URL)
        assert payload.client_id == "client1"
        assert payload.bill_id == "SB00093"
        assert payload.urgency == "high"
        assert len(payload.suppression_key) == 16
        assert len(payload.alert_text) > 0

    def test_build_payload_includes_links(self):
        payload = build_alert_payload(
            _make_score(), _make_summary(), PDF_URL,
            bill_status_url=BILL_STATUS_URL,
        )
        assert PDF_URL in payload.alert_text
        assert BILL_STATUS_URL in payload.alert_text

    def test_suppression_key_deterministic(self):
        p1 = build_alert_payload(_make_score(), _make_summary(), PDF_URL)
        p2 = build_alert_payload(_make_score(), _make_summary(), PDF_URL)
        assert p1.suppression_key == p2.suppression_key

    def test_telegram_markdown_formatted(self):
        md = format_telegram_markdown(_make_score(), _make_summary(), PDF_URL)
        assert "SB00093" in md
        assert "View PDF" in md
