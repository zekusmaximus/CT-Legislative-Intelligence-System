"""Tests for the daily file-copy collector parser."""

from datetime import date
from pathlib import Path

from src.collectors.cga_daily_filecopies import parse_daily_filecopies_page

FIXTURE_PATH = (
    Path(__file__).parent.parent.parent / "data" / "fixtures" / "daily_filecopies_sample.html"
)


def _load_fixture():
    return FIXTURE_PATH.read_text()


class TestDailyFileCopiesParser:
    def test_parses_correct_number_of_rows(self):
        html = _load_fixture()
        source, rows = parse_daily_filecopies_page(html, session_year=2026)
        assert len(rows) == 4

    def test_source_record_created(self):
        html = _load_fixture()
        source, rows = parse_daily_filecopies_page(html, session_year=2026)
        assert source.source_type == "daily_filecopies"
        assert source.session_year == 2026
        assert source.http_status == 200
        assert len(source.content_sha256) == 64

    def test_bill_ids_normalized(self):
        html = _load_fixture()
        _, rows = parse_daily_filecopies_page(html, session_year=2026)
        bill_ids = [r.bill_id for r in rows]
        assert "SB00093" in bill_ids
        assert "HB05140" in bill_ids
        assert "SB00421" in bill_ids
        assert "HB06301" in bill_ids

    def test_file_copy_numbers(self):
        html = _load_fixture()
        _, rows = parse_daily_filecopies_page(html, session_year=2026)
        fc_nums = {r.bill_id: r.file_copy_number for r in rows}
        assert fc_nums["SB00093"] == 44
        assert fc_nums["HB05140"] == 12
        assert fc_nums["SB00421"] == 7
        assert fc_nums["HB06301"] == 3

    def test_titles_extracted(self):
        html = _load_fixture()
        _, rows = parse_daily_filecopies_page(html, session_year=2026)
        sb93 = next(r for r in rows if r.bill_id == "SB00093")
        assert "TRANSPORTATION" in sb93.bill_title

    def test_pdf_urls_absolute(self):
        html = _load_fixture()
        _, rows = parse_daily_filecopies_page(html, session_year=2026)
        for row in rows:
            assert str(row.file_copy_pdf_url).startswith("https://")
            assert ".PDF" in str(row.file_copy_pdf_url).upper()

    def test_listing_date_extracted(self):
        html = _load_fixture()
        _, rows = parse_daily_filecopies_page(html, session_year=2026)
        assert rows[0].listing_date == date(2026, 3, 18)

    def test_display_names_preserved(self):
        html = _load_fixture()
        _, rows = parse_daily_filecopies_page(html, session_year=2026)
        sb93 = next(r for r in rows if r.bill_id == "SB00093")
        assert "S.B." in sb93.bill_number_display or "93" in sb93.bill_number_display

    def test_empty_table_returns_empty_list(self):
        html = "<html><body><h2>No file copies</h2><table></table></body></html>"
        _, rows = parse_daily_filecopies_page(html, session_year=2026)
        assert rows == []

    def test_session_year_propagated(self):
        html = _load_fixture()
        _, rows = parse_daily_filecopies_page(html, session_year=2026)
        for row in rows:
            assert row.session_year == 2026
