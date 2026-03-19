"""Tests for the change event classifier."""

from src.diff.change_classifier import classify_changes
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
        diff = _make_diff([
            SectionDelta(
                section_id="sec_1",
                new_heading="Section 1",
                delta_type="added",
                new_text="This act shall take effect July 1, 2026.",
                similarity_score=0.0,
            ),
        ])
        events = classify_changes(diff)
        flags = {e.change_flag for e in events}
        assert "new_section_added" in flags

    def test_removed_section_creates_event(self):
        diff = _make_diff([
            SectionDelta(
                section_id="sec_1",
                old_heading="Section 1",
                delta_type="removed",
                old_text="Old provision text",
                similarity_score=0.0,
            ),
        ])
        events = classify_changes(diff)
        flags = {e.change_flag for e in events}
        assert "section_removed" in flags

    def test_technical_correction(self):
        diff = _make_diff([
            SectionDelta(
                section_id="sec_1",
                old_heading="Section 1",
                new_heading="Section 1",
                delta_type="modified",
                old_text="The commissioner shall adopt rules.",
                new_text="The commissioner shall adopt regulations.",
                similarity_score=0.92,
            ),
        ])
        events = classify_changes(diff)
        flags = {e.change_flag for e in events}
        assert "technical_correction" in flags

    def test_substantive_amendment(self):
        diff = _make_diff([
            SectionDelta(
                section_id="sec_1",
                old_heading="Section 1",
                new_heading="Section 1",
                delta_type="modified",
                old_text="Grant program for municipalities.",
                new_text="Completely new regulatory framework "
                "with licensing requirements.",
                similarity_score=0.3,
            ),
        ])
        events = classify_changes(diff)
        flags = {e.change_flag for e in events}
        assert "substantive_amendment" in flags

    def test_effective_date_detected(self):
        diff = _make_diff([
            SectionDelta(
                section_id="sec_4",
                new_heading="Section 4",
                delta_type="added",
                new_text="This act shall take effect October 1, 2026.",
                similarity_score=0.0,
            ),
        ])
        events = classify_changes(diff)
        flags = {e.change_flag for e in events}
        assert "effective_date_change" in flags

    def test_appropriation_detected(self):
        diff = _make_diff([
            SectionDelta(
                section_id="sec_3",
                new_heading="Section 3",
                delta_type="added",
                new_text="There is appropriated from the General Fund "
                "the sum of five million dollars.",
                similarity_score=0.0,
            ),
        ])
        events = classify_changes(diff)
        flags = {e.change_flag for e in events}
        assert "appropriation_change" in flags

    def test_unchanged_produces_no_events(self):
        diff = _make_diff([
            SectionDelta(
                section_id="sec_1",
                old_heading="S1",
                new_heading="S1",
                delta_type="unchanged",
                similarity_score=1.0,
            ),
        ])
        events = classify_changes(diff)
        assert len(events) == 0

    def test_penalty_detected(self):
        diff = _make_diff([
            SectionDelta(
                section_id="sec_2",
                new_heading="Section 2",
                delta_type="added",
                new_text="Any violation shall be subject to a fine "
                "of not more than five thousand dollars.",
                similarity_score=0.0,
            ),
        ])
        events = classify_changes(diff)
        flags = {e.change_flag for e in events}
        assert "penalty_change" in flags
