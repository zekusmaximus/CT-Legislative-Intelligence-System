"""OCR fallback for PDFs with poor text extraction.

Only used when extraction confidence falls below threshold.
Requires pytesseract and Pillow (optional dependencies).
"""

import logging

from src.schemas.extraction import PageText

logger = logging.getLogger(__name__)


def ocr_page_from_pdf(pdf_path: str, page_number: int) -> PageText | None:
    """Extract text from a specific PDF page using OCR.

    Returns PageText or None if OCR is unavailable.
    """
    try:
        import pymupdf
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.warning("OCR dependencies not installed (pytesseract, Pillow)")
        return None

    try:
        # Close the PDF before invoking OCR so Windows does not keep the file
        # handle locked if pytesseract raises.
        doc = pymupdf.open(pdf_path)
        try:
            page = doc[page_number - 1]

            # Render page to image at 300 DPI
            mat = pymupdf.Matrix(300 / 72, 300 / 72)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        finally:
            doc.close()

        raw_text = pytesseract.image_to_string(img)

        return PageText(
            page_number=page_number,
            raw_text=raw_text,
            cleaned_text=raw_text,
            extraction_method="ocr",
            extraction_confidence=0.6,  # OCR baseline confidence
        )
    except Exception as e:
        logger.error("OCR failed for page %d of %s: %s", page_number, pdf_path, e)
        return None


def ocr_all_low_confidence_pages(
    pdf_path: str,
    pages: list[PageText],
    confidence_threshold: float = 0.50,
) -> list[PageText]:
    """Re-extract low-confidence pages using OCR.

    Returns a new list with OCR results replacing low-confidence pages.
    """
    result = []
    for page in pages:
        if page.extraction_confidence < confidence_threshold:
            ocr_page = ocr_page_from_pdf(pdf_path, page.page_number)
            if ocr_page and len(ocr_page.raw_text.strip()) > len(page.raw_text.strip()):
                logger.info(
                    "OCR improved page %d: %d -> %d chars",
                    page.page_number,
                    len(page.raw_text),
                    len(ocr_page.raw_text),
                )
                result.append(ocr_page)
                continue
        result.append(page)
    return result
