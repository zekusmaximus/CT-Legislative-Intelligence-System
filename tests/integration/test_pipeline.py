"""End-to-end integration test for the pipeline orchestrator.

Uses fixtures and mock fetcher — no network calls.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pymupdf

from src.db.repositories.bills import BillRepository
from src.db.repositories.file_copies import FileCopyRepository
from src.pipeline.orchestrator import Pipeline
from src.utils.storage import LocalStorage

DAILY_FIXTURE = (
    Path(__file__).parent.parent.parent / "data" / "fixtures" / "daily_filecopies_sample.html"
)


def _create_fake_pdf(text: str = "Section 1. AN ACT CONCERNING testing.") -> bytes:
    """Create a minimal PDF for testing."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(pymupdf.Point(72, 72), text, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_mock_fetcher(daily_html: str, pdf_bytes: bytes):
    """Create a mock fetcher that returns fixture data."""
    fetcher = MagicMock()

    def fetch_html(url):
        return daily_html, 200

    def fetch_pdf(url):
        return pdf_bytes, 200

    fetcher.fetch_html = MagicMock(side_effect=fetch_html)
    fetcher.fetch_pdf = MagicMock(side_effect=fetch_pdf)
    return fetcher


class TestPipelineEndToEnd:
    def test_full_daily_pipeline(self, db_session):
        """Run the full pipeline from HTML fixture through scoring."""
        daily_html = DAILY_FIXTURE.read_text()
        pdf_bytes = _create_fake_pdf(
            "Section 1. This act shall take effect July 1, 2026.\n"
            "The Commissioner of Transportation shall establish "
            "a municipal transit pilot program."
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            fetcher = _make_mock_fetcher(daily_html, pdf_bytes)

            pipeline = Pipeline(
                db_session=db_session,
                storage=storage,
                fetcher=fetcher,
                session_year=2026,
            )

            results = pipeline.run_daily()

            # Should process all 4 file copies from fixture
            assert len(results) == 4

            # Each result should have tags, summary, diff
            for r in results:
                assert "tags" in r
                assert "summary" in r
                assert "diff" in r
                assert "bill_id" in r
                assert "canonical_id" in r

            # Verify DB persistence
            bill_repo = BillRepository(db_session)
            sb93 = bill_repo.get_by_bill_id(2026, "SB00093")
            assert sb93 is not None
            assert "TRANSPORTATION" in sb93.current_title

            fc_repo = FileCopyRepository(db_session)
            fc = fc_repo.get_by_canonical_id("2026-SB00093-FC00044")
            assert fc is not None
            assert fc.pdf_sha256 is not None

    def test_idempotent_daily_run(self, db_session):
        """Running daily twice with same data produces no new results."""
        daily_html = DAILY_FIXTURE.read_text()
        pdf_bytes = _create_fake_pdf()

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            fetcher = _make_mock_fetcher(daily_html, pdf_bytes)

            pipeline = Pipeline(
                db_session=db_session,
                storage=storage,
                fetcher=fetcher,
                session_year=2026,
            )

            # First run
            results1 = pipeline.run_daily()
            assert len(results1) == 4

            # Second run — same HTML hash means page is skipped
            results2 = pipeline.run_daily()
            assert len(results2) == 0

    def test_extract_and_diff(self, db_session):
        """Test extraction and diffing stages independently."""
        pdf_text = (
            "Section 1. Definitions.\n\nSection 2. This act shall take effect October 1, 2026."
        )
        pdf_bytes = _create_fake_pdf(pdf_text)

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            pdf_path = storage.store_pdf(2026, "SB00099", 1, pdf_bytes)

            pipeline = Pipeline(
                db_session=db_session,
                storage=storage,
                session_year=2026,
            )

            doc = pipeline.extract_document(pdf_path, "2026-SB00099-FC00001")
            assert doc is not None
            assert len(doc.sections) > 0
            assert doc.overall_extraction_confidence > 0

            # Diff with no prior
            diff = pipeline.diff_version(doc, bill_db_id=999, file_copy_number=1)
            assert diff.compared_against == "none"
            assert diff.sections_added == len(doc.sections)

    def test_score_and_summarize(self, db_session):
        """Test scoring and summary generation."""
        pdf_text = (
            "Section 1. AN ACT CONCERNING transportation and transit.\n\n"
            "Section 2. There is appropriated from the General Fund "
            "the sum of one million dollars."
        )
        pdf_bytes = _create_fake_pdf(pdf_text)

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            pdf_path = storage.store_pdf(2026, "SB00100", 5, pdf_bytes)

            pipeline = Pipeline(
                db_session=db_session,
                storage=storage,
                session_year=2026,
            )

            doc = pipeline.extract_document(pdf_path, "2026-SB00100-FC00005")
            assert doc is not None

            diff = pipeline.diff_version(doc, bill_db_id=999, file_copy_number=5)
            result = pipeline.score_and_summarize(doc, diff, bill_title="Transportation Act")

            assert result["tags"].subject_tags  # Should tag transportation
            assert result["summary"].one_sentence_summary
            assert result["summary"].practical_takeaways
