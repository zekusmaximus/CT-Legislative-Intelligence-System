"""Tests for the section-level differ."""

from src.diff.section_differ import diff_documents, get_unified_diff
from src.schemas.extraction import ExtractedDocument, PageText, SectionSpan


def _make_doc(version_id: str, sections: list[SectionSpan]) -> ExtractedDocument:
    full_text = "\n\n".join(s.text for s in sections)
    return ExtractedDocument(
        canonical_version_id=version_id,
        pages=[
            PageText(
                page_number=1,
                raw_text=full_text,
                cleaned_text=full_text,
                extraction_method="text",
                extraction_confidence=0.9,
            )
        ],
        full_raw_text=full_text,
        full_cleaned_text=full_text,
        sections=sections,
        overall_extraction_confidence=0.9,
    )


def _make_section(section_id: str, heading: str, text: str) -> SectionSpan:
    return SectionSpan(
        section_id=section_id,
        heading=heading,
        start_page=1,
        end_page=1,
        start_char=0,
        end_char=len(text),
        text=text,
    )


class TestSectionDiffer:
    def test_no_prior_all_added(self):
        doc = _make_doc(
            "2026-SB00093-FC00044",
            [
                _make_section("sec_1", "Section 1", "First section text"),
                _make_section("sec_2", "Section 2", "Second section text"),
            ],
        )
        result = diff_documents(doc, None)
        assert result.compared_against == "none"
        assert result.sections_added == 2
        assert result.sections_removed == 0
        assert result.sections_modified == 0
        assert all(d.delta_type == "added" for d in result.section_deltas)

    def test_identical_documents(self):
        sections = [
            _make_section("sec_1", "Section 1", "Same text"),
        ]
        doc1 = _make_doc("2026-SB00093-FC00031", sections)
        doc2 = _make_doc("2026-SB00093-FC00044", sections)
        result = diff_documents(doc2, doc1)
        assert result.sections_modified == 0
        assert result.section_deltas[0].delta_type == "unchanged"

    def test_modified_section(self):
        prior = _make_doc(
            "2026-SB00093-FC00031",
            [
                _make_section("sec_1", "Section 1", "Original text about transportation"),
            ],
        )
        current = _make_doc(
            "2026-SB00093-FC00044",
            [
                _make_section("sec_1", "Section 1", "Modified text about transit services"),
            ],
        )
        result = diff_documents(current, prior)
        assert result.sections_modified == 1
        delta = result.section_deltas[0]
        assert delta.delta_type == "modified"
        assert 0 < delta.similarity_score < 1

    def test_added_section(self):
        prior = _make_doc(
            "v1",
            [
                _make_section("sec_1", "Section 1", "Text"),
            ],
        )
        current = _make_doc(
            "v2",
            [
                _make_section("sec_1", "Section 1", "Text"),
                _make_section("sec_2", "Section 2", "New section"),
            ],
        )
        result = diff_documents(current, prior)
        assert result.sections_added == 1
        added = [d for d in result.section_deltas if d.delta_type == "added"]
        assert len(added) == 1
        assert added[0].section_id == "sec_2"

    def test_removed_section(self):
        prior = _make_doc(
            "v1",
            [
                _make_section("sec_1", "Section 1", "Text"),
                _make_section("sec_2", "Section 2", "Removed later"),
            ],
        )
        current = _make_doc(
            "v2",
            [
                _make_section("sec_1", "Section 1", "Text"),
            ],
        )
        result = diff_documents(current, prior)
        assert result.sections_removed == 1

    def test_version_ids_set(self):
        doc = _make_doc(
            "2026-SB00093-FC00044",
            [
                _make_section("sec_1", "S1", "Text"),
            ],
        )
        result = diff_documents(doc, None)
        assert result.current_version_id == "2026-SB00093-FC00044"
        assert result.prior_version_id is None

    def test_unified_diff_output(self):
        old = "Line 1\nLine 2\nLine 3"
        new = "Line 1\nLine 2 modified\nLine 3"
        diff = get_unified_diff(old, new)
        assert "---" in diff
        assert "+++" in diff
        assert "-Line 2" in diff
        assert "+Line 2 modified" in diff
