"""Tests for PDF text extraction."""

import pymupdf

from src.extract.confidence import compute_overall_confidence, needs_ocr_fallback
from src.extract.pdf_text import extract_text_from_bytes

_DEFAULT_TEXT = "Section 1. This is a test legislative bill.\n\nSection 2. Another section."


def _create_test_pdf(text: str = _DEFAULT_TEXT) -> bytes:
    """Create a minimal PDF with the given text for testing."""
    doc = pymupdf.open()
    page = doc.new_page()
    text_point = pymupdf.Point(72, 72)
    page.insert_text(text_point, text, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestPDFExtraction:
    def test_extracts_text_from_pdf(self):
        pdf_bytes = _create_test_pdf()
        pages = extract_text_from_bytes(pdf_bytes)
        assert len(pages) == 1
        assert "Section 1" in pages[0].raw_text

    def test_page_numbers_start_at_one(self):
        pdf_bytes = _create_test_pdf()
        pages = extract_text_from_bytes(pdf_bytes)
        assert pages[0].page_number == 1

    def test_extraction_method_is_text(self):
        pdf_bytes = _create_test_pdf()
        pages = extract_text_from_bytes(pdf_bytes)
        assert pages[0].extraction_method == "text"

    def test_confidence_positive_for_good_text(self):
        pdf_bytes = _create_test_pdf(
            "Section 1. AN ACT CONCERNING transportation.\n"
            "This shall amend the statute effective July 1, 2026."
        )
        pages = extract_text_from_bytes(pdf_bytes)
        assert pages[0].extraction_confidence > 0.3

    def test_multi_page_pdf(self):
        doc = pymupdf.open()
        for i in range(3):
            page = doc.new_page()
            page.insert_text(pymupdf.Point(72, 72), f"Page {i + 1} content", fontsize=11)
        pdf_bytes = doc.tobytes()
        doc.close()

        pages = extract_text_from_bytes(pdf_bytes)
        assert len(pages) == 3
        assert pages[0].page_number == 1
        assert pages[2].page_number == 3


class TestConfidenceScoring:
    def test_high_confidence_for_good_text(self):
        from src.schemas.extraction import PageText

        pages = [
            PageText(
                page_number=1,
                raw_text="Section 1. AN ACT CONCERNING transportation statutes and amendments.",
                cleaned_text="",
                extraction_method="text",
                extraction_confidence=0.85,
            )
        ]
        overall, warnings = compute_overall_confidence(pages)
        assert overall > 0.5

    def test_low_confidence_for_empty_pages(self):
        from src.schemas.extraction import PageText

        pages = [
            PageText(
                page_number=1,
                raw_text="",
                cleaned_text="",
                extraction_method="text",
                extraction_confidence=0.0,
            )
        ]
        overall, warnings = compute_overall_confidence(pages)
        assert overall < 0.5
        assert len(warnings) > 0

    def test_needs_ocr_fallback(self):
        assert needs_ocr_fallback(0.3) is True
        assert needs_ocr_fallback(0.5) is False
        assert needs_ocr_fallback(0.8) is False

    def test_empty_pages_list(self):
        overall, warnings = compute_overall_confidence([])
        assert overall == 0.0
        assert "No pages" in warnings[0]
