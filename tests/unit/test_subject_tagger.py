"""Tests for the subject tagger with controlled vocabulary enforcement."""

import pytest

from src.metadata.taxonomy import InvalidTaxonomyValueError, load_subject_tags
from src.schemas.extraction import ExtractedDocument, PageText, SectionSpan
from src.scoring.subject_tagger import SUBJECT_KEYWORDS, tag_bill_version


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

    def test_health_care_tagged(self):
        doc = _make_doc(
            "An act concerning health care coverage "
            "for mental health services and hospital access."
        )
        result = tag_bill_version(doc)
        assert "health_care" in result.subject_tags

    def test_no_tags_for_generic_text(self):
        doc = _make_doc("A very short document about nothing in particular.")
        result = tag_bill_version(doc)
        assert len(result.subject_tags) == 0
        assert result.tag_confidence < 0.5

    def test_multiple_subjects(self):
        doc = _make_doc(
            "An act concerning education funding for school "
            "districts and student health care coverage "
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
            "funding. Health care and hospital requirements. "
            "Environmental pollution and climate."
        )
        sparse_result = tag_bill_version(sparse)
        rich_result = tag_bill_version(rich)
        assert rich_result.tag_confidence >= sparse_result.tag_confidence


class TestVocabularyCompliance:
    """Tests proving taggers cannot emit unsupported values."""

    def test_all_keyword_map_keys_are_canonical(self):
        """Every key in SUBJECT_KEYWORDS must be in the approved taxonomy."""
        approved = load_subject_tags()
        for key in SUBJECT_KEYWORDS:
            assert key in approved, f"'{key}' is not an approved subject tag"

    def test_all_canonical_tags_have_keywords(self):
        """Every approved tag must have a keyword entry (no gaps)."""
        approved = load_subject_tags()
        for tag in approved:
            assert tag in SUBJECT_KEYWORDS, f"Approved tag '{tag}' has no keywords"

    def test_emitted_tags_are_canonical(self):
        """All tags returned by the tagger must be in the approved set."""
        approved = load_subject_tags()
        doc = _make_doc(
            "An act concerning transportation and transit and vehicle "
            "and education school student teacher curriculum "
            "and health care hospital medical medicaid "
            "and tax revenue assessment income tax sales tax "
            "and cannabis marijuana hemp dispensary "
            "and gaming gambling casino lottery "
            "and housing landlord tenant rent eviction "
            "and energy environment pollution emission climate conservation "
            "and criminal felony misdemeanor law enforcement police "
            "and data privacy personal data biometric "
        )
        result = tag_bill_version(doc)
        assert len(result.subject_tags) > 0
        for tag in result.subject_tags:
            assert tag in approved, f"Emitted tag '{tag}' is not canonical"

    def test_tagger_never_invents_tags(self):
        """Even with varied legislative text, only canonical tags appear."""
        texts = [
            "An act concerning zoning and land use and planning.",
            "An act concerning insurance and insurer and premium coverage.",
            "An act concerning labor employment and wage and worker.",
            "An act concerning appropriation budget general fund.",
            "An act concerning municipality municipal town city.",
        ]
        approved = load_subject_tags()
        for text in texts:
            doc = _make_doc(text)
            result = tag_bill_version(doc)
            for tag in result.subject_tags:
                assert tag in approved, f"Emitted tag '{tag}' is not canonical"
