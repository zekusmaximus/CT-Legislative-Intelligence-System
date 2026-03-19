"""Extraction confidence scoring for full documents.

Thresholds per technical contract §10.2:
  >= 0.80: accept text extraction
  0.50-0.79: accept with warning
  < 0.50: force OCR fallback
"""

from src.schemas.extraction import PageText

CONFIDENCE_ACCEPT = 0.80
CONFIDENCE_WARN = 0.50


def compute_overall_confidence(pages: list[PageText]) -> tuple[float, list[str]]:
    """Compute overall extraction confidence and generate warnings.

    Returns (confidence_score, warnings_list).
    """
    if not pages:
        return 0.0, ["No pages extracted"]

    warnings: list[str] = []

    # Average per-page confidence
    avg_confidence = sum(p.extraction_confidence for p in pages) / len(pages)

    # Proportion of pages with meaningful text
    non_trivial = sum(1 for p in pages if len(p.raw_text.strip()) > 50)
    non_trivial_ratio = non_trivial / len(pages)

    if non_trivial_ratio < 0.5:
        warnings.append(f"Only {non_trivial}/{len(pages)} pages have meaningful text")

    # Count low-confidence pages
    low_confidence_pages = [p for p in pages if p.extraction_confidence < CONFIDENCE_WARN]
    if low_confidence_pages:
        warnings.append(
            f"{len(low_confidence_pages)} page(s) below confidence threshold: "
            f"pages {', '.join(str(p.page_number) for p in low_confidence_pages)}"
        )

    # Blend scores
    overall = (avg_confidence * 0.6) + (non_trivial_ratio * 0.4)
    overall = max(0.0, min(1.0, overall))

    if overall < CONFIDENCE_ACCEPT:
        warnings.append(f"Overall confidence {overall:.2f} below acceptance threshold")

    return overall, warnings


def needs_ocr_fallback(overall_confidence: float) -> bool:
    """Determine if OCR fallback is needed."""
    return overall_confidence < CONFIDENCE_WARN
