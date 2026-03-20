"""Tests for the taxonomy loader and vocabulary validation."""

import pytest

from src.metadata.taxonomy import (
    InvalidTaxonomyValueError,
    load_change_flags,
    load_subject_tags,
    load_urgency_levels,
    validate_change_flags,
    validate_subject_tags,
    validate_urgency,
)


class TestTaxonomyLoader:
    def test_load_subject_tags(self):
        tags = load_subject_tags()
        assert len(tags) == 28
        assert "health_care" in tags
        assert "transportation" in tags
        assert "artificial_intelligence" in tags

    def test_load_change_flags(self):
        flags = load_change_flags()
        assert len(flags) == 34
        assert "section_added" in flags
        assert "section_removed" in flags
        assert "effective_date_changed" in flags

    def test_load_urgency_levels(self):
        levels = load_urgency_levels()
        assert levels == frozenset({"low", "medium", "high", "critical"})


class TestVocabularyValidation:
    def test_validate_valid_subject_tags(self):
        result = validate_subject_tags(["health_care", "transportation"])
        assert result == ["health_care", "transportation"]

    def test_validate_invalid_subject_tag_raises(self):
        with pytest.raises(InvalidTaxonomyValueError, match="Invalid subject tag"):
            validate_subject_tags(["health_care", "bogus_tag"])

    def test_validate_empty_subject_tags(self):
        result = validate_subject_tags([])
        assert result == []

    def test_validate_valid_change_flags(self):
        result = validate_change_flags(["section_added", "penalty_added"])
        assert result == ["section_added", "penalty_added"]

    def test_validate_invalid_change_flag_raises(self):
        with pytest.raises(InvalidTaxonomyValueError, match="Invalid change flag"):
            validate_change_flags(["section_added", "totally_made_up"])

    def test_validate_old_flag_names_rejected(self):
        """Old non-canonical flag names must be rejected."""
        old_flags = [
            "new_section_added",
            "effective_date_change",
            "definition_change",
            "appropriation_change",
            "penalty_change",
            "regulatory_change",
            "scope_change",
            "substantive_amendment",
            "technical_correction",
        ]
        for flag in old_flags:
            with pytest.raises(InvalidTaxonomyValueError):
                validate_change_flags([flag])

    def test_validate_valid_urgency(self):
        assert validate_urgency("critical") == "critical"
        assert validate_urgency("low") == "low"

    def test_validate_invalid_urgency_raises(self):
        with pytest.raises(InvalidTaxonomyValueError, match="Invalid urgency"):
            validate_urgency("super_critical")
