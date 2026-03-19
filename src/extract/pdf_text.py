"""PDF text extraction using PyMuPDF."""

import logging

import pymupdf

from src.schemas.extraction import PageText

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_path: str) -> list[PageText]:
    """Extract text from each page of a PDF using PyMuPDF.

    Returns a list of PageText objects, one per page.
    """
    pages: list[PageText] = []

    doc = pymupdf.open(pdf_path)
    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            raw_text = page.get_text("text")
            confidence = _estimate_page_confidence(raw_text)

            pages.append(
                PageText(
                    page_number=page_num + 1,
                    raw_text=raw_text,
                    cleaned_text=raw_text,  # Cleaning happens in normalize step
                    extraction_method="text",
                    extraction_confidence=confidence,
                )
            )
    finally:
        doc.close()

    return pages


def extract_text_from_bytes(pdf_bytes: bytes) -> list[PageText]:
    """Extract text from PDF bytes (useful for testing)."""
    pages: list[PageText] = []

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            raw_text = page.get_text("text")
            confidence = _estimate_page_confidence(raw_text)

            pages.append(
                PageText(
                    page_number=page_num + 1,
                    raw_text=raw_text,
                    cleaned_text=raw_text,
                    extraction_method="text",
                    extraction_confidence=confidence,
                )
            )
    finally:
        doc.close()

    return pages


def get_page_count(pdf_path: str) -> int:
    """Get the number of pages in a PDF."""
    doc = pymupdf.open(pdf_path)
    try:
        return len(doc)
    finally:
        doc.close()


def _estimate_page_confidence(text: str) -> float:
    """Estimate extraction confidence for a single page.

    Based on:
    - Ratio of printable characters to total length
    - Presence of expected legislative patterns
    - Absence of OCR garbage indicators
    """
    if not text or len(text.strip()) < 10:
        return 0.0

    stripped = text.strip()

    # Check printable ratio
    printable_count = sum(1 for c in stripped if c.isprintable() or c in "\n\t")
    printable_ratio = printable_count / len(stripped) if stripped else 0.0

    # Check for legislative patterns
    legislative_patterns = [
        "Section",
        "Sec.",
        "AN ACT",
        "CONCERNING",
        "effective",
        "shall",
        "subsection",
        "subdivision",
        "amended",
        "repealed",
        "chapter",
        "statute",
    ]
    pattern_score = 0.0
    text_lower = stripped.lower()
    for pattern in legislative_patterns:
        if pattern.lower() in text_lower:
            pattern_score += 0.08
    pattern_score = min(pattern_score, 0.4)

    # Check for OCR garbage (high ratio of non-alpha chars)
    alpha_count = sum(1 for c in stripped if c.isalpha())
    alpha_ratio = alpha_count / len(stripped) if stripped else 0.0
    garbage_penalty = 0.0
    if alpha_ratio < 0.3:
        garbage_penalty = 0.3

    confidence = (printable_ratio * 0.4) + pattern_score + (alpha_ratio * 0.2) - garbage_penalty

    return max(0.0, min(1.0, confidence))
