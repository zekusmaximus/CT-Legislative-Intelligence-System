"""Tests for the subject tagger."""

from src.schemas.extraction import ExtractedDocument, PageText, SectionSpan
from src.scoring.subject_tagger import tag_bill_version


def _make_doc(text: str, version_id: str = "v1") -> ExtractedDocument:
    return ExtractedDocument(
        canonical_version_id=version_id,
        pages=[
            PageText(
                page_number=1,
                raw_text=text,
                cleaned_text=text,
                extraction_method="text",
                extraction_confidence=0.9,
            )
        ],
        full_raw_text=text,
        full_cleaned_text=text,
        sections=[
            SectionSpan(
                section_id="sec_1",
                heading="Section 1",
                start_page=1,
                end_page=1,
                start_char=0,
                end_char=len(text),
                text=text,
            )
        ],
        overall_extraction_confidence=0.9,
    )


class TestSubjectTagger:
    def test_transportation_tagged(self):
        doc = _make_doc(
            "An act concerning transportation network companies "
            "and municipal transit pilot programs."
        )
        result = tag_bill_version(doc)
        assert "transportation" in result.subject_tags

    def test_healthcare_tagged(self):
        doc = _make_doc(
            "An act concerning health insurance coverage "
            "for mental health services and hospital access."
        )
        result = tag_bill_version(doc)
        assert "healthcare" in result.subject_tags

    def test_no_tags_for_generic_text(self):
        doc = _make_doc("A very short document about nothing in particular.")
        result = tag_bill_version(doc)
        assert len(result.subject_tags) == 0
        assert result.tag_confidence < 0.5

    def test_multiple_subjects(self):
        doc = _make_doc(
            "An act concerning education funding for school "
            "districts and student health insurance coverage "
            "for hospital visits and medical services."
        )
        result = tag_bill_version(doc)
        assert len(result.subject_tags) >= 2

    def test_rationale_provided(self):
        doc = _make_doc("Act about transportation and transit and vehicle regulation.")
        result = tag_bill_version(doc)
        assert len(result.rationale) > 0

    def test_confidence_increases_with_tags(self):
        sparse = _make_doc("Just about transportation and transit.")
        rich = _make_doc(
            "Transportation and transit. Education and school "
            "funding. Healthcare and hospital requirements. "
            "Environmental pollution and climate."
        )
        sparse_result = tag_bill_version(sparse)
        rich_result = tag_bill_version(rich)
        assert rich_result.tag_confidence >= sparse_result.tag_confidence
