"""Tests for the summary generator."""

from src.diff.section_differ import diff_documents
from src.schemas.extraction import ExtractedDocument, PageText, SectionSpan
from src.scoring.summary_generator import generate_summary


def _make_doc(sections: list[SectionSpan], version_id: str = "v1") -> ExtractedDocument:
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


def _sec(sid: str, heading: str, text: str) -> SectionSpan:
    return SectionSpan(
        section_id=sid,
        heading=heading,
        start_page=1,
        end_page=1,
        start_char=0,
        end_char=len(text),
        text=text,
    )


class TestSummaryGenerator:
    def test_generates_one_sentence(self):
        doc = _make_doc(
            [
                _sec("sec_1", "Section 1", "First section."),
            ]
        )
        summary = generate_summary(doc, bill_title="Test Bill")
        assert "Test Bill" in summary.one_sentence_summary
        assert len(summary.one_sentence_summary) > 0

    def test_deep_summary_includes_sections(self):
        doc = _make_doc(
            [
                _sec("sec_1", "Section 1", "Content of section one."),
                _sec("sec_2", "Section 2", "Content of section two."),
            ]
        )
        summary = generate_summary(doc)
        assert "Section 1" in summary.deep_summary
        assert "Section 2" in summary.deep_summary

    def test_diff_summary_shows_changes(self):
        prior = _make_doc(
            [
                _sec("sec_1", "Section 1", "Original text."),
            ],
            version_id="v1",
        )
        current = _make_doc(
            [
                _sec("sec_1", "Section 1", "Modified text."),
                _sec("sec_2", "Section 2", "New section."),
            ],
            version_id="v2",
        )

        diff = diff_documents(current, prior)
        summary = generate_summary(current, diff_result=diff, bill_title="Test Bill")
        assert "added" in summary.one_sentence_summary.lower()
        assert len(summary.practical_takeaways) > 0

    def test_key_sections_for_effective_date(self):
        doc = _make_doc(
            [
                _sec("sec_1", "Section 1", "Regular content."),
                _sec(
                    "sec_4",
                    "Section 4",
                    "This act shall take effect July 1, 2026.",
                ),
            ]
        )
        summary = generate_summary(doc)
        assert any("Section 4" in k for k in summary.key_sections_to_review)

    def test_takeaways_for_new_bill(self):
        doc = _make_doc(
            [
                _sec("sec_1", "Section 1", "Content."),
            ]
        )
        summary = generate_summary(doc)
        assert len(summary.practical_takeaways) > 0
        assert "initial review" in summary.practical_takeaways[0].lower()

    def test_confidence_reflects_extraction(self):
        doc = _make_doc(
            [
                _sec("sec_1", "Section 1", "Content."),
            ]
        )
        summary = generate_summary(doc, bill_title="Title")
        assert summary.confidence > 0
        assert summary.confidence <= 1.0
