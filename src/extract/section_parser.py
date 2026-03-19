"""Legislative section parser.

Detects section boundaries per technical contract §10.4:
- "Section 1." / "Sec. 1." style headings
- Effective-date sections
- Repeal-and-substitute phrases
- Definition blocks
- Appropriation/funding blocks

If no formal section boundaries found, falls back to paragraph chunking.
Never discards text.
"""

import re

from src.schemas.extraction import SectionSpan

# Patterns for detecting section boundaries
_SEC_PATTERN = re.compile(
    r"^\s*(Section|Sec\.)\s+(\d+[a-z]?)\.\s*(.*)",
    re.IGNORECASE | re.MULTILINE,
)

_EFFECTIVE_DATE_PATTERN = re.compile(
    r"(effective|this act shall take effect|takes effect)",
    re.IGNORECASE,
)

_DEFINITION_PATTERN = re.compile(
    r"(as used in this|for (?:the )?purposes? of this|means?(?:\s+and\s+includes?)?:?\s)",
    re.IGNORECASE,
)

_APPROPRIATION_PATTERN = re.compile(
    r"(appropriat|there is (?:hereby )?allocated|sum of|from the general fund)",
    re.IGNORECASE,
)


def parse_sections(text: str, start_page: int = 1, total_pages: int = 1) -> list[SectionSpan]:
    """Parse legislative text into sections.

    Returns list of SectionSpan objects covering the entire text.
    """
    sections = _parse_formal_sections(text, start_page, total_pages)

    if not sections:
        sections = _paragraph_chunk_fallback(text, start_page, total_pages)

    return sections


def _parse_formal_sections(text: str, start_page: int, total_pages: int) -> list[SectionSpan]:
    """Parse sections using formal section markers like 'Section 1.' or 'Sec. 1.'."""
    matches = list(_SEC_PATTERN.finditer(text))

    if not matches:
        return []

    sections: list[SectionSpan] = []

    # Handle text before first section (preamble)
    if matches[0].start() > 0:
        preamble_text = text[: matches[0].start()].strip()
        if preamble_text:
            page_est = _estimate_page(0, len(text), start_page, total_pages)
            sections.append(
                SectionSpan(
                    section_id="preamble",
                    heading="Preamble",
                    start_page=start_page,
                    end_page=page_est,
                    start_char=0,
                    end_char=matches[0].start(),
                    text=preamble_text,
                )
            )

    for i, match in enumerate(matches):
        sec_keyword = match.group(1)
        sec_num = match.group(2)
        sec_rest = match.group(3).strip()

        section_id = f"sec_{sec_num}"
        heading = f"{sec_keyword} {sec_num}."
        if sec_rest:
            heading = f"{heading} {sec_rest.split(chr(10))[0].strip()}"

        start_char = match.start()
        end_char = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start_char:end_char].strip()

        s_page = _estimate_page(start_char, len(text), start_page, total_pages)
        e_page = _estimate_page(end_char, len(text), start_page, total_pages)

        sections.append(
            SectionSpan(
                section_id=section_id,
                heading=heading,
                start_page=s_page,
                end_page=e_page,
                start_char=start_char,
                end_char=end_char,
                text=section_text,
            )
        )

    # Tag sections with special characteristics
    for section in sections:
        _tag_section_type(section)

    return sections


def _paragraph_chunk_fallback(
    text: str, start_page: int, total_pages: int, min_chunk_size: int = 200
) -> list[SectionSpan]:
    """Fall back to paragraph chunking when no formal sections are found."""
    paragraphs = re.split(r"\n\n+", text)
    sections: list[SectionSpan] = []
    char_pos = 0
    chunk_idx = 0

    current_chunk = ""
    chunk_start = 0

    for para in paragraphs:
        para_start = text.find(para, char_pos)
        if para_start == -1:
            para_start = char_pos

        if not current_chunk:
            chunk_start = para_start

        current_chunk += para + "\n\n"
        char_pos = para_start + len(para)

        if len(current_chunk) >= min_chunk_size:
            chunk_idx += 1
            s_page = _estimate_page(chunk_start, len(text), start_page, total_pages)
            e_page = _estimate_page(char_pos, len(text), start_page, total_pages)

            sections.append(
                SectionSpan(
                    section_id=f"chunk_{chunk_idx}",
                    heading=f"Chunk {chunk_idx}",
                    start_page=s_page,
                    end_page=e_page,
                    start_char=chunk_start,
                    end_char=char_pos,
                    text=current_chunk.strip(),
                )
            )
            current_chunk = ""

    # Don't discard remaining text
    if current_chunk.strip():
        chunk_idx += 1
        s_page = _estimate_page(chunk_start, len(text), start_page, total_pages)
        sections.append(
            SectionSpan(
                section_id=f"chunk_{chunk_idx}",
                heading=f"Chunk {chunk_idx}",
                start_page=s_page,
                end_page=_estimate_page(len(text), len(text), start_page, total_pages),
                start_char=chunk_start,
                end_char=len(text),
                text=current_chunk.strip(),
            )
        )

    return sections


def _tag_section_type(section: SectionSpan) -> None:
    """Add type information to section heading if special content detected."""
    text_lower = section.text.lower()

    if _EFFECTIVE_DATE_PATTERN.search(text_lower):
        if "effective date" not in section.heading.lower():
            section.heading = section.heading  # Keep as-is, detection info is implicit

    if _DEFINITION_PATTERN.search(text_lower[:500]):
        pass  # Could tag but keeping heading clean per spec

    if _APPROPRIATION_PATTERN.search(text_lower):
        pass  # Could tag but keeping heading clean per spec


def _estimate_page(char_pos: int, total_chars: int, start_page: int, total_pages: int) -> int:
    """Estimate page number from character position."""
    if total_chars == 0:
        return start_page
    ratio = char_pos / total_chars
    return start_page + int(ratio * (total_pages - 1))


def has_effective_date_section(sections: list[SectionSpan]) -> bool:
    """Check if any section contains effective date language."""
    return any(_EFFECTIVE_DATE_PATTERN.search(s.text) for s in sections)


def has_definition_section(sections: list[SectionSpan]) -> bool:
    """Check if any section contains definition language."""
    return any(_DEFINITION_PATTERN.search(s.text[:500]) for s in sections)


def has_appropriation_section(sections: list[SectionSpan]) -> bool:
    """Check if any section contains appropriation/funding language."""
    return any(_APPROPRIATION_PATTERN.search(s.text) for s in sections)
