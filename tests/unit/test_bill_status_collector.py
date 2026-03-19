"""Tests for the bill status page parser."""

from pathlib import Path

from src.collectors.cga_bill_status import parse_bill_status_page

FIXTURE_PATH = Path(__file__).parent.parent.parent / "data" / "fixtures" / "bill_status_sample.html"


def _load_fixture():
    return FIXTURE_PATH.read_text()


class TestBillStatusParser:
    def test_extracts_title(self):
        result = parse_bill_status_page(_load_fixture())
        assert "TRANSPORTATION" in result["title"].upper()

    def test_extracts_committee(self):
        result = parse_bill_status_page(_load_fixture())
        assert "Transportation" in result["committee"]

    def test_extracts_introduced_by(self):
        result = parse_bill_status_page(_load_fixture())
        assert "Smith" in result["introduced_by"]

    def test_extracts_statement_of_purpose(self):
        result = parse_bill_status_page(_load_fixture())
        assert "transportation network" in result["statement_of_purpose"].lower()

    def test_extracts_history(self):
        result = parse_bill_status_page(_load_fixture())
        assert len(result["history"]) == 3
        assert "Referred" in result["history"][0]["action"]

    def test_empty_page(self):
        result = parse_bill_status_page("<html><body></body></html>")
        assert result["title"] == ""
        assert result["committee"] == ""
        assert result["history"] == []
