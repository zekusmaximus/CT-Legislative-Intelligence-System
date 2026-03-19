"""Tests for the all-file-copies reconciliation collector."""

from datetime import date
from pathlib import Path

from src.collectors.cga_all_filecopies import parse_all_filecopies_page

FIXTURE_PATH = (
    Path(__file__).parent.parent.parent / "data" / "fixtures" / "all_filecopies_sample.html"
)


def _load_fixture():
    return FIXTURE_PATH.read_text()


class TestAllFileCopiesParser:
    def test_parses_correct_number_of_rows(self):
        html = _load_fixture()
        source, rows = parse_all_filecopies_page(html, session_year=2026)
        assert len(rows) == 4

    def test_source_type(self):
        html = _load_fixture()
        source, rows = parse_all_filecopies_page(html, session_year=2026)
        assert source.source_type == "all_filecopies"

    def test_dates_parsed(self):
        html = _load_fixture()
        _, rows = parse_all_filecopies_page(html, session_year=2026)
        dates = {
            f"{r.bill_id}-{r.file_copy_number}": r.listing_date for r in rows
        }
        assert dates["SB00001-2"] == date(2026, 2, 15)
        assert dates["SB00093-31"] == date(2026, 3, 1)
        assert dates["SB00093-44"] == date(2026, 3, 18)

    def test_multiple_versions_same_bill(self):
        html = _load_fixture()
        _, rows = parse_all_filecopies_page(html, session_year=2026)
        sb93_rows = [r for r in rows if r.bill_id == "SB00093"]
        assert len(sb93_rows) == 2
        fc_nums = sorted(r.file_copy_number for r in sb93_rows)
        assert fc_nums == [31, 44]

    def test_bill_ids_normalized(self):
        html = _load_fixture()
        _, rows = parse_all_filecopies_page(html, session_year=2026)
        bill_ids = {r.bill_id for r in rows}
        assert "SB00001" in bill_ids
        assert "SB00093" in bill_ids
        assert "HB05140" in bill_ids
