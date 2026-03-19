"""Text normalization for extracted legislative text.

Rules per technical contract §10.3:
- Preserve substantive capitalization
- Remove repeated page headers/footers
- Remove stand-alone page numbers
- Repair common hyphenation line breaks
- Collapse repeated blank lines
- Preserve section boundaries and effective-date language
- Store both pre-clean and post-clean text
"""

import re
from collections import Counter

from src.schemas.extraction import PageText


def normalize_pages(pages: list[PageText]) -> list[PageText]:
    """Clean all pages and return updated PageText objects with cleaned_text set."""
    # Detect repeated headers/footers across pages
    headers, footers = _detect_repeated_lines(pages)

    normalized = []
    for page in pages:
        cleaned = _clean_page_text(page.raw_text, headers, footers)
        normalized.append(
            PageText(
                page_number=page.page_number,
                raw_text=page.raw_text,
                cleaned_text=cleaned,
                extraction_method=page.extraction_method,
                extraction_confidence=page.extraction_confidence,
            )
        )
    return normalized


def normalize_full_text(raw_text: str) -> str:
    """Clean a single block of full text."""
    text = raw_text

    # Remove standalone page numbers
    text = re.sub(r"^\s*\d{1,4}\s*$", "", text, flags=re.MULTILINE)

    # Repair hyphenation at line breaks (word- \n continuation)
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)

    # Collapse multiple blank lines to a single one
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove trailing whitespace on each line
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)

    return text.strip()


def _detect_repeated_lines(pages: list[PageText], threshold: int = 3) -> tuple[set[str], set[str]]:
    """Detect lines that appear on multiple pages (likely headers/footers).

    Returns (headers, footers) as sets of normalized line strings.
    """
    if len(pages) < threshold:
        return set(), set()

    first_lines: Counter[str] = Counter()
    last_lines: Counter[str] = Counter()

    for page in pages:
        lines = page.raw_text.strip().split("\n")
        if lines:
            first = lines[0].strip()
            if first:
                first_lines[first] += 1
        if len(lines) > 1:
            last = lines[-1].strip()
            if last:
                last_lines[last] += 1

    headers = {line for line, count in first_lines.items() if count >= threshold}
    footers = {line for line, count in last_lines.items() if count >= threshold}

    return headers, footers


def _clean_page_text(text: str, headers: set[str], footers: set[str]) -> str:
    """Clean a single page's text."""
    lines = text.split("\n")
    cleaned_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Remove detected repeated headers (first few lines)
        if i < 3 and stripped in headers:
            continue

        # Remove detected repeated footers (last few lines)
        if i >= len(lines) - 3 and stripped in footers:
            continue

        # Remove standalone page numbers
        if re.match(r"^\s*-?\s*\d{1,4}\s*-?\s*$", stripped):
            continue

        cleaned_lines.append(line)

    result = "\n".join(cleaned_lines)

    # Repair hyphenation
    result = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", result)

    # Collapse multiple blank lines
    result = re.sub(r"\n{3,}", "\n\n", result)

    # Remove trailing whitespace per line
    result = re.sub(r"[ \t]+$", "", result, flags=re.MULTILINE)

    return result.strip()
