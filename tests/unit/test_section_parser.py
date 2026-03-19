"""Tests for the section parser."""

from src.extract.section_parser import (
    has_appropriation_section,
    has_definition_section,
    has_effective_date_section,
    parse_sections,
)

SAMPLE_BILL_TEXT = (
    "AN ACT CONCERNING TRANSPORTATION NETWORK COMPANIES\n\n"
    "Be it enacted by the Senate and House of Representatives "
    "in General Assembly convened:\n\n"
    "Section 1. (NEW) (Effective July 1, 2026) "
    "As used in this section and sections 2 to 5, inclusive:\n\n"
    '(a) "Transportation network company" means an entity that uses '
    "a digital network to connect a rider to a driver.\n\n"
    '(b) "Mobility service" means any publicly or privately funded '
    "demand-responsive transportation service.\n\n"
    "Section 2. (NEW) (Effective July 1, 2026) "
    "The Commissioner of Transportation shall establish "
    "a municipal transit pilot program.\n\n"
    "(a) The program shall provide grants to municipalities "
    "for demand-responsive transportation services.\n\n"
    "(b) The commissioner shall adopt regulations "
    "to implement this section.\n\n"
    "Section 3. (NEW) (Effective July 1, 2026) "
    "There is appropriated from the General Fund the sum of "
    "five million dollars for the purposes of this act.\n\n"
    "Section 4. This act shall take effect July 1, 2026.\n"
)


class TestSectionParser:
    def test_parses_formal_sections(self):
        sections = parse_sections(SAMPLE_BILL_TEXT)
        # Should find preamble + 4 sections
        section_ids = [s.section_id for s in sections]
        assert "preamble" in section_ids
        assert "sec_1" in section_ids
        assert "sec_2" in section_ids
        assert "sec_3" in section_ids
        assert "sec_4" in section_ids

    def test_section_count(self):
        sections = parse_sections(SAMPLE_BILL_TEXT)
        assert len(sections) == 5  # preamble + 4 sections

    def test_preamble_captured(self):
        sections = parse_sections(SAMPLE_BILL_TEXT)
        preamble = next(s for s in sections if s.section_id == "preamble")
        assert "AN ACT" in preamble.text

    def test_section_text_complete(self):
        sections = parse_sections(SAMPLE_BILL_TEXT)
        sec1 = next(s for s in sections if s.section_id == "sec_1")
        assert "Transportation network company" in sec1.text
        assert "Mobility service" in sec1.text

    def test_no_text_discarded(self):
        sections = parse_sections(SAMPLE_BILL_TEXT)
        total_text = " ".join(s.text for s in sections)
        # Key phrases should all be present
        assert "transportation network company" in total_text.lower()
        assert "municipal transit pilot" in total_text.lower()
        assert "appropriated" in total_text.lower()
        assert "take effect" in total_text.lower()

    def test_section_boundaries(self):
        sections = parse_sections(SAMPLE_BILL_TEXT)
        for s in sections:
            assert s.start_char >= 0
            assert s.end_char > s.start_char
            assert s.start_page >= 1

    def test_effective_date_detection(self):
        sections = parse_sections(SAMPLE_BILL_TEXT)
        assert has_effective_date_section(sections) is True

    def test_definition_detection(self):
        sections = parse_sections(SAMPLE_BILL_TEXT)
        assert has_definition_section(sections) is True

    def test_appropriation_detection(self):
        sections = parse_sections(SAMPLE_BILL_TEXT)
        assert has_appropriation_section(sections) is True

    def test_no_formal_sections_falls_back_to_chunks(self):
        text = (
            "This is a plain text document without any section markers.\n\n"
            "It has paragraphs but no legislative structure.\n\n"
            "Another paragraph with some content."
        )
        sections = parse_sections(text)
        assert len(sections) > 0
        assert all(s.section_id.startswith("chunk_") for s in sections)

    def test_sec_dot_format(self):
        text = "Preamble text.\n\nSec. 1. First section content.\n\nSec. 2. Second section content."
        sections = parse_sections(text)
        section_ids = [s.section_id for s in sections]
        assert "sec_1" in section_ids
        assert "sec_2" in section_ids
