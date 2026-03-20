"""Regression tests for multi-version diff scenarios.

Verifies correct behavior when diffing across version sequences:
new bill (no prior), single update, multiple consecutive updates,
section additions/removals, and renumbered sections.
"""

import pytest

from src.diff.change_classifier import classify_changes
from src.diff.section_differ import diff_documents
from src.schemas.extraction import ExtractedDocument, PageText, SectionSpan


def _make_doc(version_id: str, sections: list[SectionSpan]) -> ExtractedDocument:
    """Build an ExtractedDocument from a list of sections."""
    full_text = "\n\n".join(s.text for s in sections)
    return ExtractedDocument(
        canonical_version_id=version_id,
        pages=[
            PageText(
                page_number=1,
                raw_text=full_text,
                cleaned_text=full_text,
                extraction_method="text",
                extraction_confidence=0.95,
            )
        ],
        full_raw_text=full_text,
        full_cleaned_text=full_text,
        sections=sections,
        overall_extraction_confidence=0.95,
        extraction_warnings=[],
    )


def _sec(sec_id: str, heading: str, text: str) -> SectionSpan:
    return SectionSpan(
        section_id=sec_id,
        heading=heading,
        start_page=1,
        end_page=1,
        start_char=0,
        end_char=len(text),
        text=text,
    )


class TestNewBillNoPrior:
    """First version of a bill — no prior to diff against."""

    def test_all_sections_marked_added(self):
        doc = _make_doc("2026-SB00001-FC00001", [
            _sec("sec_1", "Section 1", "Section 1. Definitions."),
            _sec("sec_2", "Section 2", "Section 2. This act shall take effect July 1, 2026."),
        ])
        result = diff_documents(doc, None)
        assert result.compared_against == "none"
        assert result.sections_added == 2
        assert result.sections_removed == 0
        assert result.sections_modified == 0
        assert all(d.delta_type == "added" for d in result.section_deltas)

    def test_change_events_for_new_bill(self):
        doc = _make_doc("2026-SB00001-FC00001", [
            _sec("sec_1", "Section 1", "Section 1. There is appropriated from the General Fund the sum of one million dollars."),
        ])
        result = diff_documents(doc, None)
        events = classify_changes(result)
        flags = {e.change_flag for e in events}
        assert "section_added" in flags
        assert "appropriation_added" in flags


class TestSingleVersionUpdate:
    """One section modified between FC1 and FC2."""

    def test_modified_section_detected(self):
        v1 = _make_doc("2026-SB00010-FC00001", [
            _sec("sec_1", "Section 1", "Section 1. The penalty shall be fifty dollars."),
            _sec("sec_2", "Section 2", "Section 2. Effective October 1, 2026."),
        ])
        v2 = _make_doc("2026-SB00010-FC00002", [
            _sec("sec_1", "Section 1", "Section 1. The penalty shall be five hundred dollars for each violation."),
            _sec("sec_2", "Section 2", "Section 2. Effective October 1, 2026."),
        ])
        result = diff_documents(v2, v1)
        assert result.compared_against == "prior_file_copy"
        assert result.sections_modified == 1
        assert result.sections_added == 0
        assert result.sections_removed == 0

        # sec_1 modified, sec_2 unchanged
        delta_map = {d.section_id: d for d in result.section_deltas}
        assert delta_map["sec_1"].delta_type == "modified"
        assert delta_map["sec_2"].delta_type == "unchanged"

    def test_change_events_for_modified_section(self):
        v1 = _make_doc("2026-SB00010-FC00001", [
            _sec("sec_1", "Section 1", "Section 1. The penalty shall be fifty dollars."),
        ])
        v2 = _make_doc("2026-SB00010-FC00002", [
            _sec("sec_1", "Section 1", "Section 1. The penalty shall be five hundred dollars and imprisonment for 30 days."),
        ])
        result = diff_documents(v2, v1)
        events = classify_changes(result)
        flags = {e.change_flag for e in events}
        assert "penalty_added" in flags


class TestSectionAddedAndRemoved:
    """Sections added or removed across versions."""

    def test_section_added(self):
        v1 = _make_doc("2026-HB00020-FC00001", [
            _sec("sec_1", "Section 1", "Section 1. Definitions."),
        ])
        v2 = _make_doc("2026-HB00020-FC00002", [
            _sec("sec_1", "Section 1", "Section 1. Definitions."),
            _sec("sec_2", "Section 2", "Section 2. New reporting requirement: annual report to the commissioner."),
        ])
        result = diff_documents(v2, v1)
        assert result.sections_added == 1
        assert result.sections_modified == 0

        events = classify_changes(result)
        flags = {e.change_flag for e in events}
        assert "section_added" in flags
        assert "reporting_requirement_added" in flags

    def test_section_removed(self):
        v1 = _make_doc("2026-HB00030-FC00001", [
            _sec("sec_1", "Section 1", "Section 1. Sunset provision: this section shall expire on June 30, 2028."),
            _sec("sec_2", "Section 2", "Section 2. Effective date."),
        ])
        v2 = _make_doc("2026-HB00030-FC00002", [
            _sec("sec_2", "Section 2", "Section 2. Effective date."),
        ])
        result = diff_documents(v2, v1)
        assert result.sections_removed == 1
        events = classify_changes(result)
        flags = {e.change_flag for e in events}
        assert "section_removed" in flags


class TestMultipleConsecutiveUpdates:
    """Three-version chain: FC1 → FC2 → FC3."""

    def test_three_version_chain(self):
        v1 = _make_doc("2026-SB00050-FC00001", [
            _sec("sec_1", "Section 1", "Section 1. Original text about licensing requirements."),
        ])
        v2 = _make_doc("2026-SB00050-FC00002", [
            _sec("sec_1", "Section 1", "Section 1. Updated text about licensing requirements and certification."),
            _sec("sec_2", "Section 2", "Section 2. New enforcement mechanism."),
        ])
        v3 = _make_doc("2026-SB00050-FC00003", [
            _sec("sec_1", "Section 1", "Section 1. Final text about licensing, certification, and continuing education."),
            _sec("sec_2", "Section 2", "Section 2. New enforcement mechanism with penalties up to ten thousand dollars."),
            _sec("sec_3", "Section 3", "Section 3. This act shall take effect January 1, 2027."),
        ])

        # v2 vs v1
        diff_2_1 = diff_documents(v2, v1)
        assert diff_2_1.sections_modified == 1  # sec_1 changed
        assert diff_2_1.sections_added == 1  # sec_2 new

        # v3 vs v2
        diff_3_2 = diff_documents(v3, v2)
        assert diff_3_2.sections_modified == 2  # sec_1 and sec_2 changed
        assert diff_3_2.sections_added == 1  # sec_3 new

        events = classify_changes(diff_3_2)
        flags = {e.change_flag for e in events}
        assert "section_added" in flags
        assert "effective_date_changed" in flags


class TestRenumberedSectionAlignment:
    """Sections renumbered after an insertion should be fuzzy-matched."""

    def test_renumbered_section_detected_as_modified_not_add_remove(self):
        """When sec_2 becomes sec_3 (same content), it should be 'unchanged' not add+remove."""
        v1 = _make_doc("2026-SB00070-FC00001", [
            _sec("sec_1", "Section 1", "Section 1. Definitions for this chapter."),
            _sec("sec_2", "Section 2", "Section 2. The penalty shall be five hundred dollars for each violation."),
        ])
        v2 = _make_doc("2026-SB00070-FC00002", [
            _sec("sec_1", "Section 1", "Section 1. Definitions for this chapter."),
            _sec("sec_1a", "Section 1a", "Section 1a. Newly inserted section with additional definitions."),
            _sec("sec_3", "Section 3", "Section 3. The penalty shall be five hundred dollars for each violation."),
        ])
        result = diff_documents(v2, v1)

        # sec_2 and sec_3 have same text → fuzzy alignment should pair them
        delta_map = {d.section_id: d for d in result.section_deltas}

        # sec_1 matches exactly
        assert delta_map["sec_1"].delta_type == "unchanged"

        # sec_1a is new
        assert delta_map["sec_1a"].delta_type == "added"

        # sec_3 should be paired with old sec_2 via fuzzy alignment
        # Since the text is identical except for section number prefix, it should be "modified" or "unchanged"
        sec3_delta = delta_map.get("sec_3")
        if sec3_delta:
            # Should NOT be pure "added" — fuzzy alignment should catch this
            assert sec3_delta.delta_type in ("unchanged", "modified")

        # sec_2 should NOT appear as "removed" if fuzzy alignment worked
        if "sec_2" in delta_map:
            assert delta_map["sec_2"].delta_type != "removed" or sec3_delta is None


class TestIdenticalVersionsProduceNoDiff:
    """Processing the same content twice yields no changes."""

    def test_no_modifications(self):
        sections = [
            _sec("sec_1", "Section 1", "Section 1. Definitions for this chapter."),
            _sec("sec_2", "Section 2", "Section 2. Implementation procedures."),
        ]
        v1 = _make_doc("2026-SB00060-FC00001", sections)
        v2 = _make_doc("2026-SB00060-FC00002", sections)

        result = diff_documents(v2, v1)
        assert result.sections_modified == 0
        assert result.sections_added == 0
        assert result.sections_removed == 0
        assert all(d.delta_type == "unchanged" for d in result.section_deltas)

        events = classify_changes(result)
        assert len(events) == 0
