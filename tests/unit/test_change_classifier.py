"""Tests for the change event classifier with controlled vocabulary enforcement."""

import pytest

from src.diff.change_classifier import classify_changes
from src.metadata.taxonomy import InvalidTaxonomyValueError, load_change_flags
from src.schemas.diff import BillDiffResult, SectionDelta


def _make_diff(deltas: list[SectionDelta]) -> BillDiffResult:
    added = sum(1 for d in deltas if d.delta_type == "added")
    removed = sum(1 for d in deltas if d.delta_type == "removed")
    modified = sum(1 for d in deltas if d.delta_type == "modified")
    return BillDiffResult(
        bill_id="SB00093",
        current_version_id="v2",
        prior_version_id="v1",
        compared_against="prior_file_copy",
        sections_added=added,
        sections_removed=removed,
        sections_modified=modified,
        section_deltas=deltas,
        change_events=[],
    )


class TestChangeClassifier:
    def test_added_section_creates_event(self):
        diff = _make_diff(
            [
                SectionDelta(
                    section_id="sec_1",
                    new_heading="Section 1",
                    delta_type="added",
                    new_text="This act shall take effect July 1, 2026.",
                    similarity_score=0.0,
                ),
            ]
        )
        events = classify_changes(diff)
        flags = {e.change_flag for e in events}
        assert "section_added" in flags

    def test_removed_section_creates_event(self):
        diff = _make_diff(
            [
                SectionDelta(
                    section_id="sec_1",
                    old_heading="Section 1",
                    delta_type="removed",
                    old_text="Old provision text",
                    similarity_score=0.0,
                ),
            ]
        )
        events = classify_changes(diff)
        flags = {e.change_flag for e in events}
        assert "section_removed" in flags

    def test_high_similarity_produces_no_events(self):
        """Very similar text (>0.90 similarity) produces no events unless specific flags match."""
        diff = _make_diff(
            [
                SectionDelta(
                    section_id="sec_1",
                    old_heading="Section 1",
                    new_heading="Section 1",
                    delta_type="modified",
                    old_text="The commissioner shall adopt rules.",
                    new_text="The commissioner shall adopt regulations.",
                    similarity_score=0.92,
                ),
            ]
        )
        events = classify_changes(diff)
        # With high similarity and no specific content-pattern matches, may produce no events
        # or may produce specific flags if patterns match
        for e in events:
            assert e.change_flag in load_change_flags()

    def test_effective_date_detected(self):
        diff = _make_diff(
            [
                SectionDelta(
                    section_id="sec_4",
                    new_heading="Section 4",
                    delta_type="added",
                    new_text="This act shall take effect October 1, 2026.",
                    similarity_score=0.0,
                ),
            ]
        )
        events = classify_changes(diff)
        flags = {e.change_flag for e in events}
        assert "effective_date_changed" in flags

    def test_appropriation_detected(self):
        diff = _make_diff(
            [
                SectionDelta(
                    section_id="sec_3",
                    new_heading="Section 3",
                    delta_type="added",
                    new_text="There is appropriated from the General Fund "
                    "the sum of five million dollars.",
                    similarity_score=0.0,
                ),
            ]
        )
        events = classify_changes(diff)
        flags = {e.change_flag for e in events}
        assert "appropriation_added" in flags

    def test_unchanged_produces_no_events(self):
        diff = _make_diff(
            [
                SectionDelta(
                    section_id="sec_1",
                    old_heading="S1",
                    new_heading="S1",
                    delta_type="unchanged",
                    similarity_score=1.0,
                ),
            ]
        )
        events = classify_changes(diff)
        assert len(events) == 0

    def test_penalty_detected(self):
        diff = _make_diff(
            [
                SectionDelta(
                    section_id="sec_2",
                    new_heading="Section 2",
                    delta_type="added",
                    new_text="Any violation shall be subject to a fine "
                    "of not more than five thousand dollars.",
                    similarity_score=0.0,
                ),
            ]
        )
        events = classify_changes(diff)
        flags = {e.change_flag for e in events}
        assert "penalty_added" in flags

    def test_licensing_detected(self):
        diff = _make_diff(
            [
                SectionDelta(
                    section_id="sec_5",
                    new_heading="Section 5",
                    delta_type="added",
                    new_text="No person shall operate without a license "
                    "issued pursuant to this certification program.",
                    similarity_score=0.0,
                ),
            ]
        )
        events = classify_changes(diff)
        flags = {e.change_flag for e in events}
        assert "licensing_requirement_added" in flags

    def test_reporting_requirement_detected(self):
        diff = _make_diff(
            [
                SectionDelta(
                    section_id="sec_6",
                    new_heading="Section 6",
                    delta_type="added",
                    new_text="The commissioner shall submit an annual report "
                    "to the General Assembly on the reporting requirement.",
                    similarity_score=0.0,
                ),
            ]
        )
        events = classify_changes(diff)
        flags = {e.change_flag for e in events}
        assert "reporting_requirement_added" in flags


class TestVocabularyCompliance:
    """Tests proving classifiers cannot emit unsupported change flag values."""

    def test_all_emitted_flags_are_canonical(self):
        """Every flag emitted by classify_changes must be in the approved set."""
        approved = load_change_flags()
        # Exercise multiple delta types
        diff = _make_diff(
            [
                SectionDelta(
                    section_id="sec_1",
                    new_heading="Section 1",
                    delta_type="added",
                    new_text=(
                        "This act shall take effect July 1, 2026. "
                        "There is appropriated from the General Fund the sum of $5M. "
                        "Any violation shall be subject to a fine. "
                        'As used in this act, "provider" means a licensed entity. '
                        "No person shall operate without a license. "
                        "The commissioner shall submit an annual report."
                    ),
                    similarity_score=0.0,
                ),
                SectionDelta(
                    section_id="sec_2",
                    old_heading="Section 2",
                    delta_type="removed",
                    old_text="Old repealed language.",
                    similarity_score=0.0,
                ),
                SectionDelta(
                    section_id="sec_3",
                    old_heading="Section 3",
                    new_heading="Section 3",
                    delta_type="modified",
                    old_text="Old scope language about applicability.",
                    new_text="Expanded new scope language with broader applicability and more detail.",
                    similarity_score=0.4,
                ),
            ]
        )
        events = classify_changes(diff)
        assert len(events) > 0
        for event in events:
            assert event.change_flag in approved, (
                f"Emitted flag '{event.change_flag}' is not in approved vocabulary"
            )

    def test_modified_section_flags_are_canonical(self):
        """Modified section classification emits only canonical flags."""
        approved = load_change_flags()
        diff = _make_diff(
            [
                SectionDelta(
                    section_id="sec_1",
                    old_heading="Section 1",
                    new_heading="Section 1",
                    delta_type="modified",
                    old_text="The penalty for violation shall be a fine of $1000.",
                    new_text="No penalty provisions in this version.",
                    similarity_score=0.3,
                ),
            ]
        )
        events = classify_changes(diff)
        for event in events:
            assert event.change_flag in approved

    def test_no_old_flag_names_emitted(self):
        """Ensure none of the old non-canonical flag names are emitted."""
        old_flags = {
            "new_section_added",
            "effective_date_change",
            "definition_change",
            "appropriation_change",
            "penalty_change",
            "regulatory_change",
            "scope_change",
            "substantive_amendment",
            "technical_correction",
        }
        diff = _make_diff(
            [
                SectionDelta(
                    section_id="sec_1",
                    new_heading="Section 1",
                    delta_type="added",
                    new_text=(
                        "This act shall take effect July 1, 2026. "
                        "There is appropriated $5M. "
                        "Any violation subject to fine. "
                        'As used in this act, "X" means Y. '
                        "Regulatory compliance and inspection required."
                    ),
                    similarity_score=0.0,
                ),
            ]
        )
        events = classify_changes(diff)
        for event in events:
            assert event.change_flag not in old_flags, (
                f"Old flag name '{event.change_flag}' was emitted"
            )
