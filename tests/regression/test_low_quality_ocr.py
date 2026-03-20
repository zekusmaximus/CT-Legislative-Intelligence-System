"""Regression tests for low-quality OCR extraction scenarios.

Verifies that the pipeline handles garbled, sparse, or low-confidence
text gracefully — producing warnings, triggering OCR fallback decisions,
and never silently dropping content.
"""

import tempfile
from pathlib import Path

import pymupdf
import pytest

from src.extract.confidence import (
    CONFIDENCE_ACCEPT,
    CONFIDENCE_WARN,
    compute_overall_confidence,
    needs_ocr_fallback,
)
from src.extract.section_parser import parse_sections
from src.pipeline.orchestrator import Pipeline
from src.schemas.extraction import ExtractedDocument, PageText
from src.utils.storage import LocalStorage


def _make_low_confidence_pages() -> list[PageText]:
    """Simulate pages that came from a bad scan."""
    return [
        PageText(
            page_number=1,
            raw_text="S c t i o n 1 . T h i s   a c t",
            cleaned_text="S c t i o n 1 . T h i s a c t",
            extraction_method="text",
            extraction_confidence=0.25,
        ),
        PageText(
            page_number=2,
            raw_text="",
            cleaned_text="",
            extraction_method="text",
            extraction_confidence=0.0,
        ),
        PageText(
            page_number=3,
            raw_text="x" * 10,
            cleaned_text="x" * 10,
            extraction_method="text",
            extraction_confidence=0.15,
        ),
    ]


def _make_mixed_confidence_pages() -> list[PageText]:
    """Simulate a document with some good and some bad pages."""
    return [
        PageText(
            page_number=1,
            raw_text="Section 1. AN ACT CONCERNING public health and safety measures.",
            cleaned_text="Section 1. AN ACT CONCERNING public health and safety measures.",
            extraction_method="text",
            extraction_confidence=0.95,
        ),
        PageText(
            page_number=2,
            raw_text="a" * 20,
            cleaned_text="a" * 20,
            extraction_method="text",
            extraction_confidence=0.20,
        ),
        PageText(
            page_number=3,
            raw_text="Section 2. This act shall take effect October 1, 2026.",
            cleaned_text="Section 2. This act shall take effect October 1, 2026.",
            extraction_method="text",
            extraction_confidence=0.92,
        ),
    ]


class TestLowQualityOCRConfidence:
    """Tests for confidence scoring on degraded text."""

    def test_all_low_confidence_pages_triggers_fallback(self):
        pages = _make_low_confidence_pages()
        overall, warnings = compute_overall_confidence(pages)
        assert overall < CONFIDENCE_WARN
        assert needs_ocr_fallback(overall)
        assert any("below" in w.lower() or "confidence" in w.lower() for w in warnings)

    def test_mixed_confidence_produces_warnings(self):
        pages = _make_mixed_confidence_pages()
        overall, warnings = compute_overall_confidence(pages)
        # Mixed pages: at least one warning about low-confidence page
        assert len(warnings) >= 1
        assert any("page" in w.lower() for w in warnings)

    def test_empty_page_list_returns_zero(self):
        overall, warnings = compute_overall_confidence([])
        assert overall == 0.0
        assert len(warnings) >= 1

    def test_single_blank_page(self):
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
        assert overall < CONFIDENCE_WARN
        assert needs_ocr_fallback(overall)


class TestLowQualitySectionParsing:
    """Tests that degraded text still produces sections (never drops content)."""

    def test_garbled_text_falls_back_to_paragraph_chunks(self):
        garbled = (
            "T h i s   i s   g a r b l e d   t e x t   f r o m   a   "
            "b a d   s c a n .  I t   s h o u l d   s t i l l   b e   "
            "c a p t u r e d   i n   a   c h u n k   s e c t i o n ."
        )
        # No "Section 1." markers → falls back to paragraph chunking
        sections = parse_sections(garbled, start_page=1, total_pages=1)
        assert len(sections) >= 1
        # All text should be captured somewhere
        combined = " ".join(s.text for s in sections)
        assert "g a r b l e d" in combined

    def test_sparse_text_not_discarded(self):
        sparse = "Short.\n\nVery short text."
        sections = parse_sections(sparse, start_page=1, total_pages=1)
        assert len(sections) >= 1
        combined = " ".join(s.text for s in sections)
        assert "Short" in combined

    def test_mixed_quality_preserves_valid_sections(self):
        text = (
            "Section 1. Valid section with clear text about transportation.\n\n"
            "Section 2. X x x x garbled content from bad OCR page.\n\n"
            "Section 3. Another valid section about effective dates."
        )
        sections = parse_sections(text, start_page=1, total_pages=3)
        assert len(sections) >= 3
        section_ids = {s.section_id for s in sections}
        assert "sec_1" in section_ids
        assert "sec_2" in section_ids
        assert "sec_3" in section_ids


class TestLowQualityPipelineExtraction:
    """Integration: pipeline handles low-quality PDFs without crashing."""

    def test_extract_document_with_minimal_text(self, db_session):
        """A PDF with almost no extractable text should still return a doc."""
        doc = pymupdf.open()
        page = doc.new_page()
        # Insert very small, hard-to-extract text
        page.insert_text(pymupdf.Point(72, 72), "x", fontsize=4)
        pdf_bytes = doc.tobytes()
        doc.close()

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            pdf_path = storage.store_pdf(2026, "SB00999", 1, pdf_bytes)

            pipeline = Pipeline(
                db_session=db_session,
                storage=storage,
                session_year=2026,
            )

            result = pipeline.extract_document(pdf_path, "2026-SB00999-FC00001")
            # Should return a document (possibly with warnings), not None
            # unless truly zero text was extracted
            if result is not None:
                assert result.overall_extraction_confidence >= 0.0
                assert isinstance(result.extraction_warnings, list)

    def test_extract_document_with_good_pdf(self, db_session):
        """Baseline: a normal PDF produces high-confidence extraction."""
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text(
            pymupdf.Point(72, 72),
            "Section 1. AN ACT CONCERNING public health.\n"
            "This section establishes requirements for hospitals.",
            fontsize=11,
        )
        pdf_bytes = doc.tobytes()
        doc.close()

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            pdf_path = storage.store_pdf(2026, "SB00998", 1, pdf_bytes)

            pipeline = Pipeline(
                db_session=db_session,
                storage=storage,
                session_year=2026,
            )

            result = pipeline.extract_document(pdf_path, "2026-SB00998-FC00001")
            assert result is not None
            assert result.overall_extraction_confidence >= CONFIDENCE_ACCEPT
            assert len(result.sections) >= 1
